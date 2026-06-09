"""
peru-budget-lakehouse | Prefect Orchestration Entry Point
=========================================================
Medallion pipeline: Bronze → Silver (clean + unpivot) → Gold → QA → Reports

Execution:
    uv run python main.py

Requirements:
    - Source CSV must exist at data/01_bronze/comparativo_gastos_2022_2026.csv
    - polars-hash must be installed: uv add polars-hash
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from prefect import flow, task, get_run_logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SRC_DIR = Path(__file__).parent / "src"

SCRIPTS = {
    "bronze":  "etl_01_bronze_ingestion.py",
    "silver":  "etl_02_silver_cleaning.py",
    "unpivot": "etl_03_silver_unpivot.py",
    "gold":    "etl_04_star_schema.py",
    "qa":      "etl_05_data_quality_audit.py",
    "reports": "etl_06_analytical_reports.py",
}

# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------
def _run_script(script_name: str, logger) -> dict:
    import subprocess

    script_path = SRC_DIR / script_name

    if not script_path.exists():
        available = [p.name for p in SRC_DIR.glob("*.py")]
        raise FileNotFoundError(
            f"Script not found: {script_path}\nAvailable: {available}"
        )

    logger.info(f"Starting: {script_name}")
    t0 = time.perf_counter()

    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent  # always PROJECT_ROOT, never CWD-relative
    )

    duration_s = round(time.perf_counter() - t0, 2)

    if result.returncode != 0:
        logger.error(f"FAILED: {script_name}\n{result.stderr[-2000:]}")
        raise RuntimeError(
            f"Exit code {result.returncode}: {script_name}\n{result.stderr[-2000:]}"
        )

    if result.stdout:
        logger.info(f"[{script_name}] stdout:\n{result.stdout[-1000:]}")

    logger.info(f"Completed: {script_name} in {duration_s}s")

    return {
        "script":       script_name,
        "status":       "success",
        "duration_s":   duration_s,
        "completed_at": datetime.now(timezone.utc).isoformat()
    }


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
@task(name="bronze-ingestion", retries=1, retry_delay_seconds=10)
def bronze() -> dict:
    """Ingest raw MEF CSV → Bronze Parquet (ZSTD). ~54M rows source."""
    return _run_script(SCRIPTS["bronze"], get_run_logger())


@task(name="silver-cleaning", retries=1, retry_delay_seconds=10)
def silver() -> dict:
    """Type casting, null handling, column normalization → Silver Parquet."""
    return _run_script(SCRIPTS["silver"], get_run_logger())


@task(name="silver-unpivot", retries=1, retry_delay_seconds=10)
def unpivot() -> dict:
    """DuckDB UNPIVOT: wide → long format (fase/monto). OOM-safe."""
    return _run_script(SCRIPTS["unpivot"], get_run_logger())


@task(name="gold-star-schema", retries=0)
def gold() -> dict:
    """Polars streaming star schema: 1 fact + 5 dims. Surrogate keys via wyhash."""
    return _run_script(SCRIPTS["gold"], get_run_logger())


@task(name="data-quality-audit", retries=0)
def qa() -> dict:
    """Gate 1: financial reconciliation (S/. 0.01 tolerance). Gate 2: row volumetrics."""
    return _run_script(SCRIPTS["qa"], get_run_logger())


@task(name="analytical-reports", retries=0)
def reports() -> dict:
    """DuckDB in-memory: 4 executive SQL reports over Gold Parquet views."""
    return _run_script(SCRIPTS["reports"], get_run_logger())


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------
@flow(
    name="peru-budget-lakehouse",
    description="MEF budget execution pipeline: Bronze → Silver → Gold → QA → Reports",
    log_prints=True
)
def pipeline() -> dict:
    """
    Sequential medallion pipeline with explicit Prefect dependencies.
    wait_for= enforces execution order — Prefect cannot parallelize or
    reorder stages regardless of scheduling configuration.
    """
    run_id  = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    t_start = time.perf_counter()

    print("=" * 60)
    print(f"  peru-budget-lakehouse")
    print(f"  Run ID  : {run_id}")
    print(f"  Started : {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    b = bronze()
    s = silver(wait_for=[b])
    u = unpivot(wait_for=[s])
    g = gold(wait_for=[u])
    q = qa(wait_for=[g])
    r = reports(wait_for=[q])

    total_s = round(time.perf_counter() - t_start, 2)

    results = {
        "run_id":    run_id,
        "status":    "success",
        "total_s":   total_s,
        "total_min": round(total_s / 60, 2),
        "stages": {
            "bronze":  b,
            "silver":  s,
            "unpivot": u,
            "gold":    g,
            "qa":      q,
            "reports": r,
        }
    }

    print(f"\n{'=' * 60}")
    print(f"  PIPELINE COMPLETED in {total_s:.2f}s ({total_s/60:.2f} min)")
    for stage, meta in results["stages"].items():
        print(f"  {stage:<10}: {meta['duration_s']}s")
    print(f"{'=' * 60}\n")

    return results


if __name__ == "__main__":
    pipeline()