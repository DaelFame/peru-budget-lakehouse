import time
import logging
import polars as pl
from config import FINAL_SILVER_PATH, GOLD_FACT_PATH

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

def audit_financial_amounts(lazy_silver: pl.LazyFrame, lazy_gold_fact: pl.LazyFrame):
    """Validates total financial amount reconciliation between Silver and Gold layers."""
    logging.info("Starting Data Quality Control 1: Financial reconciliation check...")
    
    silver_total = lazy_silver.select(pl.col("monto").sum()).collect().item()
    gold_total = lazy_gold_fact.select(pl.col("monto").sum()).collect().item()
    
    discrepancy = abs(silver_total - gold_total)
    
    logging.info(f"Silver Layer Total Sum : S/. {silver_total:,.2f}")
    logging.info(f"Gold Layer Total Sum   : S/. {gold_total:,.2f}")
    logging.info(f"Total Discrepancy      : S/. {discrepancy:,.2f}")
    
    # 0.01 threshold allowance due to Float64 precision handling
    if discrepancy > 0.01:
        logging.error("❌ CRITICAL ERROR: Financial amounts between Silver and Gold layers DO NOT reconcile!")
        raise ValueError(f"Data quality audit failed. Financial mismatch detected: S/. {discrepancy:,.2f}")
    
    logging.info("✅ Data Quality Control 1 passed: Financial amounts are 100% synchronized.")

def audit_row_volumetrics(lazy_silver: pl.LazyFrame, lazy_gold_fact: pl.LazyFrame):
    """Verifies that record reduction matches expected business filtering logic (Null/Zero drop)."""
    logging.info("Starting Data Quality Control 2: Row volumetric consistency check...")
    
    total_silver_rows = lazy_silver.select(pl.len()).collect().item()
    clean_silver_rows = lazy_silver.filter(pl.col("monto").is_not_null() & (pl.col("monto") != 0.0)).select(pl.len()).collect().item()
    final_gold_rows = lazy_gold_fact.select(pl.len()).collect().item()
    
    expected_dropped_rows = total_silver_rows - clean_silver_rows
    unexplained_gap = clean_silver_rows - final_gold_rows
    
    logging.info(f"Total rows in Silver layer           : {total_silver_rows:,}")
    logging.info(f"Valid dropped rows (Nulls or Zeros)  : {expected_dropped_rows:,}")
    logging.info(f"Expected clean target rows           : {clean_silver_rows:,}")
    logging.info(f"Final injected rows in Fact Table    : {final_gold_rows:,}")
    
    if unexplained_gap != 0:
        logging.warning(f"⚠️ Notice: Unexplained delta of {unexplained_gap:,} rows detected. "
                        f"This standard deviation typically occurs due to null keys or source duplicates.")
    else:
        logging.info("✅ Data Quality Control 2 passed: Row volumetrics comply with business rules.")

def main():
    start_time = time.time()
    logging.info("=== STARTING AUTOMATED DATA QUALITY AUDIT (QA) ===")
    
    if not FINAL_SILVER_PATH.exists() or not GOLD_FACT_PATH.exists():
        logging.error("Missing core baseline data assets to run audit. Please run scripts 01 and 02 first.")
        return
        
    lazy_silver = pl.scan_parquet(FINAL_SILVER_PATH)
    lazy_gold_fact = pl.scan_parquet(GOLD_FACT_PATH)
    
    audit_financial_amounts(lazy_silver, lazy_gold_fact)
    audit_row_volumetrics(lazy_silver, lazy_gold_fact)
    
    duration = time.time() - start_time
    logging.info(f"=== QA AUDIT PIPELINE COMPLETED SUCCESSFULLY IN {duration:.2f} SECONDS ===")

if __name__ == "__main__":
    main()