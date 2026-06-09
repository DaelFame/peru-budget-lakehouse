"""
National Budget Execution Intelligence App

Streamlit entry point for the Peru Budget Lakehouse executive dashboard.
Coordinates responsive filters in the sidebar control panel with reactive DuckDB
data extraction and premium Plotly Graph Objects visualizations.
"""

import os
import sys
import logging
import json
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
    get_geographic_heatmap_data,
    get_economic_composition_data,
    get_financing_structure_data,
    get_programmatic_allocation_data,
)
from dashboard.components import (
    render_kpi_cards,
    render_top_concentrations,
    render_execution_variance,
    render_geographic_heatmap,
    render_economic_composition,
    render_financing_structure,
    render_programmatic_allocation,
    render_ai_response,
)
from dashboard.theme import LIGHT_COLORS, DARK_COLORS, FONT_FAMILY

# ----------------------------------------------------
# AI RESPONSE DEFENSIVE INTEGRATION HELPERS
# ----------------------------------------------------
def safe_parse_payload(payload):
    """
    Safely parses a payload (dictionary or string) into a valid AI contract dict.
    Returns the parsed dictionary if valid, otherwise None.
    """
    if isinstance(payload, dict):
        if "intent" in payload:
            return payload
        return None

    if not isinstance(payload, str):
        return None

    stripped = payload.strip()
    # Check if we should attempt parsing
    if not (stripped.startswith("{") or stripped.startswith("```json") or ("{" in stripped and "}" in stripped)):
        return None

    # Safely strip markdown fences
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) > 2:
            if lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
        else:
            stripped = stripped.replace("```json", "").replace("```", "").strip()
    else:
        stripped = stripped.strip("`").strip()

    # Extract first { to last }
    try:
        first_brace = stripped.index("{")
        last_brace = stripped.rindex("}")
        stripped = stripped[first_brace:last_brace + 1].strip()
    except ValueError:
        pass

    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict) and "intent" in parsed:
            return parsed
    except Exception:
        pass

    return None


def render_assistant_message(content, lang_dict):
    """
    Renders assistant messages using either the premium visualization dashboard
    or falling back to basic text rendering.
    """
    parsed = safe_parse_payload(content)

    if parsed is not None:
        try:
            render_ai_response(parsed, lang_dict)
            return
        except Exception as e:
            logger.error("Error in render_ai_response execution: %s", e)
            # Silently fall back to text rendering
            pass

    # Fallback rendering path (for plain string responses, errors, welcome messages, etc.)
    if isinstance(content, dict):
        summary = content.get("executive_summary") or content.get("summary")
        if summary:
            st.markdown(summary)
        else:
            st.json(content)
    elif isinstance(content, str):
        st.markdown(content)
    else:
        st.write(content)

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
# THEME-AWARE CSS INJECTION
# ----------------------------------------------------
def _inject_theme_css(colors: dict) -> None:
    """Injects theme-aware CSS using the provided color palette."""
    st.markdown(f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');

        html, body, [class*="css"] {{
            font-family: {FONT_FAMILY};
        }}

        .main-title {{
            font-size: 2.8rem;
            font-weight: 700;
            color: {colors['secondary']};
            margin-bottom: 0.2rem;
            letter-spacing: -0.02em;
        }}

        .subtitle {{
            font-size: 1.2rem;
            font-weight: 400;
            color: {colors['subtitle']};
            margin-bottom: 1.5rem;
        }}

        [data-testid="metric-container"] {{
            background-color: {colors['background_card']};
            border: 1px solid {colors['border']};
            padding: 1.2rem;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.015);
        }}

        [data-testid="metric-container"] label {{
            font-weight: 600 !important;
            color: {colors['card_label']} !important;
            font-size: 1.0rem !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        [data-testid="metric-container"] div[data-testid="stMetricValue"] {{
            font-size: 2.4rem !important;
            font-weight: 700;
            color: {colors['card_value']};
        }}

        .section-title {{
            font-size: 1.6rem;
            font-weight: 600;
            color: {colors['secondary']};
            margin-top: 1rem;
            margin-bottom: 1rem;
        }}

        .section-desc {{
            font-size: 0.9rem;
            color: {colors['subtitle']};
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

@st.cache_data
def cached_economic_composition(year, gov_level, sector, dept):
    return get_economic_composition_data(
        year=year,
        government_level=gov_level,
        sector=sector,
        department=dept
    )

@st.cache_data
def cached_financing_structure(year, gov_level, sector, dept):
    return get_financing_structure_data(
        year=year,
        government_level=gov_level,
        sector=sector,
        department=dept
    )

@st.cache_data
def cached_programmatic_allocation(group_by, year, gov_level, sector, dept):
    return get_programmatic_allocation_data(
        group_by_level=group_by,
        limit=10,
        year=year,
        government_level=gov_level,
        sector=sector,
        department=dept
    )


# ----------------------------------------------------
# MAIN APPLICATION PIPELINE
# ----------------------------------------------------
def main():
    if "pending_prompt" not in st.session_state:
        st.session_state.pending_prompt = None

    # ---- THEME INIT ----
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = False
    colors = DARK_COLORS if st.session_state.dark_mode else LIGHT_COLORS
    st.session_state["ui_colors"] = colors
    _inject_theme_css(colors)

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

            "sec_economic": "Economic Classification Composition",
            "sub_economic": "Budget distribution by economic category (Personnel, Goods & Services, Investment, Debt Service, etc.).",
            "no_economic_data": "No economic composition data found matching the active filters.",

            "sec_financing": "Financing Source Structure",
            "sub_financing": "Budget allocation by financing source (Treasury, Loans, Donations, Direct Revenue, etc.).",
            "no_financing_data": "No financing structure data found matching the active filters.",

            "sec_programmatic": "Programmatic Allocation (Top-N)",
            "sub_programmatic": "Largest budget allocations by program, project, or government function.",
            "toggle_prog": "Group Programmatic By",
            "prog_toggle_options": ["Budget Program", "Project", "Government Function"],
            "no_prog_data": "No programmatic allocation data found matching the active filters.",

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
            "spinner_econ": "Aggregating economic composition...",
            "spinner_fin": "Aggregating financing structure...",
            "spinner_prog": "Aggregating programmatic allocation...",

            # Chart titles & tooltips
            "chart_budget": "Budget",
            "chart_dimension": "Dimension",
            "chart_executed_val": "Executed (Devengado)",
            "chart_planned_val": "Planned (PIM)",

            # AI Chat
            "sec_ai_chat": "AI Budget Analyst",
            "sub_ai_chat": "Ask natural language questions about the budget data. The AI translates your question into SQL, queries the database, and summarizes the results.",
            "chat_input_placeholder": "Ask a question about the budget...",
            "chat_spinner": "Analyzing your question...",
            "ai_chat_disabled": "Set the GROQ_API_KEY environment variable to enable the AI Budget Analyst.",
            "chat_show_sql": "View SQL Query",
            "chat_error_prefix": "Sorry, I could not process your question.",
            "chat_welcome": "Ask me anything about Peru's national budget! For example: \"What was the total PIM for 2024?\" or \"Which sector had the highest execution rate in 2023?\"",
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

            "sec_economic": "Composición por Clasificación Económica",
            "sub_economic": "Distribución presupuestal por categoría económica (Personal, Bienes y Servicios, Inversiones, Servicio de la Deuda, etc.).",
            "no_economic_data": "No se encontraron datos de composición económica que coincidan con los filtros activos.",

            "sec_financing": "Estructura por Fuente de Financiamiento",
            "sub_financing": "Asignación presupuestal por fuente de financiamiento (Tesoro, Préstamos, Donaciones, Recursos Directamente Recaudados, etc.).",
            "no_financing_data": "No se encontraron datos de estructura de financiamiento que coincidan con los filtros activos.",

            "sec_programmatic": "Asignación Programática (Top-N)",
            "sub_programmatic": "Mayores asignaciones presupuestales por programa, proyecto o función de gobierno.",
            "toggle_prog": "Agrupar Programático Por",
            "prog_toggle_options": ["Programa Presupuestal", "Proyecto", "Función de Gobierno"],
            "no_prog_data": "No se encontraron datos de asignación programática que coincidan con los filtros activos.",

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
            "spinner_econ": "Agrupando composición económica...",
            "spinner_fin": "Agrupando estructura de financiamiento...",
            "spinner_prog": "Agrupando asignación programática...",

            # Chart titles & tooltips
            "chart_budget": "Presupuesto",
            "chart_dimension": "Dimensión",
            "chart_executed_val": "Ejecutado (Devengado)",
            "chart_planned_val": "Planificado (PIM)",

            # AI Chat
            "sec_ai_chat": "Analista Presupuestal IA",
            "sub_ai_chat": "Haga preguntas en lenguaje natural sobre los datos presupuestarios. La IA traduce su pregunta a SQL, consulta la base de datos y resume los resultados.",
            "chat_input_placeholder": "Haga una pregunta sobre el presupuesto...",
            "chat_spinner": "Analizando su pregunta...",
            "ai_chat_disabled": "Configure la variable GROQ_API_KEY para habilitar el Analista Presupuestal IA.",
            "chat_show_sql": "Ver Consulta SQL",
            "chat_error_prefix": "Lo siento, no pude procesar su pregunta.",
            "chat_welcome": "¡Pregúnteme cualquier cosa sobre el presupuesto nacional de Perú! Por ejemplo: \"¿Cuál fue el PIM total para 2024?\" o \"¿Qué sector tuvo la tasa de ejecución más alta en 2023?\"",
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

    # Dark mode toggle
    st.sidebar.markdown("---")
    dark_mode = st.sidebar.checkbox("🌓 Dark Mode", value=st.session_state.dark_mode)
    if dark_mode != st.session_state.dark_mode:
        st.session_state.dark_mode = dark_mode
        st.rerun()

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
    # LAYER 2: ECONOMIC COMPOSITION (FULL WIDTH)
    # ----------------------------------------------------
    st.markdown(f'<div class="section-title">{LANG["sec_economic"]}</div>', unsafe_allow_html=True)
    st.markdown(
        f"<div class='section-desc'>"
        f"{LANG['sub_economic']}"
        f"</div>",
        unsafe_allow_html=True
    )

    with st.spinner(LANG["spinner_econ"]):
        df_econ = cached_economic_composition(
            year=year_filter,
            gov_level=gov_filter,
            sector=sector_filter,
            dept=dept_filter
        )

    if not df_econ.empty:
        render_economic_composition(df_econ, LANG)
    else:
        st.info(LANG["no_economic_data"])

    st.markdown("---")

    # ----------------------------------------------------
    # LAYER 3: ALLOCATION & VARIANCE CHARTS (SIDE-BY-SIDE)
    # ----------------------------------------------------
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.markdown(f'<div class="section-title">{LANG["sec_concentrations"]}</div>', unsafe_allow_html=True)
        st.markdown(
            f"<div class='section-desc'>"
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
            f"<div class='section-desc'>"
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
    # LAYER 4: FINANCING STRUCTURE & PROGRAMMATIC ALLOCATION (SIDE-BY-SIDE)
    # ----------------------------------------------------
    fin_col1, fin_col2 = st.columns(2)

    with fin_col1:
        st.markdown(f'<div class="section-title">{LANG["sec_financing"]}</div>', unsafe_allow_html=True)
        st.markdown(
            f"<div class='section-desc'>"
            f"{LANG['sub_financing']}"
            f"</div>",
            unsafe_allow_html=True
        )

        with st.spinner(LANG["spinner_fin"]):
            df_fin = cached_financing_structure(
                year=year_filter,
                gov_level=gov_filter,
                sector=sector_filter,
                dept=dept_filter
            )

        if not df_fin.empty:
            render_financing_structure(df_fin, LANG)
        else:
            st.info(LANG["no_financing_data"])

    with fin_col2:
        st.markdown(f'<div class="section-title">{LANG["sec_programmatic"]}</div>', unsafe_allow_html=True)
        st.markdown(
            f"<div class='section-desc'>"
            f"{LANG['sub_programmatic']}"
            f"</div>",
            unsafe_allow_html=True
        )

        prog_toggle = st.selectbox(
            LANG["toggle_prog"],
            options=LANG["prog_toggle_options"],
            index=0,
            key="prog_toggle",
            label_visibility="collapsed"
        )
        prog_column = {
            LANG["prog_toggle_options"][0]: "programa_ppto_nombre",
            LANG["prog_toggle_options"][1]: "producto_proyecto_nombre",
            LANG["prog_toggle_options"][2]: "funcion_nombre",
        }[prog_toggle]

        with st.spinner(LANG["spinner_prog"]):
            df_prog = cached_programmatic_allocation(
                group_by=prog_column,
                year=year_filter,
                gov_level=gov_filter,
                sector=sector_filter,
                dept=dept_filter
            )

        if not df_prog.empty:
            render_programmatic_allocation(df_prog, LANG)
        else:
            st.info(LANG["no_prog_data"])

    st.markdown("---")

    # ----------------------------------------------------
    # LAYER 5: GEOGRAPHIC ACCOUNTABILITY MATRIX (HEATMAP)
    # ----------------------------------------------------
    st.markdown(f'<div class="section-title">{LANG["sec_heatmap"]}</div>', unsafe_allow_html=True)
    st.markdown(
        f"<div class='section-desc'>"
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

    # ----------------------------------------------------
    # LAYER 6: AI-POWERED CONVERSATIONAL BUDGET ANALYST
    # ----------------------------------------------------
    st.markdown("---")
    st.markdown(f'<div class="section-title">{LANG["sec_ai_chat"]}</div>', unsafe_allow_html=True)
    st.markdown(
        f"<div class='section-desc'>"
        f"{LANG['sub_ai_chat']}"
        f"</div>",
        unsafe_allow_html=True
    )

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        st.info(LANG["ai_chat_disabled"])
    else:
        lazy_init_engine(api_key)
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                if msg["role"] == "user":
                    st.markdown(msg["content"])
                else:
                    render_assistant_message(msg["content"], LANG)

        if not st.session_state.chat_history:
            with st.chat_message("assistant"):
                render_assistant_message(LANG["chat_welcome"], LANG)

        active_prompt = None
        if st.session_state.get("pending_prompt"):
            active_prompt = st.session_state.pending_prompt
            # ATOMIC CONSUMPTION
            st.session_state.pending_prompt = None
        else:
            active_prompt = st.chat_input(LANG["chat_input_placeholder"])

        if active_prompt:
            st.session_state.chat_history.append({"role": "user", "content": active_prompt})
            with st.chat_message("user"):
                st.markdown(active_prompt)

            with st.chat_message("assistant"):
                with st.spinner(LANG["chat_spinner"]):
                    chat_lang = "es" if LANG["lang_name"] == "Español" else "en"

                    # Convert any dictionary content to string for the LLM history to avoid API crash
                    sanitized_history = []
                    for msg in st.session_state.chat_history[:-1]:
                        msg_copy = msg.copy()
                        if isinstance(msg_copy["content"], dict):
                            summary = msg_copy["content"].get("executive_summary") or msg_copy["content"].get("summary")
                            if not summary:
                                summary = json.dumps(msg_copy["content"], ensure_ascii=False)
                            msg_copy["content"] = summary
                        sanitized_history.append(msg_copy)

                    result = st.session_state.ai_engine.ask(
                        question=active_prompt,
                        lang=chat_lang,
                        conversation_history=sanitized_history,
                    )

                if result["success"]:
                    render_assistant_message(result["summary"], LANG)
                    response_text = result["summary"]
                else:
                    msg = f"{LANG['chat_error_prefix']}: {result['error']}"
                    st.error(msg)
                    response_text = msg

            st.session_state.chat_history.append(
                {"role": "assistant", "content": response_text}
            )


def lazy_init_engine(api_key: str) -> None:
    """Initialises the AIEngine once and caches it in session state."""
    if "ai_engine" in st.session_state:
        return
    from dashboard.database import get_connection
    from dashboard.ai_engine import AIEngine
    st.session_state.ai_engine = AIEngine(
        api_key=api_key,
        db_connect_fn=get_connection,
    )


if __name__ == "__main__":
    main()
