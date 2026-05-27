"""
AI-Ready Sample Generator Module
Extracts a lightweight sample of the unified dataset specifically tailored
for ChatGPT/Claude context window limitations and structural analysis.
"""

import os
import sys
import time
import logging
import duckdb

# Fix Python path to discover modules inside the src/ directory smoothly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))
from config import GOLD_DIR, MAX_THREADS, MEMORY_LIMIT

# Professional logging configuration
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - [%(levelname)s] - %(message)s"
)

def generate_lightweight_ai_sample():
    """
    Connects to DuckDB to perform the full dimensional joins on a limited subset,
    exporting a tiny, high-context CSV file perfect for ChatGPT analysis.
    """
    logging.info("=== STARTING AI-READY SAMPLE GENERATION ===")
    start_time = time.time()
    
    # Target file designed specifically to be uploaded to ChatGPT
    output_sample_path = GOLD_DIR / "mef_dashboard_sample.csv"
    
    if output_sample_path.exists():
        output_sample_path.unlink()

    con = duckdb.connect(database=":memory:")
    con.execute(f"SET threads TO {MAX_THREADS};")
    con.execute(f"SET memory_limit = '{MEMORY_LIMIT}';")
    
    # We apply a 'LIMIT 500' at the core fact table level to keep it micro-lightweight
    logging.info("Executing relational joins on a limited sample data subset...")
    query = f"""
        COPY (
            SELECT 
                f.ano_eje,
                f.fase,
                f.monto,
                g.* EXCLUDE (sk_geografia_id),
                i.* EXCLUDE (sk_institucion_id),
                p.* EXCLUDE (sk_programatica_id),
                fi.* EXCLUDE (sk_financiamiento_id),
                e.* EXCLUDE (sk_economica_id)
            FROM (
                SELECT * FROM '{GOLD_DIR}/fact_presupuesto.parquet' 
                LIMIT 500
            ) f
            LEFT JOIN '{GOLD_DIR}/dim_geografia.parquet' g ON f.sk_geografia_id = g.sk_geografia_id
            LEFT JOIN '{GOLD_DIR}/dim_institucion.parquet' i ON f.sk_institucion_id = i.sk_institucion_id
            LEFT JOIN '{GOLD_DIR}/dim_programatica.parquet' p ON f.sk_programatica_id = p.sk_programatica_id
            LEFT JOIN '{GOLD_DIR}/dim_financiamiento.parquet' fi ON f.sk_financiamiento_id = fi.sk_financiamiento_id
            LEFT JOIN '{GOLD_DIR}/dim_economica.parquet' e ON f.sk_economica_id = e.sk_economica_id
        ) TO '{output_sample_path}' (FORMAT 'CSV', HEADER true);
    """
    
    try:
        con.execute(query)
        elapsed_time = time.time() - start_time
        logging.info(f"=== SAMPLE GENERATED SUCCESSFULLY IN {elapsed_time:.2f}s ===")
        logging.info(f"👉 Upload this file to ChatGPT: {output_sample_path}")
        
    except Exception as e:
        logging.error(f"Fatal error creating AI sample: {str(e)}")
        raise
    finally:
        con.close()

if __name__ == "__main__":
    generate_lightweight_ai_sample()