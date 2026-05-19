import time
import logging
import polars as pl
from config import FINAL_SILVER_PATH, GOLD_DIR

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

# Declarative metadata setup for Star Schema generation
DIMENSIONS_CONFIG = {
    "geografia": {
        "columns": [
            "departamento_ejecutora", "departamento_ejecutora_nombre",
            "provincia_ejecutora", "provincia_ejecutora_nombre",
            "distrito_ejecutora", "distrito_ejecutora_nombre"
        ],
        "hash_keys": ["departamento_ejecutora", "provincia_ejecutora", "distrito_ejecutora"],
        "not_null_filter": "departamento_ejecutora",
        "pk_name": "sk_geografia_id"
    },
    "institucion": {
        "columns": [
            "nivel_gobierno", "nivel_gobierno_nombre", "sector", "sector_nombre",
            "pliego", "pliego_nombre", "sec_ejec", "ejecutora", "ejecutora_nombre"
        ],
        "hash_keys": ["nivel_gobierno", "sector", "pliego", "sec_ejec"],
        "not_null_filter": "nivel_gobierno",
        "pk_name": "sk_institucion_id"
    },
    "programatica": {
        "columns": [
            "programa_ppto", "programa_ppto_nombre", "tipo_act_proy", "tipo_act_proy_nombre",
            "producto_proyecto", "producto_proyecto_nombre", "actividad_accion_obra", "actividad_accion_obra_nombre",
            "funcion", "funcion_nombre", "division_funcional", "division_funcional_nombre",
            "grupo_funcional", "grupo_funcional_nombre", "meta", "meta_nombre"
        ],
        "hash_keys": [
            "programa_ppto", "producto_proyecto", "actividad_accion_obra",
            "funcion", "division_funcional", "grupo_funcional", "meta"
        ],
        "not_null_filter": "programa_ppto",
        "pk_name": "sk_programatica_id"
    },
    "economica": {
        "columns": [
            "tipo_transaccion", "generica", "generica_nombre", "subgenerica", "subgenerica_nombre",
            "subgenerica_det", "subgenerica_det_nombre", "especifica", "especifica_nombre",
            "especifica_det", "especifica_det_nombre"
        ],
        "hash_keys": [
            "tipo_transaccion", "generica", "subgenerica",
            "subgenerica_det", "especifica", "especifica_det"
        ],
        "not_null_filter": "tipo_transaccion",
        "pk_name": "sk_economica_id"
    },
    "financiamiento": {
        "columns": [
            "fuente_financiamiento", "fuente_financiamiento_nombre", "rubro", "rubro_nombre",
            "tipo_recurso", "tipo_recurso_nombre", "categoria_gasto", "categoria_gasto_nombre"
        ],
        "hash_keys": ["fuente_financiamiento", "rubro", "tipo_recurso", "categoria_gasto"],
        "not_null_filter": "fuente_financiamiento",
        "pk_name": "sk_financiamiento_id"
    }
}

def process_dimensions(lazy_silver: pl.LazyFrame):
    """Iterates through configuration to extract and save dimension tables using pure Streaming."""
    logging.info("Extracting Dimension Tables via Polars Streaming...")
    
    for dim_name, config in DIMENSIONS_CONFIG.items():
        logging.info(f"Processing Dimension Table: {dim_name.upper()}")
        output_path = GOLD_DIR / f"dim_{dim_name}.parquet"
        
        req_columns = config["columns"]
        hash_keys = config["hash_keys"]
        pk = config["pk_name"]
        filter_col = config["not_null_filter"]
        
        dim_lazy = (
            lazy_silver
            .select(req_columns)
            .filter(pl.col(filter_col).is_not_null())
            .unique(maintain_order=False)
            .with_columns(
                pl.concat_str([pl.col(c) for c in hash_keys], separator="_")
                .hash()
                .alias(pk)
            )
            .select([pk] + req_columns)
        )
        
        dim_lazy.sink_parquet(output_path, compression="zstd")
        logging.info(f"Successfully saved dimension: {output_path.name}")

def process_fact_table(lazy_silver: pl.LazyFrame):
    """Builds the central Fact Table computing surrogate foreign keys on-the-fly."""
    logging.info("Building central Fact Table...")
    output_path = GOLD_DIR / "fact_presupuesto.parquet"
    
    # Dynamic surrogate keys assignment using list comprehension
    fact_lazy = lazy_silver.with_columns(
        *[
            pl.concat_str([pl.col(c) for c in config["hash_keys"]], separator="_")
            .hash()
            .alias(config["pk_name"])
            for config in DIMENSIONS_CONFIG.values()
        ]
    )
    
    fact_columns = [config["pk_name"] for config in DIMENSIONS_CONFIG.values()] + ["ano_eje", "fase", "monto"]
    
    fact_lazy = (
        fact_lazy
        .select(fact_columns)
        .filter(pl.col("monto").is_not_null())
    )
    
    logging.info("Streaming Fact Table directly to disk (this might take a few minutes)...")
    fact_lazy.sink_parquet(output_path, compression="zstd")
    logging.info(f"Successfully saved Fact Table: {output_path.name}")

def main():
    start_time = time.time()
    logging.info("=== STARTING GOLD MODELING PIPELINE (STAR SCHEMA) ===")
    
    if not FINAL_SILVER_PATH.exists():
        logging.error(f"Silver source file not found at {FINAL_SILVER_PATH}. Please run script 01 first.")
        return
        
    lazy_silver = pl.scan_parquet(FINAL_SILVER_PATH)
    
    process_dimensions(lazy_silver)
    process_fact_table(lazy_silver)
    
    duration = (time.time() - start_time) / 60
    logging.info(f"=== GOLD MODELING COMPLETED IN {duration:.2f} MINUTES ===")

if __name__ == "__main__":
    main()