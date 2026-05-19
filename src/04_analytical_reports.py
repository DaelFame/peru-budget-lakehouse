import time
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
    
    logging.info("Mapping physical Parquet files into virtual relational SQL views...")
    con.execute(f"CREATE VIEW fact_presupuesto AS SELECT * FROM '{GOLD_FACT_PATH}';")
    con.execute(f"CREATE VIEW dim_geografia AS SELECT * FROM '{GOLD_DIM_GEO_PATH}';")
    con.execute(f"CREATE VIEW dim_institucion AS SELECT * FROM '{GOLD_DIM_INST_PATH}';")
    con.execute(f"CREATE VIEW dim_programatica AS SELECT * FROM '{GOLD_DIM_PROG_PATH}';")
    
    logging.info("SQL database mapping completed. Engine ready for querying.")
    return con

def execute_report_1(con: duckdb.DuckDBPyConnection):
    """Report 1: Top 5 Departments with the Highest Real Expenditure (Devengado) in 2024."""
    logging.info("Executing Analytical Query 1: Top 5 Departments by real expenditure (2024)...")
    
    query = """
    SELECT 
        d_geo.departamento_ejecutora_nombre AS department,
        SUM(f.monto) / 1000000000 AS billion_soles
    FROM fact_presupuesto f
    JOIN dim_geografia d_geo ON f.sk_geografia_id = d_geo.sk_geografia_id
    WHERE f.ano_eje = 2024 
      AND f.fase = 'devengado'
      AND d_geo.departamento_ejecutora_nombre IS NOT NULL 
      AND TRIM(d_geo.departamento_ejecutora_nombre) != ''
    GROUP BY 1
    ORDER BY 2 DESC
    LIMIT 5;
    """
    df_res = con.execute(query).pl()
    print("\n--- REPORT 1: TOP 5 DEPARTMENTS EXPENDITURE ---")
    print(df_res)
    print("-" * 47 + "\n")

def execute_report_2(con: duckdb.DuckDBPyConnection):
    """Report 2: Historical evolution of the Modified Institutional Budget (PIM)."""
    logging.info("Executing Analytical Query 2: Historical PIM evolution trend...")
    
    query = """
    SELECT 
        ano_eje AS fiscal_year, 
        SUM(monto) / 1000000000 AS total_pim_billions
    FROM fact_presupuesto
    WHERE fase = 'pim'
    GROUP BY 1
    ORDER BY 1 ASC;
    """
    df_res = con.execute(query).pl()
    print("\n--- REPORT 2: HISTORICAL PIM TREND ---")
    print(df_res)
    print("-" * 38 + "\n")

def execute_report_3(con: duckdb.DuckDBPyConnection):
    """Report 3: Cross-sector governance analysis evaluating budget vs unique projects count."""
    logging.info("Executing Analytical Query 3: Cross-sector budget vs project volume analysis (2024)...")
    
    query = """
    SELECT 
        d_inst.sector_nombre AS government_sector,
        APPROX_COUNT_DISTINCT(d_prog.producto_proyecto) AS estimated_project_count,
        SUM(f.monto) / 1000000000 AS expenditure_billions
    FROM fact_presupuesto f
    JOIN dim_institucion d_inst ON f.sk_institucion_id = d_inst.sk_institucion_id
    JOIN dim_programatica d_prog ON f.sk_programatica_id = d_prog.sk_programatica_id
    WHERE f.ano_eje = 2024 
      AND f.fase = 'devengado'
      AND d_inst.sector_nombre IS NOT NULL 
      AND TRIM(d_inst.sector_nombre) != ''
    GROUP BY 1 
    ORDER BY 3 DESC 
    LIMIT 5;
    """
    df_res = con.execute(query).pl()
    print("\n--- REPORT 3: GOVERNMENT SECTOR BUDGET & PROJECTS ---")
    print(df_res)
    print("-" * 52 + "\n")

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