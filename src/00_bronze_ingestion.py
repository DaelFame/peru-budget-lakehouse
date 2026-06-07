import polars as pl
from config import BRONZE_DIR


def ingest_csv_to_bronze(csv_file: str, output_file: str):
    csv_path = BRONZE_DIR / csv_file
    out_path = BRONZE_DIR / output_file

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    print(f"[BRONZE INGEST] Streaming: {csv_path}")

    # 🔥 NO carga en RAM
    lf = pl.scan_csv(csv_path)

    # limpieza mínima (lazy)
    lf = lf.rename(lambda c: c.strip())

    # 🔥 escritura streaming (clave anti-OOM)
    lf.sink_parquet(out_path, compression="zstd")

    print(f"[BRONZE INGEST] Saved parquet: {out_path}")

    return out_path


if __name__ == "__main__":
    ingest_csv_to_bronze(
        "comparativo_gastos_2022_2026.csv",
        "bronze_data.parquet"
    )