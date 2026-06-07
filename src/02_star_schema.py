import time
import logging
import polars as pl
from config import FINAL_SILVER_PATH, GOLD_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

DIMENSIONS_CONFIG = {
    "geografia": {
        "columns": [
            "departamento_ejecutora", "departamento_ejecutora_nombre",
            "provincia_ejecutora",    "provincia_ejecutora_nombre",
            "distrito_ejecutora",     "distrito_ejecutora_nombre"
        ],
        "hash_keys":       ["departamento_ejecutora", "provincia_ejecutora", "distrito_ejecutora"],
        "not_null_filter": "departamento_ejecutora",
        "pk_name":         "sk_geografia_id"
    },
    "institucion": {
        "columns": [
            "nivel_gobierno", "nivel_gobierno_nombre",
            "sector",         "sector_nombre",
            "pliego",         "pliego_nombre",
            "sec_ejec",       "ejecutora", "ejecutora_nombre"
        ],
        # sec_ejec agregado como tiebreaker para municipalidades donde pliego=None
        # ignore_nulls=True en concat_str evita que un None colapse todo el hash
        "hash_keys":       ["nivel_gobierno", "sector", "pliego", "sec_ejec"],
        "not_null_filter": "nivel_gobierno",
        "pk_name":         "sk_institucion_id"
    },
    "programatica": {
        "columns": [
            "programa_ppto",         "programa_ppto_nombre",
            "tipo_act_proy",         "tipo_act_proy_nombre",
            "producto_proyecto",     "producto_proyecto_nombre",
            "actividad_accion_obra", "actividad_accion_obra_nombre",
            "funcion",               "funcion_nombre",
            "division_funcional",    "division_funcional_nombre",
            "grupo_funcional",       "grupo_funcional_nombre",
            "meta",                  "meta_nombre"
        ],
        "hash_keys": [
            "programa_ppto", "producto_proyecto", "actividad_accion_obra",
            "funcion", "division_funcional", "grupo_funcional", "meta"
        ],
        "not_null_filter": "programa_ppto",
        "pk_name":         "sk_programatica_id"
    },
    "economica": {
        "columns": [
            "tipo_transaccion",
            "generica",        "generica_nombre",
            "subgenerica",     "subgenerica_nombre",
            "subgenerica_det", "subgenerica_det_nombre",
            "especifica",      "especifica_nombre",
            "especifica_det",  "especifica_det_nombre"
        ],
        "hash_keys": [
            "tipo_transaccion", "generica", "subgenerica",
            "subgenerica_det",  "especifica", "especifica_det"
        ],
        "not_null_filter": "tipo_transaccion",
        "pk_name":         "sk_economica_id"
    },
    "financiamiento": {
        "columns": [
            "fuente_financiamiento", "fuente_financiamiento_nombre",
            "rubro",                 "rubro_nombre",
            "tipo_recurso",          "tipo_recurso_nombre",
            "categoria_gasto",       "categoria_gasto_nombre"
        ],
        "hash_keys":       ["fuente_financiamiento", "rubro", "tipo_recurso", "categoria_gasto"],
        "not_null_filter": "fuente_financiamiento",
        "pk_name":         "sk_financiamiento_id"
    }
}

def process_dimensions(lazy_silver: pl.LazyFrame):
    """
    Extracts and writes each dimension table to Parquet using Polars Streaming.
    The critical fix is ignore_nulls=True in concat_str — without this, any None field 
    in hash_keys (e.g., pliego=None in municipalities) collapses the entire 
    concat to null, producing the same SK for thousands of different entities.
    """
    logging.info("Extracting Dimension Tables via Polars Streaming...")

    for dim_name, config in DIMENSIONS_CONFIG.items():
        logging.info(f"Processing Dimension Table: {dim_name.upper()}")
        output_path = GOLD_DIR / f"dim_{dim_name}.parquet"

        req_columns = config["columns"]
        hash_keys   = config["hash_keys"]
        pk          = config["pk_name"]
        filter_col  = config["not_null_filter"]

        dim_lazy = (
            lazy_silver
            .select(req_columns)
            .filter(pl.col(filter_col).is_not_null())
            .unique(maintain_order=False)
            .with_columns(
                # ignore_nulls=True: None fields are omitted from the concat 
                # instead of collapsing the entire expression to null 
                # → unique hashes per row
                pl.concat_str(
                    [pl.col(c) for c in hash_keys],
                    separator="_",
                    ignore_nulls=True
                )
                .hash()
                .alias(pk)
            )
            .unique(subset=[pk], maintain_order=False)  # <--- HERE: Uniqueness filter by key
            .select([pk] + req_columns)
        )

        dim_lazy.sink_parquet(output_path, compression="zstd")
        logging.info(f"Saved: {output_path.name}")


def process_fact_table(lazy_silver: pl.LazyFrame):
    """
    Construye la fact table asignando surrogate keys on-the-fly con el mismo
    hash que las dimensiones. ignore_nulls=True garantiza que la SK del fact
    matchee exactamente con la SK de la dimensión correspondiente.
    """
    logging.info("Building central Fact Table...")
    output_path = GOLD_DIR / "fact_presupuesto.parquet"

    fact_lazy = lazy_silver.with_columns(
        *[
            pl.concat_str(
                [pl.col(c) for c in config["hash_keys"]],
                separator="_",
                ignore_nulls=True   # mismo comportamiento que en las dimensiones
            )
            .hash()
            .alias(config["pk_name"])
            for config in DIMENSIONS_CONFIG.values()
        ]
    )

    fact_columns = (
        [config["pk_name"] for config in DIMENSIONS_CONFIG.values()]
        + ["anio", "fase", "monto"]
    )

    fact_lazy = (
        fact_lazy
        .select(fact_columns)
        .filter(pl.col("monto").is_not_null())
    )

    logging.info("Streaming Fact Table to disk...")
    fact_lazy.sink_parquet(output_path, compression="zstd")
    logging.info(f"Saved: {output_path.name}")


def main():
    start_time = time.time()
    logging.info("=== STARTING GOLD MODELING PIPELINE (STAR SCHEMA) ===")

    if not FINAL_SILVER_PATH.exists():
        logging.error(f"Silver source not found: {FINAL_SILVER_PATH}")
        return

    lazy_silver = pl.scan_parquet(FINAL_SILVER_PATH)

    # Sanitización de municipalidades: sector y sector_nombre vacíos/null
    # reciben etiquetas de negocio estándar para que el hash sea consistente
    lazy_silver = lazy_silver.with_columns([
        pl.when(
            pl.col("sector_nombre").is_null() |
            (pl.col("sector_nombre").str.strip_chars() == "")
        )
        .then(pl.lit("gobiernos locales (municipalidades)"))
        .otherwise(pl.col("sector_nombre"))
        .alias("sector_nombre"),

        pl.when(
            pl.col("sector").is_null() |
            (pl.col("sector").str.strip_chars() == "")
        )
        .then(pl.lit("gl"))
        .otherwise(pl.col("sector"))
        .alias("sector")
    ])

    process_dimensions(lazy_silver)
    process_fact_table(lazy_silver)

    duration = (time.time() - start_time) / 60
    logging.info(f"=== GOLD COMPLETED IN {duration:.2f} MINUTES ===")


if __name__ == "__main__":
    main()