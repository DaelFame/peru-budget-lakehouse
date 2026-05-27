"""
National Budget Execution Intelligence App

Streamlit entry point for the Peru Budget Lakehouse executive dashboard.
Coordinates responsive filters in the sidebar control panel with reactive DuckDB
data extraction and premium Plotly Graph Objects visualizations.
"""

import os
import sys
import logging
import streamlit as st

# Professional logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

# 1. ENVIRONMENT PATHING (Discover src/ packages cleanly)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

# Import decoupled database query and component rendering modules
from dashboard.database import (
    load_filters_data,
    load_dashboard_metrics,
    get_top_concentrations_data,
    get_execution_variance_data,
    get_geographic_heatmap_data
)
from dashboard.components import (
    render_kpi_cards,
    render_top_concentrations,
    render_execution_variance,
    render_geographic_heatmap
)
from dashboard.theme import UI_COLORS, FONT_FAMILY

# ----------------------------------------------------
# STREAMLIT PAGE CONFIGURATION
# ----------------------------------------------------
st.set_page_config(
    page_title="National Budget Execution Intelligence",
    page_icon="🇵🇪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------------------------------------------
# HIGH-END FINANCIAL TERMINAL TYPOGRAPHY & CARD STYLING
# ----------------------------------------------------
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {{
        font-family: {FONT_FAMILY};
    }}
    
    .main-title {{
        font-size: 2.8rem;
        font-weight: 700;
        color: {UI_COLORS['secondary']};
        margin-bottom: 0.2rem;
        letter-spacing: -0.02em;
    }}
    
    .subtitle {{
        font-size: 1.2rem;
        font-weight: 400;
        color: #64748b;
        margin-bottom: 1.5rem;
    }}
    
    /* Premium boardroom border-free metric cards */
    [data-testid="metric-container"] {{
        background-color: {UI_COLORS['background_card']};
        border: 1px solid {UI_COLORS['border']};
        padding: 1.2rem;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.015);
    }}
    
    [data-testid="metric-container"] label {{
        font-weight: 600 !important;
        color: #1E293B !important;
        font-size: 1.0rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}
    
    [data-testid="metric-container"] div[data-testid="stMetricValue"] {{
        font-size: 2.4rem !important;
        font-weight: 700;
        color: #1E293B !important;
    }}

    /* Underperforming execution rate warning element styling */
    [data-testid="metric-container"] div[data-testid="stMetricDelta"] {{
        color: #EF4444 !important;
        font-size: 0.95rem !important;
        font-weight: 600 !important;
    }}
    
    /* Clean sections titles styling */
    .section-title {{
        font-size: 1.6rem;
        font-weight: 600;
        color: {UI_COLORS['secondary']};
        margin-top: 1rem;
        margin-bottom: 1rem;
    }}
    </style>
""", unsafe_allow_html=True)


# ----------------------------------------------------
# REACTIVE CACHING LAYER (MAXIMIZES RESPONSIVENESS)
# ----------------------------------------------------
@st.cache_data
def cached_load_filters():
    return load_filters_data()

@st.cache_data
def cached_metrics(year, gov_level, sector, dept):
    return load_dashboard_metrics(
        year=year,
        government_level=gov_level,
        sector=sector,
        department=dept
    )

@st.cache_data
def cached_top_concentrations(group_by, year, gov_level, sector, dept):
    return get_top_concentrations_data(
        group_by_column=group_by,
        limit=10,
        year=year,
        government_level=gov_level,
        sector=sector,
        department=dept
    )

@st.cache_data
def cached_execution_variance(dimension, year, gov_level, sector, dept):
    return get_execution_variance_data(
        dimension_column=dimension,
        year=year,
        government_level=gov_level,
        sector=sector,
        department=dept
    )

@st.cache_data
def cached_geographic_heatmap(year, gov_level, sector, dept):
    return get_geographic_heatmap_data(
        year=year,
        government_level=gov_level,
        sector=sector,
        department=dept
    )


# ----------------------------------------------------
# MAIN APPLICATION PIPELINE
# ----------------------------------------------------
def main():
    # Load and initialize control panel filters from the DuckDB gold layers
    try:
        filters = cached_load_filters()
    except Exception as e:
        st.error(f"Failed to initialize database filters: {str(e)}")
        return

    # ----------------------------------------------------
    # RUNTIME INTERNATIONALIZATION (i18n) ENGINE
    # ----------------------------------------------------
    lang_selection = st.sidebar.selectbox("🌐 Language / Idioma", ["English (US)", "Español (PE)"])

    if lang_selection == "English (US)":
        LANG = {
            "lang_name": "English",
            "sidebar_title": "📊 Control Panel",
            "sidebar_info": "Configure the filters below to slice national budget allocations and analyze execution performance in real-time.",
            "reset_filters": "Reset Filters",
            "fiscal_year": "Fiscal Year",
            "gov_level": "Government Level",
            "sector": "Executive Sector",
            "dept": "Executing Department",
            "footer": "Peru Budget Lakehouse • Executive Dashboard v2.0",
            
            "main_title": "🇵🇪 National Budget Execution Intelligence",
            "subtitle": "Boardroom-Grade Financial Dashboard & Public Expenditure Accountability",
            "empty_state": "⚠️ No records found matching the active criteria. Please adjust your Control Panel filters in the sidebar.",
            
            "sec_kpis": "Core Performance Indicators",
            "kpi_pim": "Total Planned Budget (PIM)",
            "kpi_executed": "Total Executed Budget",
            "kpi_rate": "Budget Execution Rate",
            "kpi_gap": "Unexecuted Budget Gap",
            "execution_warning": "⚠️ Low Execution (< 50%)",
            
            "sec_concentrations": "Top Budget Concentrations",
            "sub_concentrations": "Identifies the highest budget concentrations. Choose Sector or Department below to group.",
            "toggle_conc": "Group Concentrations By",
            "toggle_options": ["Sector", "Department"],
            "no_conc_data": "No concentration data found matching the active filters.",
            
            "sec_variance": "Budget Execution Variance",
            "sub_variance": "Compares Planned (PIM) vs Executed (Devengado) values. Choose a dimension below.",
            "toggle_var": "Group Variance By",
            "no_var_data": "No comparative variance data found matching the active filters.",
            
            "sec_heatmap": "Geographic Accountability Matrix",
            "sub_heatmap": "Heatmap distribution illustrating execution rates (%) grouped by Executing Department across all available Fiscal Years. Muted shades indicate lower output levels, and deeper Crimson represents solid progress.",
            "no_heatmap_data": "No geographic heatmap data found matching the active filters.",
            
            # Financial/Formatting mappings
            "billions_symbol": "B",
            "millions_symbol": "M",
            "trillions_symbol": "T",
            "plotly_fmt": ".3s",
            "legend_pim": "Planned Budget (PIM)",
            "legend_dev": "Executed Budget (Dev)",
            "conc_margin_r": 110,
            
            # Spinners
            "spinner_metrics": "Extracting financial metrics...",
            "spinner_conc": "Aggregating concentration data...",
            "spinner_var": "Aggregating comparative variance...",
            "spinner_geo": "Generating geographic heatmap...",
            
            # Chart titles & tooltips
            "chart_budget": "Budget",
            "chart_dimension": "Dimension",
            "chart_executed_val": "Executed (Devengado)",
            "chart_planned_val": "Planned (PIM)",
        }
    else:
        LANG = {
            "lang_name": "Español",
            "sidebar_title": "📊 Panel de Control",
            "sidebar_info": "Configure los filtros a continuación para segmentar las asignaciones presupuestarias nacionales y analizar el desempeño de la ejecución en tiempo real.",
            "reset_filters": "Restablecer Filtros",
            "fiscal_year": "Año Fiscal",
            "gov_level": "Nivel de Gobierno",
            "sector": "Sector Ejecutivo",
            "dept": "Departamento Ejecutor",
            "footer": "Peru Budget Lakehouse • Dashboard Ejecutivo v2.0",
            
            "main_title": "🇵🇪 Inteligencia de Ejecución del Presupuesto Nacional",
            "subtitle": "Dashboard Financiero de Nivel Directivo y Rendición de Cuentas del Gasto Público",
            "empty_state": "⚠️ No se encontraron registros que coincidan con los criterios activos. Por favor, ajuste los filtros del Panel de Control en la barra lateral.",
            
            "sec_kpis": "Indicadores Clave de Desempeño",
            "kpi_pim": "Presupuesto Programado Total (PIM)",
            "kpi_executed": "Presupuesto Ejecutado Total",
            "kpi_rate": "Tasa de Ejecución Presupuestal",
            "kpi_gap": "Brecha de Presupuesto No Ejecutado",
            "execution_warning": "⚠️ Baja Ejecución (< 50%)",
            
            "sec_concentrations": "Principales Concentraciones Presupuestales",
            "sub_concentrations": "Identifica las mayores concentraciones presupuestarias. Seleccione Sector o Departamento a continuación para agrupar.",
            "toggle_conc": "Agrupar Concentraciones Por",
            "toggle_options": ["Sector", "Departamento"],
            "no_conc_data": "No se encontraron datos de concentración que coincidan con los filtros activos.",
            
            "sec_variance": "Variación de la Ejecución Presupuestal",
            "sub_variance": "Compara los valores Programados (PIM) vs Ejecutados (Devengado). Seleccione una dimensión a continuación.",
            "toggle_var": "Agrupar Variación Por",
            "no_var_data": "No se encontraron datos de variación comparativa que coincidan con los filtros activos.",
            
            "sec_heatmap": "Matriz de Responsabilidad Geográfica",
            "sub_heatmap": "Distribución del mapa de calor que ilustra las tasas de ejecución (%) agrupadas por Departamento Ejecutor a lo largo de todos los Años Fiscales disponibles. Los tonos tenues indican niveles de producción más bajos, y el carmesí más profundo representa un progreso sólido.",
            "no_heatmap_data": "No se encontraron datos del mapa de calor geográfico que coincidan con los filtros activos.",
            
            # Financial/Formatting mappings
            "billions_symbol": "Mil MM",
            "millions_symbol": "Millones",
            "trillions_symbol": "Billones",
            "plotly_fmt": ",.0f",
            "legend_pim": "Presupuesto Programado (PIM)",
            "legend_dev": "Presupuesto Ejecutado (Dev)",
            "conc_margin_r": 160,
            
            # Spinners
            "spinner_metrics": "Extrayendo métricas financieras...",
            "spinner_conc": "Agrupando datos de concentración...",
            "spinner_var": "Agrupando variación comparativa...",
            "spinner_geo": "Generando mapa de calor geográfico...",
            
            # Chart titles & tooltips
            "chart_budget": "Presupuesto",
            "chart_dimension": "Dimensión",
            "chart_executed_val": "Ejecutado (Devengado)",
            "chart_planned_val": "Planificado (PIM)",
        }

    # ----------------------------------------------------
    # SIDEBAR CONTROL PANEL
    # ----------------------------------------------------
    st.sidebar.markdown(f"### {LANG['sidebar_title']}")
    st.sidebar.info(LANG["sidebar_info"])

    # Reset mechanism inside Sidebar - Updated to modern layout 'width="stretch"' parameter
    if st.sidebar.button(LANG["reset_filters"], width="stretch"):
        st.session_state["year_filter"] = "ALL"
        st.session_state["gov_filter"] = "ALL"
        st.session_state["sector_filter"] = "ALL"
        st.session_state["dept_filter"] = "ALL"

    # Default to the most recent year if available
    default_year_idx = 1 if len(filters["years"]) > 0 else 0

    year_filter = st.sidebar.selectbox(
        LANG["fiscal_year"],
        options=["ALL"] + filters["years"],
        index=default_year_idx,
        key="year_filter"
    )

    gov_filter = st.sidebar.selectbox(
        LANG["gov_level"],
        options=["ALL"] + filters["government_levels"],
        key="gov_filter"
    )

    sector_filter = st.sidebar.selectbox(
        LANG["sector"],
        options=["ALL"] + filters["sectors"],
        key="sector_filter"
    )

    dept_filter = st.sidebar.selectbox(
        LANG["dept"],
        options=["ALL"] + filters["departments"],
        key="dept_filter"
    )

    # Footer attribution
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        f"<div style='font-size:0.8rem; color:#94a3b8; text-align:center;'>"
        f"{LANG['footer']}"
        f"</div>",
        unsafe_allow_html=True
    )

    # ----------------------------------------------------
    # HEADER LAYOUT
    # ----------------------------------------------------
    st.markdown(f'<div class="main-title">{LANG["main_title"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="subtitle">{LANG["subtitle"]}</div>', unsafe_allow_html=True)
    st.markdown("---")

    # ----------------------------------------------------
    # REACTIVE PIPELINE RUN
    # ----------------------------------------------------
    with st.spinner(LANG["spinner_metrics"]):
        metrics = cached_metrics(
            year=year_filter,
            gov_level=gov_filter,
            sector=sector_filter,
            dept=dept_filter
        )

    # PRODUCTION HARDENING (Defensive Empty State Check)
    if metrics["pim"] == 0.0 and metrics["devengado"] == 0.0:
        st.warning(LANG["empty_state"])
        return

    # ----------------------------------------------------
    # LAYER 1: EXECUTIVE OVERVIEW (KPI CARDS)
    # ----------------------------------------------------
    st.markdown(f'<div class="section-title">{LANG["sec_kpis"]}</div>', unsafe_allow_html=True)
    render_kpi_cards(metrics, LANG)
    st.markdown("---")

    # ----------------------------------------------------
    # LAYER 2: ALLOCATION & VARIANCE CHARTS (SIDE-BY-SIDE)
    # ----------------------------------------------------
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.markdown(f'<div class="section-title">{LANG["sec_concentrations"]}</div>', unsafe_allow_html=True)
        st.markdown(
            f"<div style='font-size:0.9rem; color:#64748b; margin-bottom:1rem;'>"
            f"{LANG['sub_concentrations']}"
            f"</div>",
            unsafe_allow_html=True
        )
        
        # Interactive Dimension Toggle
        conc_toggle = st.selectbox(
            LANG["toggle_conc"],
            options=LANG["toggle_options"],
            index=0,
            key="conc_toggle",
            label_visibility="collapsed"
        )
        group_column = "sector_nombre" if conc_toggle == LANG["toggle_options"][0] else "departamento_ejecutora_nombre"
        
        with st.spinner(LANG["spinner_conc"]):
            df_conc = cached_top_concentrations(
                group_by=group_column,
                year=year_filter,
                gov_level=gov_filter,
                sector=sector_filter,
                dept=dept_filter
            )

        if not df_conc.empty:
            render_top_concentrations(df_conc, LANG)
        else:
            st.info(LANG["no_conc_data"])

    with chart_col2:
        st.markdown(f'<div class="section-title">{LANG["sec_variance"]}</div>', unsafe_allow_html=True)
        st.markdown(
            f"<div style='font-size:0.9rem; color:#64748b; margin-bottom:1rem;'>"
            f"{LANG['sub_variance']}"
            f"</div>",
            unsafe_allow_html=True
        )

        # Interactive Dimension Toggle (defaulting to Department for comparative variety)
        var_toggle = st.selectbox(
            LANG["toggle_var"],
            options=LANG["toggle_options"],
            index=1,
            key="var_toggle",
            label_visibility="collapsed"
        )
        var_column = "sector_nombre" if var_toggle == LANG["toggle_options"][0] else "departamento_ejecutora_nombre"

        with st.spinner(LANG["spinner_var"]):
            df_var = cached_execution_variance(
                dimension=var_column,
                year=year_filter,
                gov_level=gov_filter,
                sector=sector_filter,
                dept=dept_filter
            )

        if not df_var.empty:
            render_execution_variance(df_var, LANG)
        else:
            st.info(LANG["no_var_data"])

    st.markdown("---")

    # ----------------------------------------------------
    # LAYER 3: GEOGRAPHIC ACCOUNTABILITY MATRIX (HEATMAP)
    # ----------------------------------------------------
    st.markdown(f'<div class="section-title">{LANG["sec_heatmap"]}</div>', unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:0.9rem; color:#64748b; margin-bottom:1rem;'>"
        f"{LANG['sub_heatmap']}"
        f"</div>",
        unsafe_allow_html=True
    )

    with st.spinner(LANG["spinner_geo"]):
        df_geo = cached_geographic_heatmap(
            year=year_filter,
            gov_level=gov_filter,
            sector=sector_filter,
            dept=dept_filter
        )

    if not df_geo.empty:
        render_geographic_heatmap(df_geo)
    else:
        st.info(LANG["no_heatmap_data"])


if __name__ == "__main__":
    main()