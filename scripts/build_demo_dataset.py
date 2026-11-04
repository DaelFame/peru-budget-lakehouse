"""
build_demo_dataset.py

Builds the demo Gold layer used by the Streamlit dashboard from a full Gold
star schema.

The sampling unit is the ENTITY - the five surrogate keys that identify one
source row - never the individual fact row. Every fact belonging to a sampled
entity is kept, across years and execution phases.

Row-level sampling destroys the internal consistency of each record: a `pim`
fact can survive while its `devengado` sibling does not. The aggregate then
reports impossible execution rates (devengado > PIM) and meaningless
per-entity ratios. Entity-level sampling keeps every record intact, so the
demo is a valid - if partial - view of the same accounting ledger.

Usage:
    uv run python scripts/build_demo_dataset.py
    uv run python scripts/build_demo_dataset.py --target-rows 450000 \
        --years 2022 2023 2024 2025 --region-share-threshold 50

Outputs:
    data/00_demo/fact_presupuesto.parquet
    data/00_demo/dim_*.parquet
    data/00_demo/manifest.json

Exit code 1 when an acceptance gate fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

GOLD_DIR = Path("data/03_gold")
DEMO_DIR = Path("data/00_demo")

ENTITY_KEYS = [
    "sk_geografia_id",
    "sk_institucion_id",
    "sk_programatica_id",
    "sk_economica_id",
    "sk_financiamiento_id",
]

FACT_COLUMNS = ENTITY_KEYS + ["anio", "fase", "monto"]

DIMENSIONS = {
    "dim_geografia": "sk_geografia_id",
    "dim_institucion": "sk_institucion_id",
    "dim_programatica": "sk_programatica_id",
    "dim_economica": "sk_economica_id",
    "dim_financiamiento": "sk_financiamiento_id",
}

DEFAULT_YEARS = [2022, 2023, 2024, 2025]


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------
def select_entities(entity_sizes: pd.DataFrame, target_rows: int) -> pd.DataFrame:
    """
    Greedy deterministic selection of whole entities until `target_rows` is met.

    `entity_sizes` must carry ENTITY_KEYS plus `n_facts`, sorted by a stable
    key. An entity is either taken with all its facts or not taken at all: the
    function never splits a record. Small entities fill the remainder left by
    large ones, so the result usually hits the target exactly.
    """
    selected = []
    total = 0

    for row in entity_sizes.itertuples(index=False):
        if total == target_rows:
            break
        if total + row.n_facts <= target_rows:
            selected.append(row)
            total += row.n_facts

    chosen = pd.DataFrame(selected, columns=list(entity_sizes.columns))
    return chosen


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------
def execution_rates(facts: pd.DataFrame) -> dict:
    """PIM vs devengado execution rate, globally and per fiscal year."""
    pim = facts[facts["fase"] == "pim"]
    dev = facts[facts["fase"] == "devengado"]

    def rate(pim_value: float, dev_value: float) -> float | None:
        if pim_value == 0:
            return None
        return round(100.0 * dev_value / pim_value, 2)

    global_rate = rate(pim["monto"].sum(), dev["monto"].sum())

    per_year = []
    for year in sorted(facts["anio"].unique()):
        pim_year = pim[pim["anio"] == year]["monto"].sum()
        dev_year = dev[dev["anio"] == year]["monto"].sum()
        per_year.append(
            {
                "anio": int(year),
                "execution_rate_pct": rate(pim_year, dev_year),
                "pim": round(float(pim_year), 2),
                "devengado": round(float(dev_year), 2),
            }
        )

    return {"global_execution_rate_pct": global_rate, "by_year": per_year}


def region_pim_shares(facts: pd.DataFrame, geography: pd.DataFrame) -> list[dict]:
    """Share of total PIM held by each executing-unit department."""
    merged = facts[facts["fase"] == "pim"].merge(geography, on="sk_geografia_id", how="left")
    merged = merged[merged["departamento_ejecutora_nombre"].notna()]

    total = merged["monto"].sum()
    if total == 0:
        return []

    grouped = (
        merged.groupby("departamento_ejecutora_nombre")["monto"]
        .sum()
        .sort_values(ascending=False)
    )
    return [
        {"department": name, "pim": round(float(value), 2), "share_pct": round(100.0 * value / total, 2)}
        for name, value in grouped.items()
    ]


def check_gates(
    facts: pd.DataFrame,
    geography: pd.DataFrame,
    target_rows: int,
    region_share_threshold: float,
    row_tolerance: float,
) -> tuple[list[str], dict]:
    """
    Evaluate every acceptance gate.

    Returns (failures, diagnostics). An empty failure list means the demo
    passes. The only hard integrity criterion is the execution rate: a value
    outside [0, 100] means a record lost its PIM/devengado sibling, which is
    exactly what entity-level sampling exists to prevent.

    Geographic concentration is reported, never enforced. National ministries
    execute in Lima, so PIM concentrates there in the real dataset; that is a
    property of the data, not a defect of the sample.
    """
    failures: list[str] = []
    rates = execution_rates(facts)

    for entry in [{"anio": "global", "execution_rate_pct": rates["global_execution_rate_pct"]}] + rates["by_year"]:
        value = entry["execution_rate_pct"]
        if value is None:
            failures.append(f"Execution rate undefined for {entry['anio']}: no PIM in the sample.")
        elif not 0.0 <= value <= 100.0:
            failures.append(
                f"Execution rate {value}% for {entry['anio']} is outside [0, 100]: "
                "devengado and PIM rows of the same entity were split."
            )

    rows = len(facts)
    if abs(rows - target_rows) > max(1, int(target_rows * row_tolerance)):
        failures.append(
            f"Demo holds {rows:,} rows against a target of {target_rows:,} "
            f"(tolerance {row_tolerance:.1%})."
        )

    for column in FACT_COLUMNS:
        nulls = int(facts[column].isna().sum())
        if nulls:
            failures.append(f"Column '{column}' has {nulls:,} null values.")

    shares = region_pim_shares(facts, geography)
    concentration_note = None
    if shares and shares[0]["share_pct"] > region_share_threshold:
        concentration_note = (
            f"{shares[0]['department']} holds {shares[0]['share_pct']}% of PIM "
            f"(reported, not enforced: national ministries execute in Lima)."
        )

    diagnostics = {
        "execution_rates": rates,
        "top_region_pim_share": shares[:5],
        "region_concentration_note": concentration_note,
    }
    return failures, diagnostics


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def _entity_sizes(con: duckdb.DuckDBPyConnection, years: list[int]) -> pd.DataFrame:
    year_list = ",".join(str(y) for y in years)
    keys = ", ".join(ENTITY_KEYS)
    query = f"""
        SELECT {keys}, COUNT(*) AS n_facts
        FROM read_parquet('{GOLD_DIR / "fact_presupuesto.parquet"}')
        WHERE anio IN ({year_list})
        GROUP BY {keys}
        ORDER BY md5(concat_ws('|', {', '.join(f'CAST({k} AS VARCHAR)' for k in ENTITY_KEYS)}))
    """
    return con.execute(query).df()


def build(target_rows: int, years: list[int]) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    con = duckdb.connect()
    fact_path = GOLD_DIR / "fact_presupuesto.parquet"
    if not fact_path.exists():
        raise FileNotFoundError(
            f"Gold fact table not found: {fact_path}. Run the pipeline first (uv run python main.py)."
        )

    print(f"Gold fact table: {fact_path}")
    sizes = _entity_sizes(con, years)
    print(f"Entities available ({years[0]}-{years[-1]}): {len(sizes):,}")

    chosen = select_entities(sizes, target_rows)
    print(f"Entities selected: {len(chosen):,}")

    year_list = ",".join(str(y) for y in years)
    con.register("selected_entities", chosen[ENTITY_KEYS])

    fact = con.execute(
        f"SELECT {', '.join('f.' + c for c in FACT_COLUMNS)} "
        f"FROM read_parquet('{fact_path}') f "
        f"WHERE f.anio IN ({year_list}) "
        f"  AND EXISTS (SELECT 1 FROM selected_entities s WHERE "
        + " AND ".join(f"s.{k} = f.{k}" for k in ENTITY_KEYS)
        + ")"
    ).df()
    print(f"Facts sampled: {len(fact):,}")

    # Integrity invariant: every selected entity keeps all of its facts.
    observed = fact.groupby(ENTITY_KEYS, sort=False)["monto"].size().rename("observed")
    expected = chosen.set_index(ENTITY_KEYS)["n_facts"]
    mismatch = (observed.reindex(expected.index) != expected).sum()
    if mismatch:
        raise RuntimeError(
            f"{mismatch:,} entities lost facts during sampling. Entity-level sampling is broken."
        )

    dims = {}
    for table, key in DIMENSIONS.items():
        source = GOLD_DIR / f"{table}.parquet"
        if not source.exists():
            raise FileNotFoundError(f"Gold dimension not found: {source}")
        dims[table] = con.execute(
            f"SELECT d.* FROM read_parquet('{source}') d "
            f"JOIN (SELECT DISTINCT {key} FROM selected_entities) s USING ({key})"
        ).df()
        print(f"{table}: {len(dims[table]):,} rows")

    con.close()
    return fact, dims, chosen


def write(fact: pd.DataFrame, dims: dict, manifest: dict) -> None:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    fact.to_parquet(DEMO_DIR / "fact_presupuesto.parquet", index=False)
    for table, frame in dims.items():
        frame.to_parquet(DEMO_DIR / f"{table}.parquet", index=False)
    (DEMO_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the demo Gold layer.")
    parser.add_argument("--target-rows", type=int, default=450_000)
    parser.add_argument("--years", type=int, nargs="+", default=DEFAULT_YEARS)
    parser.add_argument("--region-share-threshold", type=float, default=50.0)
    parser.add_argument("--row-tolerance", type=float, default=0.001)
    parser.add_argument("--skip-gates", action="store_true", help="Write the demo even if a gate fails.")
    args = parser.parse_args()

    fact, dims, chosen = build(args.target_rows, args.years)
    failures, diagnostics = check_gates(
        fact,
        dims["dim_geografia"],
        target_rows=args.target_rows,
        region_share_threshold=args.region_share_threshold,
        row_tolerance=args.row_tolerance,
    )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target_rows": args.target_rows,
        "fact_rows": len(fact),
        "entities": int(len(chosen)),
        "years": args.years,
        "dimension_rows": {table: len(frame) for table, frame in dims.items()},
        "gates": {"passed": not failures, "failures": failures},
        "diagnostics": diagnostics,
    }

    print("\n=== VALIDATION ===")
    print(f"Fact rows        : {len(fact):,}")
    print(f"Entities         : {manifest['entities']:,}")
    print(f"Execution (all)  : {diagnostics['execution_rates']['global_execution_rate_pct']}%")
    for entry in diagnostics["execution_rates"]["by_year"]:
        print(f"  {entry['anio']}: PIM {entry['pim'] / 1e9:,.2f}bn  devengado {entry['devengado'] / 1e9:,.2f}bn  "
              f"-> {entry['execution_rate_pct']}%")
    for entry in diagnostics["top_region_pim_share"]:
        print(f"  PIM {entry['department']}: {entry['share_pct']}%")
    if diagnostics["region_concentration_note"]:
        print(f"  NOTE: {diagnostics['region_concentration_note']}")

    if failures:
        print("\nGATES FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        if not args.skip_gates:
            print("\nNo files written. Fix the sample or re-run with --skip-gates.")
            return 1

    write(fact, dims, manifest)
    print(f"\nDemo written to {DEMO_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
