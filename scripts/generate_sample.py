"""
AI-Ready Sample Generator Module
--------------------------------
Extracts a highly representative, lightweight subset of the Gold layer (Star Schema).
Designed for AI context window ingestion and rapid structural/schema analysis.
"""

import os
import sys
import time
import logging
from pathlib import Path

# Robust path handling: Ensures the root project directory is in the sys.path
# This allows importing 'src.config' regardless of where the script is executed.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

import duckdb
from src.config import GOLD_DIR, MAX_THREADS, MEMORY_LIMIT

# Professional logging configuration
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - [%(levelname)s] - %(message)s"
)

def export_ai_dev_sample(limit: int = 500):
    """
    Performs a relational join across the Star Schema and exports a sample 
    to CSV. Enables LLMs to perform analysis or generate queries on the 
    actual data structure.
    """
    logging.info(f"=== INITIALIZING AI SAMPLE EXPORT (LIMIT: {limit}) ===")
    start_time = time.time()
    
    output_path = GOLD_DIR / "mef_dashboard_sample.csv"
    
    # Cleanup previous sample if it exists
    if output_path.exists():
        output_path.unlink()

    # Initialize DuckDB with system-aware resource configuration
    con = duckdb.connect(database=":memory:")
    con.execute(f"SET threads TO {MAX_THREADS};")
    con.execute(f"SET memory_limit = '{MEMORY_LIMIT}';")
    
    # SQL Query: Performs an INNER JOIN logic within a constrained sample set
    # Using 'EXCLUDE' to keep the sample clean and focused on business attributes
    query = f"""
        COPY (
            SELECT 
                f.anio,
                f.fase,
                f.monto,
                g.* EXCLUDE (sk_geografia_id),
                i.* EXCLUDE (sk_institucion_id),
                p.* EXCLUDE (sk_programatica_id),
                fi.* EXCLUDE (sk_financiamiento_id),
                e.* EXCLUDE (sk_economica_id)
            FROM (
                SELECT * FROM '{GOLD_DIR}/fact_presupuesto.parquet' 
                LIMIT {limit}
            ) f
            LEFT JOIN '{GOLD_DIR}/dim_geografia.parquet' g ON f.sk_geografia_id = g.sk_geografia_id
            LEFT JOIN '{GOLD_DIR}/dim_institucion.parquet' i ON f.sk_institucion_id = i.sk_institucion_id
            LEFT JOIN '{GOLD_DIR}/dim_programatica.parquet' p ON f.sk_programatica_id = p.sk_programatica_id
            LEFT JOIN '{GOLD_DIR}/dim_financiamiento.parquet' fi ON f.sk_financiamiento_id = fi.sk_financiamiento_id
            LEFT JOIN '{GOLD_DIR}/dim_economica.parquet' e ON f.sk_economica_id = e.sk_economica_id
        ) TO '{output_path}' (FORMAT 'CSV', HEADER true);
    """
    
    try:
        logging.info("Executing relational join engine...")
        con.execute(query)
        
        duration = time.time() - start_time
        logging.info(f"=== SUCCESS: Sample generated in {duration:.2f}s ===")
        logging.info(f"Location: {output_path}")
        
    except Exception as e:
        logging.error(f"Failed to export sample: {str(e)}")
        raise
    finally:
        con.close()

if __name__ == "__main__":
    export_ai_dev_sample()