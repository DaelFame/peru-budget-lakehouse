"""
Executive Dashboard Database Module (Star Schema Optimized)
Handles all high-performance data extraction from the Gold Star Schema layers
using DuckDB with conditional JOINs — only joins dimension tables when the
active filter actually requires it, keeping scans minimal on 54M+ row fact tables.
"""
import logging
from typing import Dict, List, Tuple, Any
import duckdb
import pandas as pd
import streamlit as st
from config import (
    GOLD_FACT_PATH,
    GOLD_DIM_GEO_PATH,
    GOLD_DIM_INST_PATH,
    GOLD_DIM_PROG_PATH,
    GOLD_DIM_ECON_PATH,
    GOLD_DIM_FIN_PATH,
    MAX_THREADS,
    MEMORY_LIMIT,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

# ----------------------------------------------------
# STAR SCHEMA PATHS (Single Source of Truth: config.py)
# ----------------------------------------------------
FACT_PATH     = str(GOLD_FACT_PATH)
DIM_GEO_PATH  = str(GOLD_DIM_GEO_PATH)
DIM_INST_PATH = str(GOLD_DIM_INST_PATH)
DIM_PROG_PATH = str(GOLD_DIM_PROG_PATH)
DIM_ECON_PATH = str(GOLD_DIM_ECON_PATH)
DIM_FIN_PATH  = str(GOLD_DIM_FIN_PATH)

logger.info(f"Fact Table Path:      {FACT_PATH}")
logger.info(f"Dim Geography Path:   {DIM_GEO_PATH}")
logger.info(f"Dim Institution Path: {DIM_INST_PATH}")


# ----------------------------------------------------
# CONNECTION MANAGEMENT
# ----------------------------------------------------
def _get_connection() -> duckdb.DuckDBPyConnection:
    """
    Creates a fresh in-memory DuckDB connection and registers all Gold Parquet
    files as named views. This allows both the dashboard queries and the AI Engine
    to reference tables by name (e.g. fact_presupuesto, dim_geografia) without
    hardcoding file paths in every SQL statement.
    """
    con = duckdb.connect(database=":memory:")
    con.execute(f"SET threads TO {MAX_THREADS};")
    con.execute(f"SET memory_limit = '{MEMORY_LIMIT}';")

    con.execute(f"CREATE OR REPLACE VIEW fact_presupuesto   AS SELECT * FROM '{FACT_PATH}'")
    con.execute(f"CREATE OR REPLACE VIEW dim_geografia       AS SELECT * FROM '{DIM_GEO_PATH}'")
    con.execute(f"CREATE OR REPLACE VIEW dim_institucion     AS SELECT * FROM '{DIM_INST_PATH}'")
    con.execute(f"CREATE OR REPLACE VIEW dim_programatica    AS SELECT * FROM '{DIM_PROG_PATH}'")
    con.execute(f"CREATE OR REPLACE VIEW dim_economica       AS SELECT * FROM '{DIM_ECON_PATH}'")
    con.execute(f"CREATE OR REPLACE VIEW dim_financiamiento  AS SELECT * FROM '{DIM_FIN_PATH}'")

    return con


@st.cache_resource
def get_connection() -> duckdb.DuckDBPyConnection:
    """
    Singleton cached connection for Streamlit sessions.
    @st.cache_resource ensures a single DuckDB connection is reused across
    all reruns, avoiding repeated Parquet scans on view registration.
    """
    return _get_connection()


# ----------------------------------------------------
# JOIN OPTIMIZER
# Conditional JOIN logic: only joins a dimension table when the active
# filter or grouping column actually requires it. On unfiltered queries
# (ALL selected), the fact table is scanned directly — no JOIN overhead.
# ----------------------------------------------------
def _needs_geo_join(department: Any, group_col: str = "") -> bool:
    """Returns True if the geography dimension JOIN is required."""
    active_filter = department is not None and str(department).strip().upper() != "ALL"
    needs_for_group = group_col == "departamento_ejecutora_nombre"
    return active_filter or needs_for_group


def _needs_inst_join(government_level: Any, sector: Any, group_col: str = "") -> bool:
    """Returns True if the institution dimension JOIN is required."""
    active_gov    = government_level is not None and str(government_level).strip().upper() != "ALL"
    active_sector = sector is not None and str(sector).strip().upper() != "ALL"
    needs_for_group = group_col in ("sector_nombre", "nivel_gobierno_nombre")
    return active_gov or active_sector or needs_for_group


def _build_joins(need_geo: bool = False, need_inst: bool = False, need_econ: bool = False, need_fin: bool = False, need_prog: bool = False) -> str:
    """Assembles only the JOIN clauses required by the current query context."""
    joins = []
    if need_geo:
        joins.append("LEFT JOIN dim_geografia g ON f.sk_geografia_id = g.sk_geografia_id")
    if need_inst:
        joins.append("LEFT JOIN dim_institucion i ON f.sk_institucion_id = i.sk_institucion_id")
    if need_econ:
        joins.append("LEFT JOIN dim_economica e ON f.sk_economica_id = e.sk_economica_id")
    if need_fin:
        joins.append("LEFT JOIN dim_financiamiento fi ON f.sk_financiamiento_id = fi.sk_financiamiento_id")
    if need_prog:
        joins.append("LEFT JOIN dim_programatica p ON f.sk_programatica_id = p.sk_programatica_id")
    return "\n".join(joins)


# ----------------------------------------------------
# WHERE CLAUSE BUILDER
# Dynamically constructs a parameterized WHERE clause.
# Column → dimension alias mapping:
#   f.anio                        → Fact Table        (alias 'f')
#   nivel_gobierno_nombre         → dim_institucion   (alias 'i')
#   sector_nombre                 → dim_institucion   (alias 'i')
#   departamento_ejecutora_nombre → dim_geografia     (alias 'g')
# 2026 is always blocked — source data clones 2025 values into 2026.
# ----------------------------------------------------
def _build_where_clause(
    year: Any = None,
    government_level: Any = None,
    sector: Any = None,
    department: Any = None
) -> Tuple[str, Dict[str, Any]]:
    where_clauses = ["f.anio <= 2025"]  # Block cloned 2026 data
    params: Dict[str, Any] = {}

    if year is not None and str(year).strip().upper() != "ALL":
        year_str = str(year).strip()
        if year_str == "2026":
            where_clauses.append("1 = 0")
        else:
            where_clauses.append("CAST(f.anio AS VARCHAR) = $year")
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

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    return where_sql, params


# ----------------------------------------------------
# 1. FILTER DROPDOWNS
# Reads unique values directly from isolated dimension/fact Parquet files.
# No JOINs needed here — each dropdown maps to exactly one table.
# ----------------------------------------------------
def load_filters_data() -> Dict[str, List[Any]]:
    """
    Populates sidebar filter dropdowns from their source dimension tables:
        - Fiscal Year       → fact_presupuesto  (anio)
        - Government Level  → dim_institucion   (nivel_gobierno_nombre)
        - Sector            → dim_institucion   (sector_nombre)
        - Department        → dim_geografia     (departamento_ejecutora_nombre)
    """
    logger.info("Extracting unique filters directly from Star Schema source Parquet tables...")
    con = get_connection()
    try:
        years_df   = con.execute("SELECT DISTINCT anio FROM fact_presupuesto WHERE anio IS NOT NULL AND anio <= 2025 ORDER BY anio DESC").df()
        gov_df     = con.execute("SELECT DISTINCT nivel_gobierno_nombre FROM dim_institucion WHERE nivel_gobierno_nombre IS NOT NULL ORDER BY 1").df()
        sectors_df = con.execute("SELECT DISTINCT sector_nombre FROM dim_institucion WHERE sector_nombre IS NOT NULL ORDER BY 1").df()
        depts_df   = con.execute("SELECT DISTINCT departamento_ejecutora_nombre FROM dim_geografia WHERE departamento_ejecutora_nombre IS NOT NULL ORDER BY 1").df()

        filters = {
            "years":             [str(v) for v in years_df["anio"].tolist()],
            "government_levels": [str(v) for v in gov_df["nivel_gobierno_nombre"].tolist()],
            "sectors":           [str(v) for v in sectors_df["sector_nombre"].tolist()],
            "departments":       [str(v) for v in depts_df["departamento_ejecutora_nombre"].tolist()],
        }
        logger.info("Successfully loaded filter options.")
        return filters
    except Exception as e:
        logger.error(f"Error loading dropdown filters: {str(e)}")
        raise


# ----------------------------------------------------
# 2. CORE KPIs
# Computes 4 executive KPIs from the fact table.
# JOINs are skipped entirely when no dimension filter is active.
# fase values: 'pim', 'pia', 'certificado', 'comprometido',
#              'comprometido_anual', 'devengado', 'girado'
# PIM  = fase == 'pim'       (Presupuesto Institucional Modificado)
# DEV  = fase == 'devengado' (Gasto efectivamente ejecutado)
# ----------------------------------------------------
def load_dashboard_metrics(
    year: Any = None,
    government_level: Any = None,
    sector: Any = None,
    department: Any = None
) -> Dict[str, float]:
    """
    Returns:
        pim            → Total planned budget
        devengado      → Total executed budget
        execution_rate → devengado / pim * 100
        unexecuted_gap → pim - devengado
    """
    logger.info("Calculating Core KPIs from Gold Star Schema...")
    con = get_connection()
    where_sql, params = _build_where_clause(year, government_level, sector, department)

    need_geo  = _needs_geo_join(department)
    need_inst = _needs_inst_join(government_level, sector)
    joins     = _build_joins(need_geo, need_inst)

    query = f"""
        SELECT
            COALESCE(SUM(CASE WHEN f.fase = 'pim'       THEN f.monto ELSE 0.0 END), 0.0) AS pim,
            COALESCE(SUM(CASE WHEN f.fase = 'devengado' THEN f.monto ELSE 0.0 END), 0.0) AS devengado
        FROM fact_presupuesto f
        {joins}
        {where_sql}
    """
    try:
        result    = con.execute(query, params).fetchone()
        pim       = float(result[0]) if result and result[0] is not None else 0.0
        devengado = float(result[1]) if result and result[1] is not None else 0.0
        metrics   = {
            "pim":            pim,
            "devengado":      devengado,
            "execution_rate": (devengado / pim * 100.0) if pim > 0.0 else 0.0,
            "unexecuted_gap": max(0.0, pim - devengado),
        }
        logger.info(f"Core KPIs successfully computed: {metrics}")
        return metrics
    except Exception as e:
        logger.error(f"Error calculating KPIs: {str(e)}")
        raise


# ----------------------------------------------------
# 3. TOP BUDGET CONCENTRATIONS
# Aggregates PIM by sector or department for the bar chart.
# Always JOINs the dimension being grouped — conditionally JOINs
# the other dimension only if its filter is active.
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
    Args:
        group_by_column: 'sector_nombre' or 'departamento_ejecutora_nombre'
        limit: Top N results (default 10)
    Returns:
        DataFrame with columns ['dimension', 'total_monto']
    """
    allowed_columns = {"sector_nombre", "departamento_ejecutora_nombre"}
    if group_by_column not in allowed_columns:
        raise ValueError(f"Invalid group_by_column: '{group_by_column}'. Must be one of {allowed_columns}.")

    logger.info(f"Querying concentrations by {group_by_column}...")
    con = get_connection()
    where_sql, params = _build_where_clause(year, government_level, sector, department)

    need_geo  = _needs_geo_join(department, group_col=group_by_column)
    need_inst = _needs_inst_join(government_level, sector, group_col=group_by_column)
    joins     = _build_joins(need_geo, need_inst)
    alias     = "i" if group_by_column == "sector_nombre" else "g"

    query = f"""
        SELECT
            {alias}.{group_by_column}                                                         AS dimension,
            COALESCE(SUM(CASE WHEN f.fase = 'pim' THEN f.monto ELSE 0.0 END), 0.0) AS total_monto
        FROM fact_presupuesto f
        {joins}
        {where_sql}
        GROUP BY 1
        ORDER BY total_monto DESC
        LIMIT {limit}
    """
    try:
        df = con.execute(query, params).df()
        logger.info(f"Concentrations: {len(df)} rows retrieved.")
        return df
    except Exception as e:
        logger.error(f"Error querying concentrations: {str(e)}")
        raise


# ----------------------------------------------------
# 4. EXECUTION VARIANCE (PIM vs DEVENGADO)
# Compares planned vs executed budget by a chosen dimension.
# Used for the side-by-side bar chart in the dashboard.
# ----------------------------------------------------
def get_execution_variance_data(
    dimension_column: str,
    year: Any = None,
    government_level: Any = None,
    sector: Any = None,
    department: Any = None
) -> pd.DataFrame:
    """
    Args:
        dimension_column: 'sector_nombre', 'departamento_ejecutora_nombre',
                          or 'nivel_gobierno_nombre'
    Returns:
        DataFrame with columns ['dimension', 'pim', 'devengado']
    """
    allowed_columns = {"sector_nombre", "departamento_ejecutora_nombre", "nivel_gobierno_nombre"}
    if dimension_column not in allowed_columns:
        raise ValueError(f"Invalid dimension_column: '{dimension_column}'. Must be one of {allowed_columns}.")

    logger.info(f"Querying execution variance by {dimension_column}...")
    con = get_connection()
    where_sql, params = _build_where_clause(year, government_level, sector, department)

    need_geo  = _needs_geo_join(department, group_col=dimension_column)
    need_inst = _needs_inst_join(government_level, sector, group_col=dimension_column)
    joins     = _build_joins(need_geo, need_inst)
    alias     = "g" if dimension_column == "departamento_ejecutora_nombre" else "i"

    query = f"""
        SELECT
            {alias}.{dimension_column}                                                              AS dimension,
            COALESCE(SUM(CASE WHEN f.fase = 'pim'       THEN f.monto ELSE 0.0 END), 0.0) AS pim,
            COALESCE(SUM(CASE WHEN f.fase = 'devengado' THEN f.monto ELSE 0.0 END), 0.0) AS devengado
        FROM fact_presupuesto f
        {joins}
        {where_sql}
        GROUP BY 1
        ORDER BY pim DESC
    """
    try:
        df = con.execute(query, params).df()
        logger.info(f"Variance: {len(df)} rows retrieved.")
        return df
    except Exception as e:
        logger.error(f"Error querying variance: {str(e)}")
        raise


# ----------------------------------------------------
# 5. GEOGRAPHIC HEATMAP
# Execution rate (%) by department × fiscal year matrix.
# Always JOINs geography (needed for department label).
# Only JOINs institution if a gov/sector filter is active.
# ----------------------------------------------------
def get_geographic_heatmap_data(
    year: Any = None,
    government_level: Any = None,
    sector: Any = None,
    department: Any = None
) -> pd.DataFrame:
    """
    Returns:
        DataFrame with columns:
        ['department', 'fiscal_year', 'pim', 'devengado', 'execution_rate']
    """
    logger.info("Querying geographic heatmap data...")
    con = get_connection()
    where_sql, params = _build_where_clause(year, government_level, sector, department)

    # Geo always needed for department label; inst only if filter is active
    need_inst = _needs_inst_join(government_level, sector)
    joins     = _build_joins(need_geo=True, need_inst=need_inst)

    query = f"""
        SELECT
            g.departamento_ejecutora_nombre                                                     AS department,
            f.anio                                                                              AS fiscal_year,
            COALESCE(SUM(CASE WHEN f.fase = 'pim'       THEN f.monto ELSE 0.0 END), 0.0)      AS pim,
            COALESCE(SUM(CASE WHEN f.fase = 'devengado' THEN f.monto ELSE 0.0 END), 0.0)      AS devengado,
            CASE
                WHEN SUM(CASE WHEN f.fase = 'pim' THEN f.monto ELSE 0.0 END) > 0
                THEN SUM(CASE WHEN f.fase = 'devengado' THEN f.monto ELSE 0.0 END) /
                     SUM(CASE WHEN f.fase = 'pim'       THEN f.monto ELSE 0.0 END) * 100.0
                ELSE 0.0
            END                                                                                 AS execution_rate
        FROM fact_presupuesto f
        {joins}
        {where_sql}
        GROUP BY 1, 2
        ORDER BY department ASC, fiscal_year DESC
    """
    try:
        df = con.execute(query, params).df()
        logger.info(f"Heatmap: {len(df)} rows retrieved.")
        return df
    except Exception as e:
        logger.error(f"Error querying heatmap: {str(e)}")
        raise


# ----------------------------------------------------
# 6. ECONOMIC COMPOSITION
# Groups budget by economic classification (generica_nombre).
# Always JOINs dim_economica; conditionally JOINs geography
# and institution based on active filters.
# ----------------------------------------------------
def get_economic_composition_data(
    year: Any = None,
    government_level: Any = None,
    sector: Any = None,
    department: Any = None
) -> pd.DataFrame:
    """
    Returns:
        DataFrame with columns ['economic_category', 'pim', 'devengado']
        sorted by pim DESC.
    """
    logger.info("Querying economic composition by generica_nombre...")
    con = get_connection()
    where_sql, params = _build_where_clause(year, government_level, sector, department)

    need_geo  = _needs_geo_join(department)
    need_inst = _needs_inst_join(government_level, sector)
    joins     = _build_joins(need_geo=need_geo, need_inst=need_inst, need_econ=True)

    query = f"""
        SELECT
            e.generica_nombre                                                              AS economic_category,
            COALESCE(SUM(CASE WHEN f.fase = 'pim'       THEN f.monto ELSE 0.0 END), 0.0)  AS pim,
            COALESCE(SUM(CASE WHEN f.fase = 'devengado' THEN f.monto ELSE 0.0 END), 0.0)  AS devengado
        FROM fact_presupuesto f
        {joins}
        {where_sql}
        GROUP BY 1
        ORDER BY pim DESC
    """
    try:
        df = con.execute(query, params).df()
        logger.info(f"Economic composition: {len(df)} rows retrieved.")
        return df
    except Exception as e:
        logger.error(f"Error querying economic composition: {str(e)}")
        raise


# ----------------------------------------------------
# 7. FINANCING STRUCTURE
# Groups budget by financing source (fuente_financiamiento_nombre).
# Always JOINs dim_financiamiento; conditionally JOINs geography
# and institution based on active filters.
# ----------------------------------------------------
def get_financing_structure_data(
    year: Any = None,
    government_level: Any = None,
    sector: Any = None,
    department: Any = None
) -> pd.DataFrame:
    """
    Returns:
        DataFrame with columns ['financing_source', 'pim', 'devengado']
        sorted by pim DESC.
    """
    logger.info("Querying financing structure by fuente_financiamiento_nombre...")
    con = get_connection()
    where_sql, params = _build_where_clause(year, government_level, sector, department)

    need_geo  = _needs_geo_join(department)
    need_inst = _needs_inst_join(government_level, sector)
    joins     = _build_joins(need_geo=need_geo, need_inst=need_inst, need_fin=True)

    query = f"""
        SELECT
            fi.fuente_financiamiento_nombre                                                   AS financing_source,
            COALESCE(SUM(CASE WHEN f.fase = 'pim'       THEN f.monto ELSE 0.0 END), 0.0)     AS pim,
            COALESCE(SUM(CASE WHEN f.fase = 'devengado' THEN f.monto ELSE 0.0 END), 0.0)     AS devengado
        FROM fact_presupuesto f
        {joins}
        {where_sql}
        GROUP BY 1
        ORDER BY pim DESC
    """
    try:
        df = con.execute(query, params).df()
        logger.info(f"Financing structure: {len(df)} rows retrieved.")
        return df
    except Exception as e:
        logger.error(f"Error querying financing structure: {str(e)}")
        raise


# ----------------------------------------------------
# 8. PROGRAMMATIC ALLOCATION
# Top-N PIM by selected programmatic dimension.
# Always JOINs dim_programatica; conditionally JOINs geography
# and institution based on active filters.
# ----------------------------------------------------
def get_programmatic_allocation_data(
    group_by_level: str,
    limit: int = 10,
    year: Any = None,
    government_level: Any = None,
    sector: Any = None,
    department: Any = None
) -> pd.DataFrame:
    """
    Args:
        group_by_level: 'programa_ppto_nombre', 'producto_proyecto_nombre', or 'funcion_nombre'
        limit: Top N results (default 10)
    Returns:
        DataFrame with columns ['dimension', 'total_monto']
        sorted by total_monto DESC, limited to top N.
    """
    allowed_columns = {"programa_ppto_nombre", "producto_proyecto_nombre", "funcion_nombre"}
    if group_by_level not in allowed_columns:
        raise ValueError(f"Invalid group_by_level: '{group_by_level}'. Must be one of {allowed_columns}.")

    logger.info(f"Querying programmatic allocation by {group_by_level}...")
    con = get_connection()
    where_sql, params = _build_where_clause(year, government_level, sector, department)

    need_geo  = _needs_geo_join(department)
    need_inst = _needs_inst_join(government_level, sector)
    joins     = _build_joins(need_geo=need_geo, need_inst=need_inst, need_prog=True)

    query = f"""
        SELECT
            p.{group_by_level}                                                                 AS dimension,
            COALESCE(SUM(CASE WHEN f.fase = 'pim' THEN f.monto ELSE 0.0 END), 0.0)  AS total_monto
        FROM fact_presupuesto f
        {joins}
        {where_sql}
        GROUP BY 1
        ORDER BY total_monto DESC
        LIMIT {limit}
    """
    try:
        df = con.execute(query, params).df()
        logger.info(f"Programmatic allocation: {len(df)} rows retrieved.")
        return df
    except Exception as e:
        logger.error(f"Error querying programmatic allocation: {str(e)}")
        raise
