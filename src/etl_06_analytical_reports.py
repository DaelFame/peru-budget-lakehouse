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
    GOLD_DIM_ECON_PATH,
    GOLD_DIM_FIN_PATH,
    PROJECT_ROOT          # ← fix: rutas SQL absolutas, no relativas al CWD
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

SQL_DIR = PROJECT_ROOT / "sql"


def initialize_analytical_engine() -> duckdb.DuckDBPyConnection:
    """Initializes in-memory DuckDB engine, configures limits, and maps Parquet views."""
    logging.info("Initializing in-memory DuckDB Analytical Engine...")
    con = duckdb.connect(database=':memory:')

    con.execute(f"PRAGMA threads={MAX_THREADS};")
    con.execute(f"PRAGMA memory_limit='{MEMORY_LIMIT}';")
    logging.info(f"Engine hardware boundaries defined: {MAX_THREADS} threads | RAM limit: {MEMORY_LIMIT}")

    view_mappings = {
        "fact_presupuesto":   GOLD_FACT_PATH,
        "dim_geografia":      GOLD_DIM_GEO_PATH,
        "dim_institucion":    GOLD_DIM_INST_PATH,
        "dim_programatica":   GOLD_DIM_PROG_PATH,
        "dim_economica":      GOLD_DIM_ECON_PATH,
        "dim_financiamiento": GOLD_DIM_FIN_PATH
    }

    logging.info("Validating dataset assets and mapping physical Parquet files into virtual relational views...")
    for view_name, file_path in view_mappings.items():
        if not file_path.exists():
            logging.error(f"Required Parquet file missing for view '{view_name}': {file_path}")
            raise FileNotFoundError(f"Parquet file not found: {file_path}")
        con.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM '{file_path}';")

    logging.info("SQL database mapping completed. Engine ready for querying.")
    return con


def execute_query(con: duckdb.DuckDBPyConnection, sql_filename: str):
    """
    Ejecuta un reporte SQL usando ruta absoluta desde PROJECT_ROOT/sql/.
    Nunca falla por CWD — funciona igual desde terminal, Prefect, o Jupyter.
    """
    query_path = SQL_DIR / sql_filename
    try:
        with open(query_path, 'r', encoding='utf-8') as f:
            query = f.read()

        df_res = con.execute(query).pl()
        report_name = sql_filename.replace('.sql', '').upper()

        print("\n===============================================")
        print(f"📊 REPORT: {report_name}")
        print("===============================================")
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

        execute_query(con, 'report_1.sql')
        execute_query(con, 'report_2.sql')
        execute_query(con, 'report_3.sql')
        execute_query(con, 'report_4.sql')

    except Exception as e:
        logging.error(f"Critical execution error running executive reports: {e}")
        raise
    finally:
        if con is not None:
            con.close()
            logging.info("Connection successfully terminated. RAM allocated to engine released.")

    duration = time.time() - start_time
    logging.info(f"=== ANALYTICAL REPORT ENGINE RUN COMPLETED IN {duration:.2f} SECONDS ===")


if __name__ == "__main__":
    main()
