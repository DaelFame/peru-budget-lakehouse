# Peru Budget Lakehouse

**Analytics engineering pipeline processing 54M+ financial records (8.5GB raw CSV) on $0 infrastructure — medallion architecture, Kimball star schema, conversational LLM analytics, financial reconciliation gate.**

[![CI](https://github.com/YOUR_GITHUB_USERNAME/peru-budget-lakehouse/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_GITHUB_USERNAME/peru-budget-lakehouse/actions)
[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![Polars](https://img.shields.io/badge/Polars-1.40-orange)](https://pola.rs/)
[![DuckDB](https://img.shields.io/badge/DuckDB-OLAP-yellow)](https://duckdb.org/)
[![Prefect](https://img.shields.io/badge/Prefect-3.x-purple)](https://www.prefect.io/)
[![Docker](https://img.shields.io/badge/Docker-containerized-blue)](https://www.docker.com/)
[![Parquet](https://img.shields.io/badge/Storage-Parquet_ZSTD-green)](https://parquet.apache.org/)

**→ [Live dashboard (demo)](https://peru-fiscal-lakehouse.streamlit.app/)**

---

## What this is

A production-grade ETL pipeline that ingests Peru's national budget execution dataset, normalizes it through a three-layer medallion architecture, models it as a Kimball star schema, enforces financial reconciliation before any report is produced, and exposes the Gold layer to a conversational LLM analytics interface.

The domain comes from years of auditing financial statements at KPMG — reconciling ledgers, testing controls, building Excel workbooks that collapsed under their own weight. Every manual tie-out and vlookup chain from those audits is what this pipeline automates.

**The engineering problem is not throughput. It is correctness under memory constraints.**  
54M rows. 8.5GB source file. Local hardware. No cloud. No OOM errors.

---

## Architecture

```
8.5GB RAW CSV (54M rows)
        │
        ▼
┌─────────────────────────────┐
│  BRONZE  — Polars streaming │  29s
│  CSV → Parquet ZSTD         │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  SILVER  — Normalization    │  16s
│  Type casting, null gates   │
│  Column standardization     │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  SILVER  — UNPIVOT          │  3m 41s
│  DuckDB vectorized UNPIVOT  │
│  35 wide columns → long     │
│  2.4GB Parquet output       │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  GOLD  — Star Schema        │  59s
│  1 fact + 5 dimensions      │
│  wyhash surrogate keys      │
└──────┬──────────────────────┘
       │
  ┌────┴──────────────────┐
  ▼                       ▼
QA Gate            Streamlit Dashboard
S/.0.00            ├── Deterministic DuckDB reports
discrepancy        └── Conversational LLM analytics
                       (NL → SQL → synthesis)
```

**Total pipeline: 328s (5.47 min) · Peak RAM: <4GB**

---

## Star schema

```
              dim_geografia
             (district grain)
                    │
    dim_institucion ─── fact_presupuesto ─── dim_programatica
    (executor unit)       (47M+ rows)        (activity grain)
                    │               │
              dim_economica    dim_financiamiento
              (expenditure      (funding source)
               classifier)
```

**Fact grain:** one row per `(institution × geography × program × economic classifier × funding source × year × execution phase)` — a fully exploded accounting ledger at execution-level granularity, normalized for OLAP queries.

---

## Engineering decisions worth reading

### 1. Polars streaming instead of Pandas

`scan_parquet` + `sink_parquet` never materializes the full dataset. Peak RAM stays under 4GB regardless of input size. This is not a performance optimization — it is the only approach that runs on constrained hardware without OOM. Pandas would fail at the `read_csv` call.

### 2. DuckDB for UNPIVOT, Polars for everything else

Silver reshapes 35 wide financial columns (`pim_2022`, `devengado_2023`, etc.) into long format. Polars `melt()` on 54M rows at this width causes OOM. DuckDB's vectorized UNPIVOT processes this through the query optimizer with bounded memory. The tradeoff is explicit: DuckDB owns this one transformation, Polars owns everything else.

### 3. `polars-hash` for stable surrogate keys instead of `pl.hash()`

`pl.hash()` does not guarantee identical output across Polars version upgrades. A version bump silently breaks every FK relationship between dimension and fact tables — the join returns zero rows with no error. `polars-hash` provides deterministic wyhash keys that survive version changes, and unlike `map_elements`, it runs inside the Polars streaming engine without forcing RAM materialization.

### 4. `ignore_nulls=True` in `concat_str` — a real data integrity bug

Municipal entities (`nivel_gobierno = "gobierno local"`) frequently have `pliego = NULL` in source data. Without `ignore_nulls=True`, one NULL field collapses the entire surrogate key expression to NULL — producing the same key for thousands of different municipalities. Silent collision. This was a live data integrity bug, caught and fixed at the hash generation layer. See `etl_04_star_schema.py` line ~88.

### 5. Financial reconciliation as a hard pipeline gate — not a warning

```python
assert abs(sum_silver - sum_gold) <= Decimal("0.01"), \
    f"Reconciliation failed: S/. {discrepancy:.2f} discrepancy"
```

`abs(Σ silver.monto − Σ gold.monto) ≤ S/. 0.01` is enforced before any report runs. If violated, the pipeline raises and halts. This is the same control logic used in accounting systems: no downstream output until the numbers tie out.

**Current result: S/. 0.00 discrepancy.**

---

## Conversational analytics layer

Natural language → SQL → DuckDB execution → structured executive summary.

Two LLM calls per question (Groq / `llama-3.3-70b-versatile`):

```
User question
      │
      ▼
  LLM Call 1 — _translate_to_sql()
  System prompt: 200-line schema description
  + business rules + 8 worked examples
      │
      ▼
  QueryValidationPolicy        ← SELECT-only, 20 forbidden keywords (sqlparse)
  SQLSemanticContractValidator ← column scope, aggregation consistency,
                                  CTE dependency graph, grain detection
      │
      ▼
  DuckDB execution over Gold Parquet views
      │
      ▼
  LLM Call 2 — _synthesize()
  Input: question + SQL + results
  Output: structured JSON
         (intent, title, KPIs, chart spec, insights, follow-ups)
      │
      ▼
  Streamlit + Plotly rendering
```

The LLM never sees raw data — it sees the schema, generates SQL, and synthesizes the execution results. Two independent validation layers run between generation and execution.

---

## Data quality gates

| Gate | Logic | On failure |
|---|---|---|
| Financial reconciliation | `abs(Σ Silver − Σ Gold) ≤ S/. 0.01` | `ValueError` raised, pipeline stops |
| Row volumetrics | Silver clean rows == Gold fact rows | Warning logged, gap reported |
| SQL safety | SELECT-only, 20 forbidden tokens | Query rejected before execution |
| SQL semantics | Column scope, aggregation, grain | Query rejected before execution |

108 unit tests — executed automatically on every push to `main` via GitHub Actions.

### Pipeline determinism

`scripts/test_pipeline_diff.py` runs the full pipeline twice and compares outputs — row counts, schemas, and monetary sums must be identical across runs. Any drift raises an error. This catches non-determinism in hash generation, float precision, or row-ordering dependencies before they reach production.

Silent transformation errors are worse than crashes. This pipeline fails loudly instead of producing plausible but incorrect aggregates.

---

## Performance

| Stage | Runtime |
|---|---|
| Bronze ingestion | 29.34s |
| Silver cleaning | 16.17s |
| Silver UNPIVOT | 220.90s |
| Gold star schema | 59.48s |
| QA audit | 1.38s |
| Analytical reports | 0.96s |
| **Total** | **328.39s (5.47 min)** |

Measured on commodity hardware, constrained RAM, no cloud.

---

## Quick start

### Option A — Live demo (no setup)

**[peru-fiscal-lakehouse.streamlit.app](https://peru-fiscal-lakehouse.streamlit.app/)** — runs on a pre-built 450K-row stratified sample. Open and use immediately.

### Option B — Docker

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/peru-budget-lakehouse
cd peru-budget-lakehouse
docker build -t peru-budget-lakehouse .
docker run -p 8501:8501 peru-budget-lakehouse
```

Dashboard loads at `http://localhost:8501`.

### Option C — Local (uv)

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/peru-budget-lakehouse
cd peru-budget-lakehouse
uv sync
uv run streamlit run app.py
```

### Option D — Full pipeline

Download the MEF budget execution CSV (~8.5GB) from the [MEF open data portal](https://datosabiertos.mef.gob.pe/dataset/comparacion-de-presupuesto-ejecucion-gasto/resource/510bae6d-3d37-4fb2-af35-a40ce01715f4) and place it at:

```
data/comparativo_gastos_2022_2026.csv
```

Then run:

```bash
uv run python main.py   # Prefect-orchestrated, sequential
```

Or stage by stage:

```bash
uv run python src/etl_01_bronze_ingestion.py
uv run python src/etl_02_silver_cleaning.py
uv run python src/etl_03_silver_unpivot.py
uv run python src/etl_04_star_schema.py
uv run python src/etl_05_data_quality_audit.py
uv run python src/etl_06_analytical_reports.py
```

---

## What to read first

| File | What it demonstrates |
|---|---|
| `src/etl_03_silver_unpivot.py` | DuckDB UNPIVOT — the core memory tradeoff |
| `src/etl_04_star_schema.py` | `ignore_nulls=True` on line ~88 — why it exists |
| `src/etl_05_data_quality_audit.py` | Financial reconciliation gate logic |
| `src/dashboard/ai_engine.py` | Two-LLM-call pipeline, SQL validation layers |
| `src/dashboard/semantic_contract.py` | `SQLSemanticContractValidator` — column scope, grain enforcement |
| `main.py` | Prefect `wait_for=` dependency chain |
| `src/config.py` | Hardware auto-detection, smart path resolver |

---

## Stack

| Tool | Why |
|---|---|
| Polars 1.40 | Streaming LazyFrame engine, Rust core, zero-copy scans |
| DuckDB | Vectorized UNPIVOT, embedded OLAP, zero-copy Parquet reads |
| polars-hash 0.6 | Cross-version stable wyhash surrogate keys |
| Groq / llama-3.3-70b | LLM backend for NL→SQL and synthesis |
| Prefect 3.x | Task-level observability, `wait_for=` dependency enforcement |
| Streamlit | Dashboard and conversational UI |
| Docker | Reproducible environment — eliminates native dependency friction (Polars/Rust, DuckDB) |
| GitHub Actions | CI — 108 unit tests on every push to `main` |
| Parquet + ZSTD | 3–5x compression vs CSV, columnar pushdown |
| uv | Rust-based package manager, reproducible lockfile |

---

## Project structure

```
peru-budget-lakehouse/
├── main.py                               # Prefect orchestration entry point
├── Dockerfile
├── src/
│   ├── config.py                         # Paths, hardware detection, constants
│   ├── etl_01_bronze_ingestion.py
│   ├── etl_02_silver_cleaning.py
│   ├── etl_03_silver_unpivot.py          # DuckDB UNPIVOT
│   ├── etl_04_star_schema.py             # Star schema, wyhash surrogate keys
│   ├── etl_05_data_quality_audit.py      # Reconciliation gate
│   ├── etl_06_analytical_reports.py
│   ├── dashboard/
│   │   ├── ai_engine.py                  # Two-LLM-call pipeline
│   │   ├── semantic_contract.py          # SQL semantic validator
│   │   ├── grain_router.py               # Grain classifier (pre-LLM)
│   │   ├── components.py                 # Streamlit rendering
│   │   └── database.py                   # DuckDB view registration
│   └── observability/                    # Query execution trace model
├── scripts/
│   └── test_pipeline_diff.py             # Determinism checker (dual-run comparison)
├── tests/                                # 108 unit tests
├── sql/
├── data/
│   ├── 00_demo/                          # Pre-built 450K-row Gold Parquet
│   ├── 01_bronze/                        # gitignored
│   ├── 02_silver/                        # gitignored
│   └── 03_gold/                          # gitignored
├── pyproject.toml
└── uv.lock
```

---

## Roadmap

- [x] Medallion pipeline: Bronze → Silver → Gold (streaming at every layer)
- [x] Kimball star schema: 1 fact + 5 dimensions, wyhash surrogate keys
- [x] Financial reconciliation QA gate (S/. 0.01 tolerance)
- [x] Prefect orchestration with explicit sequential dependencies
- [x] DuckDB analytical reports layer
- [x] Demo dataset (stratified 450K-row sample)
- [x] Live Streamlit dashboard
- [x] Conversational LLM analytics (NL → SQL → synthesis, two-call pipeline)
- [x] SQL safety guardrails (SELECT-only + semantic contract validator)
- [x] 108 unit tests + GitHub Actions CI
- [x] Docker
- [ ] Wire `GrainRouter` into `AIEngine.ask()` — pre-LLM grain classification exists and is tested, not yet connected to production flow
- [ ] Pass active sidebar filters into LLM context
- [ ] AWS S3 integration (remote Parquet reads via DuckDB S3 extension)

---

## Author

Accounting and auditing professional transitioning to analytics engineering.

Years at KPMG auditing financial statements: reconciling ledgers, testing controls, chasing discrepancies through multi-tab Excel workbooks. The financial domain knowledge here — fiscal periods, budget execution phases, economic classification charts, reconciliation controls — is what makes this more than a tutorial project. The engineering side — streaming pipelines, dimensional modeling, LLM integration, data quality automation — is the transition.

**Target roles:** Analytics Engineer · BI Engineer · Financial Data Analyst

> *Replace `#` below with your actual LinkedIn and GitHub URLs before publishing.*

[LinkedIn](#) · [GitHub](#)