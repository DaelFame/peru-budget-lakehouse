import duckdb
import logging
import shutil
from pathlib import Path
from config import SILVER_DIR

# =========================
# CONFIG
# =========================
INPUT   = SILVER_DIR / "step1_clean.parquet"
TMP_DIR = SILVER_DIR / "00_tmp_unpivot"
OUTPUT  = SILVER_DIR / "step2_long.parquet"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s"
)

# ORDEN IMPORTA: comprometido_anual antes que comprometido
METRICS = [
    "pia",
    "pim",
    "certificado",
    "comprometido_anual",
    "comprometido",
    "devengado",
    "girado",
]

# =========================
# HELPERS
# =========================
def get_columns(con: duckdb.DuckDBPyConnection) -> tuple[list[str], list[str]]:
    cols = con.execute(f"""
        SELECT column_name
        FROM (DESCRIBE SELECT * FROM read_parquet('{INPUT}'))
    """).fetchall()
    cols = [c[0] for c in cols]

    metric_cols, id_cols = [], []
    for c in cols:
        if any(c == m or c.startswith(m + "_") for m in METRICS):
            metric_cols.append(c)
        else:
            id_cols.append(c)

    return id_cols, metric_cols


def build_unpivot_query(
    input_path: Path,
    out_path: Path,
    id_cols: list[str],
    col_list_sql: str,
) -> str:
    id_cols_sql = ", ".join(id_cols)
    return f"""
    COPY (
        SELECT
            {id_cols_sql},
            value                                                                    AS monto,
            CAST(regexp_extract(col_name, '\\d{{4}}') AS INTEGER)                   AS anio,
            regexp_replace(regexp_extract(col_name, '^[a-zA-Z_]+'), '_$', '')       AS fase
        FROM read_parquet('{input_path}')
        UNPIVOT (
            value FOR col_name IN ({col_list_sql})
        )
        WHERE value IS NOT NULL
          AND value <> 0
    )
    TO '{out_path}'
    (FORMAT PARQUET, COMPRESSION ZSTD);
    """


# =========================
# RUN
# =========================
def run():
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("PRAGMA threads=16")
    con.execute("PRAGMA memory_limit='10GB'")
    con.execute(f"PRAGMA temp_directory='{TMP_DIR}'")

    logging.info("DuckDB threads=16, memory=10GB")

    id_cols, metric_cols = get_columns(con)
    logging.info(f"ID cols:     {len(id_cols)}")
    logging.info(f"Metric cols: {len(metric_cols)}")

    # =========================
    # UNPIVOT POR MÉTRICA
    # =========================
    for metric in METRICS:
        cols = [c for c in metric_cols if c == metric or c.startswith(metric + "_")]

        if not cols:
            logging.warning(f"Sin columnas para metric={metric!r} — skipping")
            continue

        out_path     = TMP_DIR / f"{metric}.parquet"
        col_list_sql = ", ".join(cols)

        logging.info(f"Procesando metric={metric!r:25s} ncols={len(cols)}")
        con.execute(build_unpivot_query(INPUT, out_path, id_cols, col_list_sql))
        logging.info(f"  → {out_path.name}")

    # =========================
    # MERGE FINAL
    # =========================
    logging.info("Merge final...")
    con.execute(f"""
    COPY (
        SELECT * FROM read_parquet('{TMP_DIR}/*.parquet')
    )
    TO '{OUTPUT}'
    (FORMAT PARQUET, COMPRESSION ZSTD);
    """)
    logging.info(f"OUTPUT → {OUTPUT}")

    # =========================
    # CLEANUP
    # =========================
    con.close()
    shutil.rmtree(TMP_DIR)
    logging.info("TMP limpiado")


if __name__ == "__main__":
    run()