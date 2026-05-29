"""
Executive Dashboard Database Module (Star Schema Optimized)

This module handles all high-performance data extraction from the Gold Star Schema layers
using DuckDB. It centralizes SQL queries, dynamic filter parameters, core KPIs, and chart
aggregations, keeping the interface decoupled, secure, and fast.
"""

import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any

import duckdb
import pandas as pd

# Professional logging setup
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

# ----------------------------------------------------
# CONFIGURATION & UNIFIED PARQUET STAR SCHEMA PATHS
# ----------------------------------------------------
try:
    import config
    logger.info("Successfully imported project configuration.")
    # Read the explicit Gold Star Schema paths from config.py
    FACT_PATH = str(config.GOLD_FACT_PATH)
    DIM_GEO_PATH = str(config.GOLD_DIM_GEO_PATH)
    DIM_INST_PATH = str(config.GOLD_DIM_INST_PATH)
    MAX_THREADS = getattr(config, "MAX_THREADS", 4)
    MEMORY_LIMIT = getattr(config, "MEMORY_LIMIT", "4GB")
except ImportError:
    logger.warning("Project config.py not found in sys.path. Calculating local paths...")
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    FACT_PATH = str(PROJECT_ROOT / "data" / "03_gold" / "fact_presupuesto.parquet")
    DIM_GEO_PATH = str(PROJECT_ROOT / "data" / "03_gold" / "dim_geografia.parquet")
    DIM_INST_PATH = str(PROJECT_ROOT / "data" / "03_gold" / "dim_institucion.parquet")
    MAX_THREADS = 4
    MEMORY_LIMIT = "4GB"

logger.info(f"Fact Table Path: {FACT_PATH}")
logger.info(f"Dim Geography Path: {DIM_GEO_PATH}")
logger.info(f"Dim Institution Path: {DIM_INST_PATH}")


def _get_connection() -> duckdb.DuckDBPyConnection:
    """
    Establishes and returns a configured in-memory DuckDB connection.
    Registers Parquet files as views so the AI Engine can query them by name.
    """
    con = duckdb.connect(database=":memory:")
    con.execute(f"SET threads TO {MAX_THREADS};")
    con.execute(f"SET memory_limit = '{MEMORY_LIMIT}';")
    
    # Registro de todas las tablas del esquema Estrella como vistas
    # Esto permite que el motor de IA haga JOINs sobre estos nombres
    con.execute(f"CREATE OR REPLACE VIEW fact_presupuesto AS SELECT * FROM '{FACT_PATH}'")
    con.execute(f"CREATE OR REPLACE VIEW dim_geografia AS SELECT * FROM '{DIM_GEO_PATH}'")
    con.execute(f"CREATE OR REPLACE VIEW dim_institucion AS SELECT * FROM '{DIM_INST_PATH}'")
    
    # Asumimos rutas consistentes para el resto de dimensiones basadas en tu configuración
    # Si estas variables no existen, reemplaza por la ruta directa: 'data/03_gold/dim_programatica.parquet'
    con.execute(f"CREATE OR REPLACE VIEW dim_programatica AS SELECT * FROM '{str(Path(FACT_PATH).parent / 'dim_programatica.parquet')}'")
    con.execute(f"CREATE OR REPLACE VIEW dim_economica AS SELECT * FROM '{str(Path(FACT_PATH).parent / 'dim_economica.parquet')}'")
    con.execute(f"CREATE OR REPLACE VIEW dim_financiamiento AS SELECT * FROM '{str(Path(FACT_PATH).parent / 'dim_financiamiento.parquet')}'")
    
    return con

def _build_where_clause(
    year: Any = None,
    government_level: Any = None,
    sector: Any = None,
    department: Any = None
) -> Tuple[str, Dict[str, Any]]:
    """
    Dynamically constructs a safe SQL WHERE clause and its corresponding
    parameter bindings for DuckDB, mapping columns explicitly to Star Schema dimensions.
    
    Mapping Specifications:
        - ano_eje maps to Fact Table (alias 'f.')
        - nivel_gobierno_nombre and sector_nombre map to Institution Dimension (alias 'i.')
        - departamento_ejecutora_nombre maps to Geography Dimension (alias 'g.')
        
    Args:
        year: Filter for f.ano_eje (e.g. 2022, "ALL")
        government_level: Filter for i.nivel_gobierno_nombre
        sector: Filter for i.sector_nombre
        department: Filter for g.departamento_ejecutora_nombre

    Returns:
        Tuple[str, Dict[str, Any]]: The SQL WHERE clause snippet and dictionary of parameters.
    """
    where_clauses = []
    params = {}

    # Block fiscal year 2026 to prevent duplicate metrics from cloned source data.
    where_clauses.append("f.ano_eje <= 2025")

    if year is not None and str(year).strip().upper() != "ALL":
        year_str = str(year).strip()
        if year_str == "2026":
            where_clauses.append("1 = 0")
        else:
            where_clauses.append("CAST(f.ano_eje AS VARCHAR) = $year")
            params["year"] = year_str

    if government_level is not None and str(government_level).strip().upper() != "ALL":
        where_clauses.append("i.nivel_gobierno_nombre = $government_level")
        params["government_level"] = str(government_level).strip()

    if sector is not None and str(sector).strip().upper() != "ALL":
        where_clauses.append("i.sector_nombre = $sector")
        params["sector"] = str(sector).strip()

    if department is not None and str(department).strip().upper() != "ALL":
        where_clauses.append("g.departamento_ejecutora_nombre = $department")
        params["department"] = str(department).strip()

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    return where_sql, params


# ----------------------------------------------------
# 1. LOAD DROPDOWN FILTER DATA
# ----------------------------------------------------
def load_filters_data() -> Dict[str, List[Any]]:
    """
    Extracts unique sorted values directly from their isolated source dimension and fact tables.
    Bypasses relational joins entirely to achieve instantaneous load times.

    Dropdowns populated:
        - Fiscal Year (ano_eje from Fact Table)
        - Government Level (nivel_gobierno_nombre from Institution Dim)
        - Sector (sector_nombre from Institution Dim)
        - Department (departamento_ejecutora_nombre from Geography Dim)

    Returns:
        Dict[str, List[Any]]: Dictionary with sorted lists of values.
    """
    logger.info("Extracting unique filters directly from Star Schema source Parquet tables...")
    con = _get_connection()

    try:
        # Years from Fact table (Fast read, tiny footprint)
        years_df = con.execute(
            f"SELECT DISTINCT ano_eje FROM '{FACT_PATH}' WHERE ano_eje IS NOT NULL AND ano_eje <= 2025 ORDER BY ano_eje DESC"
        ).df()
        
        # Government levels from Institution Dim
        gov_levels_df = con.execute(
            f"SELECT DISTINCT nivel_gobierno_nombre FROM '{DIM_INST_PATH}' WHERE nivel_gobierno_nombre IS NOT NULL ORDER BY 1 ASC"
        ).df()
        
        # Sectors from Institution Dim
        sectors_df = con.execute(
            f"SELECT DISTINCT sector_nombre FROM '{DIM_INST_PATH}' WHERE sector_nombre IS NOT NULL ORDER BY 1 ASC"
        ).df()
        
        # Departments from Geography Dim
        departments_df = con.execute(
            f"SELECT DISTINCT departamento_ejecutora_nombre FROM '{DIM_GEO_PATH}' WHERE departamento_ejecutora_nombre IS NOT NULL ORDER BY 1 ASC"
        ).df()

        filters = {
            "years": [str(val) for val in years_df["ano_eje"].tolist()],
            "government_levels": [str(val) for val in gov_levels_df["nivel_gobierno_nombre"].tolist()],
            "sectors": [str(val) for val in sectors_df["sector_nombre"].tolist()],
            "departments": [str(val) for val in departments_df["departamento_ejecutora_nombre"].tolist()],
        }
        logger.info("Successfully loaded filter options.")
        return filters
    except Exception as e:
        logger.error(f"Error loading dropdown filters from Star Schema: {str(e)}")
        raise
    finally:
        con.close()


# ----------------------------------------------------
# 2. LOAD CORE KPIs
# ----------------------------------------------------
def load_dashboard_metrics(
    year: Any = None,
    government_level: Any = None,
    sector: Any = None,
    department: Any = None
) -> Dict[str, float]:
    """
    Computes the 4 Core KPIs utilizing the Parquet Star Schema dataset and explicit LEFT JOIN operations.
    
    KPIs Calculated:
        - Total Planned Budget (PIM): Sum of f.monto where lower(f.fase) in ('certificado', 'pim')
        - Total Executed Budget (DEVENGADO): Sum of f.monto where lower(f.fase) == 'devengado'
        - Execution Rate (%): (Devengado / PIM) * 100
        - Unexecuted Budget Gap: PIM - Devengado

    Args:
        year: Fiscal year filter.
        government_level: Government level filter.
        sector: Sector filter.
        department: Department filter.

    Returns:
        Dict[str, float]: Calculated metrics dictionary.
    """
    logger.info("Calculating Core KPIs from Gold Star Schema...")
    con = _get_connection()
    where_sql, params = _build_where_clause(year, government_level, sector, department)

    # Perform joins from Fact to Geography and Institution using hashed surrogate keys
    query = f"""
        SELECT 
            COALESCE(SUM(CASE WHEN lower(f.fase) IN ('pim', 'certificado') THEN f.monto ELSE 0.0 END), 0.0) AS pim,
            COALESCE(SUM(CASE WHEN lower(f.fase) = 'devengado' THEN f.monto ELSE 0.0 END), 0.0) AS devengado
        FROM '{FACT_PATH}' f
        LEFT JOIN '{DIM_GEO_PATH}' g ON f.sk_geografia_id = g.sk_geografia_id
        LEFT JOIN '{DIM_INST_PATH}' i ON f.sk_institucion_id = i.sk_institucion_id
        {where_sql}
    """

    try:
        result = con.execute(query, params).fetchone()
        pim = float(result[0]) if result and result[0] is not None else 0.0
        devengado = float(result[1]) if result and result[1] is not None else 0.0

        execution_rate = (devengado / pim * 100.0) if pim > 0.0 else 0.0
        unexecuted_gap = max(0.0, pim - devengado)

        metrics = {
            "pim": pim,
            "devengado": devengado,
            "execution_rate": execution_rate,
            "unexecuted_gap": unexecuted_gap
        }
        logger.info(f"Core KPIs successfully computed from Star Schema: {metrics}")
        return metrics
    except Exception as e:
        logger.error(f"Error calculating dashboard metrics from Star Schema: {str(e)}")
        raise
    finally:
        con.close()


# ----------------------------------------------------
# 3. EXTRACTION FUNCTIONS FOR CHARTS
# ----------------------------------------------------
def get_top_concentrations_data(
    group_by_column: str,
    limit: int = 10,
    year: Any = None,
    government_level: Any = None,
    sector: Any = None,
    department: Any = None
) -> pd.DataFrame:
    """
    Aggregates budget allocations (PIM) grouped by either sector or department
    using Star Schema left-joins, sorted descending for concentrations charts.

    Args:
        group_by_column (str): Either 'sector_nombre' or 'departamento_ejecutora_nombre'.
        limit (int): Top N categories to retrieve. Defaults to 10.
        year: Fiscal year filter.
        government_level: Government level filter.
        sector: Sector filter.
        department: Department filter.

    Returns:
        pd.DataFrame: Pandas DataFrame with columns ['dimension', 'total_monto'].
    """
    # Strict validation to prevent SQL Injection
    allowed_columns = {"sector_nombre", "departamento_ejecutora_nombre"}
    if group_by_column not in allowed_columns:
        raise ValueError(
            f"Invalid group_by_column: '{group_by_column}'. "
            f"Must be one of {allowed_columns}."
        )

    logger.info(f"Querying concentrations grouped by {group_by_column} from Star Schema...")
    con = _get_connection()
    where_sql, params = _build_where_clause(year, government_level, sector, department)

    # Route dimension table prefixes based on targeted grouping columns
    alias = "i" if group_by_column == "sector_nombre" else "g"

    query = f"""
        SELECT 
            {alias}.{group_by_column} AS dimension,
            COALESCE(SUM(CASE WHEN lower(f.fase) IN ('pim', 'certificado') THEN f.monto ELSE 0.0 END), 0.0) AS total_monto
        FROM '{FACT_PATH}' f
        LEFT JOIN '{DIM_GEO_PATH}' g ON f.sk_geografia_id = g.sk_geografia_id
        LEFT JOIN '{DIM_INST_PATH}' i ON f.sk_institucion_id = i.sk_institucion_id
        {where_sql}
        GROUP BY 1
        ORDER BY total_monto DESC
        LIMIT {limit}
    """

    try:
        df = con.execute(query, params).df()
        logger.info(f"Retrieved {len(df)} rows for concentrations from Star Schema.")
        return df
    except Exception as e:
        logger.error(f"Error querying concentrations from Star Schema: {str(e)}")
        raise
    finally:
        con.close()


def get_execution_variance_data(
    dimension_column: str,
    year: Any = None,
    government_level: Any = None,
    sector: Any = None,
    department: Any = None
) -> pd.DataFrame:
    """
    Extracts comparative PIM vs Devengado data grouped by a selected dimension
    using Star Schema left-joins.

    Args:
        dimension_column (str): Column name ('sector_nombre' or 'departamento_ejecutora_nombre')
        year: Fiscal year filter.
        government_level: Government level filter.
        sector: Sector filter.
        department: Department filter.

    Returns:
        pd.DataFrame: Pandas DataFrame with columns ['dimension', 'pim', 'devengado'].
    """
    allowed_columns = {
        "sector_nombre", 
        "departamento_ejecutora_nombre", 
        "nivel_gobierno_nombre"
    }
    if dimension_column not in allowed_columns:
        raise ValueError(
            f"Invalid dimension_column: '{dimension_column}'. "
            f"Must be one of {allowed_columns}."
        )

    logger.info(f"Querying comparative variance grouped by {dimension_column} from Star Schema...")
    con = _get_connection()
    where_sql, params = _build_where_clause(year, government_level, sector, department)

    alias = "g" if dimension_column == "departamento_ejecutora_nombre" else "i"

    query = f"""
        SELECT 
            {alias}.{dimension_column} AS dimension,
            COALESCE(SUM(CASE WHEN lower(f.fase) IN ('pim', 'certificado') THEN f.monto ELSE 0.0 END), 0.0) AS pim,
            COALESCE(SUM(CASE WHEN lower(f.fase) = 'devengado' THEN f.monto ELSE 0.0 END), 0.0) AS devengado
        FROM '{FACT_PATH}' f
        LEFT JOIN '{DIM_GEO_PATH}' g ON f.sk_geografia_id = g.sk_geografia_id
        LEFT JOIN '{DIM_INST_PATH}' i ON f.sk_institucion_id = i.sk_institucion_id
        {where_sql}
        GROUP BY 1
        ORDER BY pim DESC
    """

    try:
        df = con.execute(query, params).df()
        logger.info(f"Retrieved {len(df)} rows for comparative variance from Star Schema.")
        return df
    except Exception as e:
        logger.error(f"Error querying comparative variance from Star Schema: {str(e)}")
        raise
    finally:
        con.close()


def get_geographic_heatmap_data(
    year: Any = None,
    government_level: Any = None,
    sector: Any = None,
    department: Any = None
) -> pd.DataFrame:
    """
    Aggregates budget execution rates grouped by executing department
    and fiscal year using Star Schema left-joins.

    Args:
        year: Fiscal year filter.
        government_level: Government level filter.
        sector: Sector filter.
        department: Department filter.

    Returns:
        pd.DataFrame: Pandas DataFrame with columns:
                      ['department', 'fiscal_year', 'pim', 'devengado', 'execution_rate'].
    """
    logger.info("Querying geographic heatmap data from Star Schema...")
    con = _get_connection()
    where_sql, params = _build_where_clause(year, government_level, sector, department)

    query = f"""
        SELECT 
            g.departamento_ejecutora_nombre AS department,
            f.ano_eje AS fiscal_year,
            COALESCE(SUM(CASE WHEN lower(f.fase) IN ('pim', 'certificado') THEN f.monto ELSE 0.0 END), 0.0) AS pim,
            COALESCE(SUM(CASE WHEN lower(f.fase) = 'devengado' THEN f.monto ELSE 0.0 END), 0.0) AS devengado,
            CASE 
                WHEN SUM(CASE WHEN lower(f.fase) IN ('pim', 'certificado') THEN f.monto ELSE 0.0 END) > 0 
                THEN (SUM(CASE WHEN lower(f.fase) = 'devengado' THEN f.monto ELSE 0.0 END) / 
                      SUM(CASE WHEN lower(f.fase) IN ('pim', 'certificado') THEN f.monto ELSE 0.0 END)) * 100.0
                ELSE 0.0 
            END AS execution_rate
        FROM '{FACT_PATH}' f
        LEFT JOIN '{DIM_GEO_PATH}' g ON f.sk_geografia_id = g.sk_geografia_id
        LEFT JOIN '{DIM_INST_PATH}' i ON f.sk_institucion_id = i.sk_institucion_id
        {where_sql}
        GROUP BY 1, 2
        ORDER BY department ASC, fiscal_year DESC
    """

    try:
        df = con.execute(query, params).df()
        logger.info(f"Retrieved {len(df)} rows for geographic heatmap from Star Schema.")
        return df
    except Exception as e:
        logger.error(f"Error querying geographic heatmap data from Star Schema: {str(e)}")
        raise
    finally:
        con.close()
