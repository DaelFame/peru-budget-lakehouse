import polars as pl
import unicodedata
import re
from config import BRONZE_DIR, SILVER_DIR

METRIC_KEYWORDS = {
    "pia", "pim", "certificado",
    "comprometido", "devengado", "girado"
}

# ----------------------------
# NORMALIZATION
# ----------------------------
def normalize_colname(name: str) -> str:
    name = name.lower()
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^a-z0-9_]", "", name)
    return name


def is_metric(col: str) -> bool:
    return any(k in col for k in METRIC_KEYWORDS)


# ----------------------------
# SILVER PIPELINE
# ----------------------------
def run():

    input_path = BRONZE_DIR / "bronze_data.parquet"
    output_path = SILVER_DIR / "step1_clean.parquet"

    lf = pl.scan_parquet(input_path)

    # 1. rename
    schema_cols = lf.collect_schema().names()
    rename_map = {c: normalize_colname(c) for c in schema_cols}
    lf = lf.rename(rename_map)

    cols = lf.collect_schema().names()

    metric_cols = [c for c in cols if is_metric(c)]
    dim_cols = [c for c in cols if c not in metric_cols]

    # 2. expressions
    exprs = []

    # métricas → float
    exprs += [
        pl.col(c).cast(pl.Float64, strict=False)
        for c in metric_cols
    ]

    # dimensiones → STRING MAYÚSCULAS
    exprs += [
        pl.col(c)
        .cast(pl.Utf8, strict=False)
        .str.strip_chars()
        .str.to_uppercase()
        for c in dim_cols
    ]

    lf = lf.with_columns(exprs)

    # 3. write streaming
    lf.sink_parquet(
        output_path,
        compression="zstd"
    )

    print(f"[OK] SILVER WRITTEN → {output_path}")


if __name__ == "__main__":
    run()