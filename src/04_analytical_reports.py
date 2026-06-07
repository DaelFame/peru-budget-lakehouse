import time
import logging
import duckdb
from config import (
    MAX_THREADS, 
    MEMORY_LIMIT, 
    GOLD_FACT_PATH, 
    GOLD_DIM_GEO_PATH, 
    GOLD_DIM_INST_PATH, 
    GOLD_DIM_PROG_PATH,
    GOLD_DIM_ECON_PATH,       # 1. Traemos las dimensiones faltantes
    GOLD_DIM_FIN_PATH         # para consistencia total
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
    
    # 2. Mapeo simétrico de las 6 tablas del Star Schema
    view_mappings = {
        "fact_presupuesto": GOLD_FACT_PATH,
        "dim_geografia": GOLD_DIM_GEO_PATH,
        "dim_institucion": GOLD_DIM_INST_PATH,
        "dim_programatica": GOLD_DIM_PROG_PATH,
        "dim_economica": GOLD_DIM_ECON_PATH,
        "dim_financiamiento": GOLD_DIM_FIN_PATH
    }
    
    # 3. Validación y registro usando Pathlib puro (sin 'os')
    logging.info("Validating dataset assets and mapping physical Parquet files into virtual relational views...")
    for view_name, file_path in view_mappings.items():
        if not file_path.exists(): # Limpio, nativo y legible
            logging.error(f"Required Parquet file missing for view '{view_name}': {file_path}")
            raise FileNotFoundError(f"Parquet file not found: {file_path}")
        
        con.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM '{file_path}';")
    
    logging.info("SQL database mapping completed. Engine ready for querying.")
    return con

def execute_query(con: duckdb.DuckDBPyConnection, query_path: str):
    """Executes a SQL query safely from a file and renders the output."""
    # 4. Agregamos un try/except local para que un SQL roto no rompa todo el pipeline
    try:
        with open(query_path, 'r', encoding='utf-8') as f:
            query = f.read()
        
        df_res = con.execute(query).pl()
        report_name = query_path.split('/')[-1].replace('.sql', '').upper()
        
        print(f"\n===============================================")
        print(f"📊 REPORT: {report_name}")
        print(f"===============================================")
        print(df_res)
        print("===============================================\n")
        
    except Exception as e:
        logging.error(f"Failed to execute query from asset {query_path}: {e}")
        raise

def main():
    start_time = time.time()
    logging.info("=== STARTING MANAGEMENT REPORT ANALYTICAL ENGINE ===")
    
    con = None
    try:
        con = initialize_analytical_engine()
        
        # Ejecución secuencial de los reportes ejecutivos
        execute_query(con, 'sql/report_1.sql')
        execute_query(con, 'sql/report_2.sql')
        execute_query(con, 'sql/report_3.sql')
        execute_query(con, 'sql/report_4.sql')
        
    except Exception as e:
        logging.error(f"Critical execution error running executive reports: {e}")
        raise
    finally:
        # 5. El bloque finally asegura la liberación de RAM pase lo que pase
        if con is not None:
            con.close()
            logging.info("Connection successfully terminated. RAM allocated to engine released.")
        
    duration = time.time() - start_time
    logging.info(f"=== ANALYTICAL REPORT ENGINE RUN COMPLETED IN {duration:.2f} SECONDS ===")

if __name__ == "__main__":
    main()