import subprocess
import sys
import json
from pathlib import Path
import os
import math

import polars as pl


# =========================================================
# PROJECT PATHS
# =========================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"

sys.path.insert(0, str(SRC_DIR))

from config import FINAL_SILVER_PATH, GOLD_FACT_PATH


# =========================================================
# OUTPUT SNAPSHOTS
# =========================================================
RUN_A_PATH = PROJECT_ROOT / "run_a.json"
RUN_B_PATH = PROJECT_ROOT / "run_b.json"


# =========================================================
# PIPELINE EXECUTION
# =========================================================
def run_pipeline():
    scripts = [
        "etl_01_bronze_ingestion.py",
        "etl_02_silver_cleaning.py",
        "etl_03_silver_unpivot.py",
        "etl_04_star_schema.py",
        "etl_05_data_quality_audit.py",
        "etl_06_analytical_reports.py",
    ]

    for script in scripts:
        script_path = SRC_DIR / script

        print(f"\n▶ Running {script}")

        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            env={**os.environ},
        )

        if result.returncode != 0:
            print(result.stderr)
            raise RuntimeError(f"PIPELINE FAILED AT {script}")

    return True


# =========================================================
# SNAPSHOT BUILDER (DETERMINISTIC ONLY)
# =========================================================
def build_snapshot():
    silver = pl.scan_parquet(FINAL_SILVER_PATH)
    fact = pl.scan_parquet(GOLD_FACT_PATH)

    return {
        "silver_exists": FINAL_SILVER_PATH.exists(),
        "fact_exists": GOLD_FACT_PATH.exists(),

        # ROWS (lazy)
        "silver_rows": silver.select(pl.len()).collect().item(),
        "fact_rows": fact.select(pl.len()).collect().item(),

        # SCHEMA (metadata only)
        "schema_silver": sorted(silver.collect_schema().names()),
        "schema_fact": sorted(fact.collect_schema().names()),

        # SUM (lazy aggregation, NO full collect)
        "silver_sum_monto": float(
            silver.select(pl.col("monto").sum()).collect().item()
        ),
        "fact_sum_monto": float(
            fact.select(pl.col("monto").sum()).collect().item()
        ),
    }


# =========================================================
# EXECUTION
# =========================================================
def execute_run(path: Path):
    print(f"\n🚀 EXECUTING PIPELINE → {path.name}")

    run_pipeline()
    snapshot = build_snapshot()

    path.write_text(json.dumps(snapshot, indent=2))

    return snapshot


# =========================================================
# DIFFERENTIAL ENGINE (FIXED)
# =========================================================
def compare(a, b):
    print("\n============================")
    print("🧪 DATA DIFFERENTIAL ENGINE")
    print("============================\n")

    # 1. EXACT COMPARISON
    checks_exact = [
        ("schema_silver", "❌ SILVER SCHEMA DRIFT"),
        ("schema_fact", "❌ FACT SCHEMA DRIFT"),
        ("silver_rows", "❌ SILVER ROW DRIFT"),
        ("fact_rows", "❌ FACT ROW DRIFT"),
    ]

    for key, msg in checks_exact:
        if a[key] != b[key]:
            print(f"\n{msg}")
            print(f"RUN A: {a[key]}")
            print(f"RUN B: {b[key]}")
            raise RuntimeError("PIPELINE IS NOT DETERMINISTIC")

    # 2. FLOAT COMPARISON
    checks_float = [
        ("silver_sum_monto", "❌ SILVER MONETARY DRIFT"),
        ("fact_sum_monto", "❌ FACT MONETARY DRIFT"),
    ]

    for key, msg in checks_float:
        if not math.isclose(a[key], b[key], abs_tol=0.01):
            print(f"\n{msg}")
            print(f"RUN A: {a[key]}")
            print(f"RUN B: {b[key]}")
            raise RuntimeError("PIPELINE IS NOT DETERMINISTIC")

    print("✅ NO DRIFT DETECTED")
    print("PIPELINE IS FULLY DETERMINISTIC")
# =========================================================
# MAIN
# =========================================================
if __name__ == "__main__":
    a = execute_run(RUN_A_PATH)

    print("\n====================================\n")

    b = execute_run(RUN_B_PATH)

    compare(a, b)