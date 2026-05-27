import time
import re
import gc
import logging
import polars as pl
import polars.selectors as cs
from config import (
    BRONZE_DIR, 
    DICTIONARY_PATH, 
    FINAL_SILVER_PATH, 
    INTERMEDIATE_SILVER_PATH,
    TMP_CONSOLIDATED_DIR, 
    TMP_UNPIVOT_DIR
)

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

def load_secure_schema() -> dict:
    """Reads the MEF data dictionary to enforce text format on descriptive columns,
    then discovers all financial _YYYY columns from the CSV header and forces them as Float64
    to prevent Null-type inference on current fiscal year columns with sparse data."""
    logging.info("Reading MEF variable schema dictionary...")
    try:
        df_dict = pl.read_csv(DICTIONARY_PATH)
        text_columns = (
            df_dict.filter(pl.col("TIPO_DATO").str.strip_chars() == "Carácter")
            .select("VARIABLE").to_series().to_list()
        )
        schema_overrides = {col: pl.String for col in text_columns}
        logging.info(f"Secure schema loaded: Enforcing String type on {len(schema_overrides)} columns.")
    except Exception as e:
        logging.error(f"Fatal error loading schema dictionary: {e}")
        raise

    # ----------------------------------------------------------------
    # STRUCTURAL HEADER DISCOVERY: Force Float64 on all financial _YYYY
    # columns to prevent Null-type inference on sparse current-year data
    # ----------------------------------------------------------------
    csv_files = list(BRONZE_DIR.glob("*.csv"))
    if not csv_files:
        logging.error("No CSV files found in BRONZE_DIR. Cannot discover financial columns.")
        raise FileNotFoundError(f"No CSV files found in {BRONZE_DIR}")
    archivo_gigante = csv_files[0]
    logging.info(f"Discovered monolithic CSV for header scan: {archivo_gigante.name}")

    # Read ONLY the first row to extract all column names without loading data into memory
    df_header = pl.read_csv(archivo_gigante, n_rows=1)
    all_csv_columns = df_header.columns

    # Identify every column whose name ends with a _YYYY year suffix
    financial_pattern = re.compile(r'_\d{4}$')
    financial_columns_found = [col for col in all_csv_columns if financial_pattern.search(col)]

    # Inject explicit Float64 overrides for both original and lowercased column names
    financial_override_count = 0
    for col in financial_columns_found:
        schema_overrides[col] = pl.Float64
        schema_overrides[col.lower()] = pl.Float64
        financial_override_count += 1

    logging.info(
        f"Financial column override complete: {financial_override_count} _YYYY columns "
        f"strictly forced to Float64 (total schema overrides: {len(schema_overrides)})."
    )
    return schema_overrides

def consolidate_by_hash_chunking(schema_overrides: dict):
    """Processes the Bronze layer using 16 hexadecimal hash chunks to prevent Out-Of-Memory (OOM) crashes."""
    hash_chars = [str(i) for i in range(10)] + ["a", "b", "c", "d", "e", "f"]
    logging.info("Starting Hash-Chunking Consolidation Phase (16 batches)...")
    
    # Resolve the explicit path to the single monolithic CSV file
    archivo_gigante = list(BRONZE_DIR.glob("*.csv"))[0]
    logging.info(f"Using explicit CSV path for scan: {archivo_gigante.name}")
    
    for char in hash_chars:
        logging.info(f"Processing batch for keys starting with: '{char}'...")
        
        lazy_mef = pl.scan_csv(
            archivo_gigante, 
            separator=",", 
            schema_overrides=schema_overrides,
            ignore_errors=True
        )
        
        cols = lazy_mef.collect_schema().names()
        lazy_chunk = (
            lazy_mef
            .rename({c: c.lower() for c in cols})
            .filter(pl.col("key_value").str.to_lowercase().str.starts_with(char))
        )
        
        # Text cleaning and sanitization
        lazy_clean = lazy_chunk.with_columns(
            cs.string()
            .str.strip_chars()
            .str.to_lowercase()
            .str.replace_all("á", "a").str.replace_all("é", "e")
            .str.replace_all("í", "i").str.replace_all("ó", "o")
            .str.replace_all("ú", "u")
        )
        
        current_cols = lazy_clean.collect_schema().names()
        financial_metrics = [col for col in current_cols if re.search(r'_\d{4}$', col)]
        descriptive_cols = [col for col in current_cols if col not in financial_metrics and col != "key_value"]
        
        # Deduplication via grouping
        lazy_consolidated = lazy_clean.group_by("key_value").agg(
            *[pl.col(c).first() for c in descriptive_cols],
            *[pl.col(c).sum() for c in financial_metrics]
        )
        
        output_path = TMP_CONSOLIDATED_DIR / f"part_{char}.parquet"
        df_result = lazy_consolidated.collect()
        df_result.write_parquet(output_path, compression="zstd")
        
        del df_result
        gc.collect()

    logging.info("Merging all 16 consolidated chunks into intermediate file...")
    pl.scan_parquet(TMP_CONSOLIDATED_DIR / "part_*.parquet").sink_parquet(INTERMEDIATE_SILVER_PATH, compression="zstd")
    logging.info("Intermediate Silver layer successfully generated.")

def transpose_financial_columns():
    """Executes the Unpivot (Melt) operation iteratively per financial column to optimize RAM usage."""
    logging.info("Starting Financial Column Transposition Phase (Unpivot)...")
    
    schema = pl.read_parquet_schema(INTERMEDIATE_SILVER_PATH)
    all_columns = list(schema.keys())

    financial_cols = [col for col in all_columns if re.search(r'_\d{4}$', col)]
    descriptive_cols = [col for col in all_columns if col not in financial_cols]

    for target_col in financial_cols:
        logging.info(f"Unpivoting column: {target_col} ...")
        
        match = re.match(r'(.+)_(\d{4})$', target_col)
        phase = match.group(1)
        fiscal_year = int(match.group(2))
        
        lazy_chunk = (
            pl.scan_parquet(INTERMEDIATE_SILVER_PATH)
            .select(descriptive_cols + [target_col]) 
            .filter(pl.col(target_col) != 0.0)              
            .rename({target_col: "monto"})                
            .with_columns([
                pl.col("monto").cast(pl.Float64),         
                pl.lit(phase).alias("fase"),               
                pl.lit(fiscal_year).alias("ano_eje").cast(pl.Int32) 
            ])
            .with_columns(
                (pl.col("key_value") + "_" + pl.col("ano_eje").cast(pl.String) + "_" + pl.col("fase"))
                .hash()
                .alias("sk_silver_id")
            )
        )
        
        ordered_cols = ["sk_silver_id"] + [c for c in lazy_chunk.collect_schema().names() if c != "sk_silver_id"]
        lazy_chunk = lazy_chunk.select(ordered_cols)
        
        output_file = TMP_UNPIVOT_DIR / f"part_unpivot_{target_col}.parquet"
        df_chunk = lazy_chunk.collect()
        df_chunk.write_parquet(output_file, compression="zstd")
        
        del df_chunk
        gc.collect()

    logging.info("Unifying all unpivoted blocks into final Silver file...")
    pl.scan_parquet(TMP_UNPIVOT_DIR / "part_unpivot_*.parquet").sink_parquet(FINAL_SILVER_PATH, compression="zstd")
    logging.info(f"Silver layer pipeline completed successfully at: {FINAL_SILVER_PATH}")

def main():
    start_time = time.time()
    logging.info("=== STARTING INGESTION PIPELINE (BRONZE -> SILVER) ===")
    
    schema_overrides = load_secure_schema()
    consolidate_by_hash_chunking(schema_overrides)
    transpose_financial_columns()
    
    duration_minutes = (time.time() - start_time) / 60
    logging.info(f"=== PIPELINE COMPLETED IN {duration_minutes:.2f} MINUTES ===")

if __name__ == "__main__":
    main()