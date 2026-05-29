import time
import os
import logging
import duckdb
from config import (
    MAX_THREADS, 
    MEMORY_LIMIT, 
    GOLD_FACT_PATH, 
    GOLD_DIM_GEO_PATH, 
    GOLD_DIM_INST_PATH, 
    GOLD_DIM_PROG_PATH
)

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

def initialize_analytical_engine() -> duckdb.DuckDBPyConnection:
    """Initializes in-memory DuckDB engine, configures limits, and maps Parquet views."""
    logging.info("Initializing in-memory DuckDB Analytical Engine...")
    con = duckdb.connect(database=':memory:')
    
    # Hardware boundaries optimization injected dynamically
    con.execute(f"PRAGMA threads={MAX_THREADS};")          
    con.execute(f"PRAGMA memory_limit='{MEMORY_LIMIT}';")  
    logging.info(f"Engine hardware boundaries defined: {MAX_THREADS} threads | RAM limit: {MEMORY_LIMIT}")
    
    required_files = [
        GOLD_FACT_PATH,
        GOLD_DIM_GEO_PATH,
        GOLD_DIM_INST_PATH,
        GOLD_DIM_PROG_PATH
    ]
    
    for file in required_files:
        if not os.path.exists(str(file)):
            logging.error(f"Required Parquet file missing: {file}")
            raise FileNotFoundError(f"Parquet file not found: {file}")
    
    logging.info("Mapping physical Parquet files into virtual relational SQL views...")
    con.execute(f"CREATE VIEW fact_presupuesto AS SELECT * FROM '{GOLD_FACT_PATH}';")
    con.execute(f"CREATE VIEW dim_geografia AS SELECT * FROM '{GOLD_DIM_GEO_PATH}';")
    con.execute(f"CREATE VIEW dim_institucion AS SELECT * FROM '{GOLD_DIM_INST_PATH}';")
    con.execute(f"CREATE VIEW dim_programatica AS SELECT * FROM '{GOLD_DIM_PROG_PATH}';")
    
    logging.info("SQL database mapping completed. Engine ready for querying.")
    return con

def execute_query(con: duckdb.DuckDBPyConnection, query_path: str):
    """Executes a SQL query from a file."""
    with open(query_path, 'r') as f:
        query = f.read()
    
    df_res = con.execute(query).pl()
    print(f"\n--- REPORT {query_path.split('/')[-1].split('.')[0]} ---")
    print(df_res)
    print("-" * 47 + "\n")

def execute_report_1(con: duckdb.DuckDBPyConnection):
    """Report 1: Top 5 Departments with the Highest Real Expenditure (Devengado) in 2024."""
    logging.info("Executing Analytical Query 1: Top 5 Departments by real expenditure (2024)...")
    execute_query(con, 'sql/report_1.sql')

def execute_report_2(con: duckdb.DuckDBPyConnection):
    """Report 2: Historical evolution of the Modified Institutional Budget (PIM)."""
    logging.info("Executing Analytical Query 2: Historical PIM evolution trend...")
    execute_query(con, 'sql/report_2.sql')

def execute_report_3(con: duckdb.DuckDBPyConnection):
    """Report 3: Cross-sector governance analysis evaluating budget vs unique projects count."""
    logging.info("Executing Analytical Query 3: Cross-sector budget vs project volume analysis (2024)...")
    execute_query(con, 'sql/report_3.sql')

def main():
    start_time = time.time()
    logging.info("=== STARTING MANAGEMENT REPORT ANALYTICAL ENGINE ===")
    
    try:
        con = initialize_analytical_engine()
        
        execute_report_1(con)
        execute_report_2(con)
        execute_report_3(con)
        
        con.close()
        logging.info("Connection successfully terminated. RAM allocated to engine released.")
        
    except Exception as e:
        logging.error(f"Critical execution error running executive reports: {e}")
        raise
        
    duration = time.time() - start_time
    logging.info(f"=== ANALYTICAL REPORT ENGINE RUN COMPLETED IN {duration:.2f} SECONDS ===")

if __name__ == "__main__":
    main()
