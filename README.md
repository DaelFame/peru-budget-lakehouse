# Peru Budget Lakehouse 🇵🇪 🏦

A high-performance, local Data Lakehouse architecture built to process, model, and analyze millions of historical public financial records from the Ministry of Economy and Finance of Peru (MEF). 

This project processes **47+ Million rows** and reconciles **S/. 8.4 Trillion (PEN)** using modern data engineering tools under strict hardware boundaries (4 Cores / 4GB RAM limit), demonstrating advanced memory management and out-of-core computing.

## 🏗️ Architecture Overview

The project follows the **Medallion Architecture** combined with a **Star Schema (Kimball Methodology)** for presentation, optimized entirely via columnar storage (Parquet).

[Bronze Layer (Raw CSVs)]
│
▼ (Hash-Chunking Ingestion & Unpivot)
[Silver Layer (Normalized Parquet)]
│
▼ (Polars Streaming & Surrogate Key Hashing)
[Gold Layer (Star Schema: 5 Dims + 1 Fact Table)]
│
├──► [Automated QA Audit (Financial Reconciliation)]
│
▼ (Virtual SQL Views Mapping)
[DuckDB Analytical Engine (Management Reports)]

### 🏎️ Core Technologies & Design Decisions
* **Polars (LazyFrame & Streaming Engine):** Chosen over Pandas/PySpark for lightning-fast execution and native out-of-core processing, preventing RAM crashes on massive analytical merges.
* **DuckDB:** Utilized as an embedded analytical database engine to query Parquet files directly using vectorized SQL execution with sub-second response times.
* **Apache Parquet (ZSTD Compression):** Used across Silver and Gold layers to ensure high compression ratios and high-performance columnar scanning.

---

## 🚀 Pipeline Evolution: From Notebooks to Production Scripts

The development lifecycle was strategically designed to move from exploratory interactive workflows to automated, resilient python production scripts (`src/`):

1. **`01_silver_ingestion.py` (Bronze ──► Silver):**
   * Enforces a strict 42-column text schema driven by the official MEF dictionary to prevent parsing errors.
   * Implements a **16-batch Hexadecimal Hash-Chunking strategy** to process gigabytes of data incrementally.
   * Performs a dynamic **Unpivot (Melt)** operation over 35 distinct financial columns (PIA, PIM, Certificado, Devengado, Girado from 2022 to 2026), normalizing the schema into a standardized deep dataset.

2. **`02_star_schema.py` (Silver ──► Gold):**
   * Normalizes the denormalized Silver file into a star schema optimized for BI tools (like Power BI).
   * Generates highly efficient **Surrogate Keys** using cryptographic/fast hashing algorithms.
   * Extracts 5 dimension tables (`Geografia`, `Institucion`, `Programatica`, `Economica`, `Financiamiento`) and streams a centralized **Fact Table (`fact_presupuesto`) containing 47,219,640 records** directly to disk.

3. **`03_data_quality_audit.py` (Automated Data Governance & QA):**
   * Acts as a production gatekeeper. It executes two automated data quality checks in **0.46 seconds**:
     * **Financial Reconciliation:** Validates that the sum of all financial phases perfectly matches between Silver and Gold (`S/. 8,448,492,418,465.24`). Tolerates zero leakage.
     * **Volumetric Consistency:** Verifies row counts against business deletion rules.
   * **Fault Tolerance:** If a 1-cent discrepancy is found, it raises a critical `ValueError` and halts the deployment pipeline immediately.

4. **`04_analytical_reports.py` (OLAP Analytical Engine):**
   * Initializes DuckDB allocating a strict hard boundary of 4 threads and 4GB RAM.
   * Maps physical Parquet structures into virtual relational database views without loading data into memory.
   * Generates C-level management reports (Top spending departments, Historical PIM trends, Cross-sector performance) on 47M+ rows in **0.37 seconds**.

---

## 📈 Performance & Execution Logs

```text
2026-05-18 21:35:51 - [INFO] - === STARTING GOLD MODELING PIPELINE (STAR SCHEMA) ===
2026-05-18 21:35:55 - [INFO] - Successfully saved dimension: dim_geografia.parquet
2026-05-18 21:36:00 - [INFO] - Successfully saved dimension: dim_institucion.parquet
2026-05-18 21:36:17 - [INFO] - Successfully saved dimension: dim_programatica.parquet
2026-05-18 21:36:28 - [INFO] - Building central Fact Table...
2026-05-18 21:36:34 - [INFO] - Successfully saved Fact Table: fact_presupuesto.parquet
2026-05-18 21:36:34 - [INFO] - === GOLD MODELING COMPLETED IN 0.71 MINUTES ===

2026-05-18 21:36:35 - [INFO] - === STARTING AUTOMATED DATA QUALITY AUDIT (QA) ===
2026-05-18 21:36:35 - [INFO] - Silver Layer Total Sum : S/. 8,448,492,418,465.24
2026-05-18 21:36:35 - [INFO] - Gold Layer Total Sum   : S/. 8,448,492,418,465.24
2026-05-18 21:36:35 - [INFO] - Total Discrepancy      : S/. 0.00
2026-05-18 21:36:35 - [INFO] - ✅ Data Quality Control 1 passed: Financial amounts are 100% synchronized.
2026-05-18 21:36:35 - [INFO] - Total rows in Silver/Gold layers: 47,219,640
2026-05-18 21:36:35 - [INFO] - ✅ Data Quality Control 2 passed: Row volumetrics comply with business rules.
2026-05-18 21:36:35 - [INFO] - === QA AUDIT PIPELINE COMPLETED SUCCESSFULLY IN 0.46 SECONDS ===

2026-05-18 21:36:35 - [INFO] - === STARTING MANAGEMENT REPORT ANALYTICAL ENGINE ===
2026-05-18 21:36:35 - [INFO] - Executing Analytical Queries over 47M+ rows...
2026-05-18 21:36:36 - [INFO] - === ANALYTICAL REPORT ENGINE RUN COMPLETED IN 0.37 SECONDS ===

🛠️ How to Run
Clone the repository:

Bash
git clone [https://github.com/your-username/peru-budget-lakehouse.git](https://github.com/your-username/peru-budget-lakehouse.git)
cd peru-budget-lakehouse
Execute the production pipeline sequentially:

Bash
python src/01_silver_ingestion.py
python src/02_star_schema.py
python src/03_data_quality_audit.py
python src/04_analytical_reports.py