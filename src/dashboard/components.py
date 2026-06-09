"""
Executive Dashboard Frontend Components Module

Handles premium UI rendering using Streamlit and Plotly. It is styled and colored
following an elite, high data-to-ink ratio presentation strategy (minimal grids,
clear visual hierarchies, and high contrast labels).
"""

import logging
from typing import Dict

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# Professional logging
logger = logging.getLogger(__name__)

# Try importing standard theme or fallback gracefully
try:
    from theme import LIGHT_COLORS, DARK_COLORS
except ImportError:
    try:
        from src.dashboard.theme import LIGHT_COLORS, DARK_COLORS
    except ImportError:
        LIGHT_COLORS = {
            "primary": "#8B0000",
            "secondary": "#1E293B",
            "background_card": "#F8FAFC",
            "border": "#E2E8F0",
            "success": "#10B981",
            "warning": "#F59E0B",
            "danger": "#EF4444",
            "bar_neutral": "#CBD5E1",
            "bar_muted": "#94A3B8",
            "subtitle": "#64748b",
            "card_label": "#1E293B",
            "card_value": "#1E293B",
        }
        DARK_COLORS = {
            "primary": "#CD5C5C",
            "secondary": "#E2E8F0",
            "background_card": "#1E293B",
            "border": "#334155",
            "success": "#34D399",
            "warning": "#FBBF24",
            "danger": "#F87171",
            "bar_neutral": "#475569",
            "bar_muted": "#64748B",
            "subtitle": "#94A3B8",
            "card_label": "#E2E8F0",
            "card_value": "#F1F5F9",
        }


def _get_colors():
    """Returns the active color palette from Streamlit session state."""
    try:
        import streamlit as st
        return st.session_state.get("ui_colors", LIGHT_COLORS)
    except Exception:
        return LIGHT_COLORS

logger.info("Successfully configured component themes.")


# ----------------------------------------------------
# 0a. EXECUTION RATE COLOR HELPER
# ----------------------------------------------------
def get_execution_rate_color(execution_rate: float) -> str:
    """
    Maps an execution rate (0-100) to the corresponding _get_colors() string
    using a three-tier threshold system:

        >= 75.0  -> success (green)
        40.0-74.9 -> warning (amber)
         < 40.0  -> danger  (red)
    """
    if execution_rate >= 75.0:
        return _get_colors()["success"]
    if execution_rate >= 40.0:
        return _get_colors()["warning"]
    return _get_colors()["danger"]


# ----------------------------------------------------
# 0b. CURRENCY FORMATTING HELPER
# ----------------------------------------------------
def format_boardroom_currency(value: float, lang_dict: dict = None) -> str:
    """
    Boardroom-grade currency formatter to cleanly abbreviate financial scales
    into Trillions (T / Billones), Billions (B / Mil MM), or Millions (M / Millones)
    using 2 decimal places and localized suffixes.
    """
    if lang_dict is None:
        lang_dict = {}
    abs_val = abs(value)
    suffix = ""
    scaled_value = value

    if abs_val >= 1e12:
        scaled_value = value / 1e12
        suffix = f" {lang_dict.get('trillions_symbol', 'T')}"
    elif abs_val >= 1e9:
        scaled_value = value / 1e9
        suffix = f" {lang_dict.get('billions_symbol', 'B')}"
    elif abs_val >= 1e6:
        scaled_value = value / 1e6
        suffix = f" {lang_dict.get('millions_symbol', 'M')}"

    return f"S/. {scaled_value:,.2f}{suffix}"


# ----------------------------------------------------
# 1. CORE KPI CARDS COMPONENT
# ----------------------------------------------------
def render_kpi_cards(metrics_dict: Dict[str, float], lang_dict: dict = None) -> None:
    """
    Renders the 4 Core KPI cards cleanly across 4 columns without card borders,
    maximizing typographical clarity and data prominence.

    KPIs Displayed:
        1. Total Planned Budget (PIM) - Formatted as Soles (S/.)
        2. Total Executed Budget (DEVENGADO) - Formatted as Soles (S/.)
        3. Budget Execution Rate (%) - Formatted as "XX.X%"
        4. Unexecuted Budget Gap - Formatted as Soles (S/.)

    Args:
        metrics_dict (Dict[str, float]): Dictionary containing 'pim', 'devengado',
                                         'execution_rate', and 'unexecuted_gap'.
        lang_dict (dict): Dictionary with active language keys.
    """
    if lang_dict is None:
        lang_dict = {}
    cols = st.columns(4)

    pim = metrics_dict.get("pim", 0.0)
    devengado = metrics_dict.get("devengado", 0.0)
    execution_rate = metrics_dict.get("execution_rate", 0.0)
    unexecuted_gap = metrics_dict.get("unexecuted_gap", 0.0)

    # Format values as human-readable currencies or percentages
    pim_str = format_boardroom_currency(pim, lang_dict)
    dev_str = format_boardroom_currency(devengado, lang_dict)
    rate_str = f"{execution_rate:.1f}%"
    gap_str = format_boardroom_currency(unexecuted_gap, lang_dict)

    with cols[0]:
        st.metric(label=lang_dict.get("kpi_pim", "Total Planned Budget (PIM)"), value=pim_str)
    with cols[1]:
        st.metric(label=lang_dict.get("kpi_executed", "Total Executed Budget"), value=dev_str)
    with cols[2]:
        target_dev = execution_rate - 75.0
        st.metric(
            label=lang_dict.get("kpi_rate", "Budget Execution Rate"),
            value=rate_str,
            delta=f"{target_dev:+.1f}pp",
            delta_color="normal"
        )
    with cols[3]:
        st.metric(label=lang_dict.get("kpi_gap", "Unexecuted Budget Gap"), value=gap_str)


# ----------------------------------------------------
# 2. CHART 1: HORIZONTAL CONCENTRATION BARS
# ----------------------------------------------------
def render_top_concentrations(df: pd.DataFrame, lang_dict: dict = None) -> None:
    """
    Renders a high data-to-ink ratio horizontal bar chart.
    Sorts categories descending, places value labels directly beside the bars,
    hides all distracting gridlines, and highlights ONLY the top 1 bar with the primary accent color.

    Args:
        df (pd.DataFrame): DataFrame with columns ['dimension', 'total_monto'].
        lang_dict (dict): Dictionary with active language keys.
    """
    if lang_dict is None:
        lang_dict = {}
    if df.empty:
        st.warning(lang_dict.get("no_conc_data", "No concentration data found matching the active filters."))
        return

    # Work on a copy and clean labels
    df_clean = df.copy()
    df_clean["dimension"] = df_clean["dimension"].fillna("Unspecified").astype(str)

    # Sort ascending for correct bottom-to-top rendering in Plotly
    df_clean = df_clean.sort_values(by="total_monto", ascending=True)

    n_bars = len(df_clean)
    if n_bars == 0:
        return

    # Apply a monochrome strategy where only the top 1 bar gets the primary accent
    bar_colors = ["#CBD5E1"] * n_bars  # Soft neutral gray for non-top bars
    bar_colors[-1] = _get_colors().get("primary", "#8B0000")  # Top bar highlighted

    # Bind the custom currency helper to the text field
    text_labels = df_clean["total_monto"].apply(lambda v: f" {format_boardroom_currency(v, lang_dict)}")

    # Hover template using localized labels
    hovertemplate = f"{lang_dict.get('chart_dimension', 'Dimension')}: %{{y}}<br>{lang_dict.get('chart_budget', 'Budget')}: %{{x:,.0f}}<extra></extra>"

    fig = go.Figure(
        go.Bar(
            x=df_clean["total_monto"],
            y=df_clean["dimension"],
            orientation="h",
            marker=dict(color=bar_colors),
            text=text_labels,
            textposition="outside",
            cliponaxis=False,
            hovertemplate=hovertemplate
        )
    )

    # Dynamically expand the right margin to perfectly accommodate abbreviated text labels
    margin_r = lang_dict.get("conc_margin_r", 110)

    fig.update_layout(
        xaxis=dict(
            showgrid=False,
            visible=False,  # Completely hide x-axis line & ticks as values are placed on bars
        ),
        yaxis=dict(
            showgrid=False,
            showline=False,
            tickfont=dict(size=12, color=_get_colors().get("secondary", "#1E293B")),
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=margin_r, t=10, b=10),
        height=350,
    )

    # Compliant with latest Streamlit parameters (width="stretch")
    st.plotly_chart(fig, width="stretch")


# ----------------------------------------------------
# 3. CHART 2: EXECUTION VARIANCE COMPARISON
# ----------------------------------------------------
def render_execution_variance(df: pd.DataFrame, lang_dict: dict = None) -> None:
    """
    Renders a grouped horizontal bar chart comparing Planned (PIM) vs Executed (Devengado).
    Keeps legends clear, and removes background grids to maximize contrast.

    Args:
        df (pd.DataFrame): DataFrame with columns ['dimension', 'pim', 'devengado'].
        lang_dict (dict): Dictionary with active language keys.
    """
    if lang_dict is None:
        lang_dict = {}
    if df.empty:
        st.warning(lang_dict.get("no_var_data", "No comparative variance data found matching the active filters."))
        return

    # Work on a copy and clean labels
    df_clean = df.copy()
    df_clean["dimension"] = df_clean["dimension"].fillna("Unspecified").astype(str)

    # Sort by PIM ascending to place the largest items at the top of the chart
    df_clean = df_clean.sort_values(by="pim", ascending=True)

    # Limit to top 10 categories to avoid visual pollution/crowding
    df_clean = df_clean.tail(10)

    fig = go.Figure()

    plotly_fmt = lang_dict.get("plotly_fmt", ",.0f")

    # Planned Budget (PIM) Trace - Soft Muted Gray
    fig.add_trace(
        go.Bar(
            name=lang_dict.get("legend_pim", "Planned Budget (PIM)"),
            y=df_clean["dimension"],
            x=df_clean["pim"],
            orientation="h",
            marker=dict(color="#94A3B8"),
            hovertemplate=f"{lang_dict.get('chart_planned_val', 'Planned (PIM)')}: S/. %{{x:{plotly_fmt}}}<extra></extra>"
        )
    )

    # Executed Budget (Devengado) Trace - Primary Crimson Accent
    fig.add_trace(
        go.Bar(
            name=lang_dict.get("legend_dev", "Executed Budget (Dev)"),
            y=df_clean["dimension"],
            x=df_clean["devengado"],
            orientation="h",
            marker=dict(color=_get_colors().get("primary", "#8B0000")),
            hovertemplate=f"{lang_dict.get('chart_executed_val', 'Executed (Devengado)')}: S/. %{{x:{plotly_fmt}}}<extra></extra>"
        )
    )

    fig.update_layout(
        barmode="group",
        xaxis=dict(
            showgrid=False,
            visible=False,  # Maximize data-to-ink ratio
        ),
        yaxis=dict(
            showgrid=False,
            showline=False,
            tickfont=dict(size=12, color=_get_colors().get("secondary", "#1E293B")),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11, color=_get_colors().get("secondary", "#1E293B")),
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=40, b=10),
        height=400,
    )

    # Compliant with latest Streamlit parameters (width="stretch")
    st.plotly_chart(fig, width="stretch")


# ----------------------------------------------------
# 4. CHART 3: GEOGRAPHIC EXECUTION HEATMAP
# ----------------------------------------------------
def render_geographic_heatmap(df: pd.DataFrame) -> None:
    """
    Renders a high-contrast sequential heatmap showing budget execution rates
    grouped by department (y-axis) over fiscal years (x-axis).
    Uses a restrained gradient palette.

    Args:
        df (pd.DataFrame): DataFrame with columns:
                           ['department', 'fiscal_year', 'pim', 'devengado', 'execution_rate'].
    """
    if df.empty:
        st.warning("No geographic heatmap data found.")
        return

    # Clean and parse types
    df_clean = df.copy()
    df_clean["department"] = df_clean["department"].fillna("Unspecified").astype(str)
    df_clean["fiscal_year"] = df_clean["fiscal_year"].astype(str)
    df_clean["execution_rate"] = df_clean["execution_rate"].fillna(0.0)

    # Pivot department names as index and years as columns
    pivot_df = df_clean.pivot(
        index="department",
        columns="fiscal_year",
        values="execution_rate"
    ).fillna(0.0)

    # Sort index descending so departments are alphabetical from top to bottom
    pivot_df = pivot_df.sort_index(ascending=False)

    # Elegant single restrained gradient from clean background gray to executive primary
    colorscale = [
        [0.0, "#F8FAFC"],
        [1.0, _get_colors().get("primary", "#8B0000")]
    ]

    # FIX: Configured colorbar using modern nested dictionary structure to resolve Plotly crash
    colorbar_config = dict(
        title=dict(
            text="Rate (%)",
            side="top"
        ),
        thickness=12,
        len=0.5,
        tickfont=dict(size=10, color=_get_colors().get("secondary", "#1E293B")),
    )

    fig = go.Figure(
        data=go.Heatmap(
            z=pivot_df.values,
            x=pivot_df.columns.tolist(),
            y=pivot_df.index.tolist(),
            colorscale=colorscale,
            colorbar=colorbar_config,
            hovertemplate="Department: %{y}<br>Year: %{x}<br>Execution Rate: %{z:.1f}%<extra></extra>"
        )
    )

    # Place years at the top for clean, matrix-style visual reports
    fig.update_layout(
        xaxis=dict(
            showgrid=False,
            showline=False,
            side="top",
            tickfont=dict(size=11, color=_get_colors().get("secondary", "#1E293B")),
        ),
        yaxis=dict(
            showgrid=False,
            showline=False,
            tickfont=dict(size=11, color=_get_colors().get("secondary", "#1E293B")),
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=40, b=10),
        height=500,
    )

    # Compliant with latest Streamlit parameters (width="stretch")
    st.plotly_chart(fig, width="stretch")


# ----------------------------------------------------
# 5. ECONOMIC COMPOSITION CHART
# Stacked horizontal bar: economic category × PIM vs Devengado.
# ----------------------------------------------------
def render_economic_composition(df: pd.DataFrame, lang_dict: dict = None) -> None:
    """
    Renders a grouped horizontal bar chart showing PIM and Devengado
    by economic classification category (generica_nombre).
    Uses the same visual style as the execution variance chart.

    Args:
        df (pd.DataFrame): DataFrame with columns ['economic_category', 'pim', 'devengado'].
        lang_dict (dict): Dictionary with active language keys.
    """
    if lang_dict is None:
        lang_dict = {}
    if df.empty:
        st.warning("No economic composition data found matching the active filters.")
        return

    df_clean = df.copy()
    df_clean["economic_category"] = df_clean["economic_category"].fillna("Unspecified").astype(str)
    df_clean = df_clean.sort_values(by="pim", ascending=True)
    df_clean = df_clean.tail(10)

    fig = go.Figure()
    plotly_fmt = lang_dict.get("plotly_fmt", ",.0f")

    fig.add_trace(
        go.Bar(
            name=lang_dict.get("legend_pim", "Planned Budget (PIM)"),
            y=df_clean["economic_category"],
            x=df_clean["pim"],
            orientation="h",
            marker=dict(color="#94A3B8"),
            hovertemplate=f"Category: %{{y}}<br>PIM: S/. %{{x:{plotly_fmt}}}<extra></extra>"
        )
    )
    fig.add_trace(
        go.Bar(
            name=lang_dict.get("legend_dev", "Executed Budget (Dev)"),
            y=df_clean["economic_category"],
            x=df_clean["devengado"],
            orientation="h",
            marker=dict(color=_get_colors().get("primary", "#8B0000")),
            hovertemplate=f"Category: %{{y}}<br>Devengado: S/. %{{x:{plotly_fmt}}}<extra></extra>"
        )
    )

    fig.update_layout(
        barmode="group",
        xaxis=dict(showgrid=False, visible=False),
        yaxis=dict(
            showgrid=False,
            showline=False,
            tickfont=dict(size=12, color=_get_colors().get("secondary", "#1E293B")),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11, color=_get_colors().get("secondary", "#1E293B")),
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=40, b=10),
        height=400,
    )
    st.plotly_chart(fig, width="stretch")


# ----------------------------------------------------
# 6. FINANCING STRUCTURE CHART
# Horizontal bar: PIM by financing source (fuente_financiamiento_nombre).
# ----------------------------------------------------
def render_financing_structure(df: pd.DataFrame, lang_dict: dict = None) -> None:
    """
    Renders a horizontal bar chart showing PIM by financing source.
    Highlights the top bar with the primary accent color.

    Args:
        df (pd.DataFrame): DataFrame with columns ['financing_source', 'pim', 'devengado'].
        lang_dict (dict): Dictionary with active language keys.
    """
    if lang_dict is None:
        lang_dict = {}
    if df.empty:
        st.warning("No financing structure data found matching the active filters.")
        return

    df_clean = df.copy()
    df_clean["financing_source"] = df_clean["financing_source"].fillna("Unspecified").astype(str)
    df_clean = df_clean.sort_values(by="pim", ascending=True)

    n_bars = len(df_clean)
    bar_colors = ["#CBD5E1"] * n_bars
    if n_bars > 0:
        bar_colors[-1] = _get_colors().get("primary", "#8B0000")

    text_labels = df_clean["pim"].apply(lambda v: f" {format_boardroom_currency(v, lang_dict)}")

    fig = go.Figure(
        go.Bar(
            x=df_clean["pim"],
            y=df_clean["financing_source"],
            orientation="h",
            marker=dict(color=bar_colors),
            text=text_labels,
            textposition="outside",
            cliponaxis=False,
            hovertemplate="Source: %{y}<br>PIM: S/. %{x:,.0f}<extra></extra>"
        )
    )

    fig.update_layout(
        xaxis=dict(showgrid=False, visible=False),
        yaxis=dict(
            showgrid=False,
            showline=False,
            tickfont=dict(size=12, color=_get_colors().get("secondary", "#1E293B")),
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10),
        height=350,
    )
    st.plotly_chart(fig, width="stretch")


# ----------------------------------------------------
# 7. PROGRAMMATIC ALLOCATION CHART
# Horizontal bar top-10: PIM by selected programmatic dimension.
# ----------------------------------------------------
def render_programmatic_allocation(df: pd.DataFrame, lang_dict: dict = None) -> None:
    """
    Renders a horizontal bar chart showing top-N PIM by programmatic
    dimension (budget program, project, or government function).

    Args:
        df (pd.DataFrame): DataFrame with columns ['dimension', 'total_monto'].
        lang_dict (dict): Dictionary with active language keys.
    """
    if lang_dict is None:
        lang_dict = {}
    if df.empty:
        st.warning("No programmatic allocation data found matching the active filters.")
        return

    df_clean = df.copy()
    df_clean["dimension"] = df_clean["dimension"].fillna("Unspecified").astype(str)
    df_clean = df_clean.sort_values(by="total_monto", ascending=True)

    n_bars = len(df_clean)
    if n_bars == 0:
        return

    bar_colors = ["#CBD5E1"] * n_bars
    if n_bars > 0:
        bar_colors[-1] = _get_colors().get("primary", "#8B0000")

    text_labels = df_clean["total_monto"].apply(lambda v: f" {format_boardroom_currency(v, lang_dict)}")

    fig = go.Figure(
        go.Bar(
            x=df_clean["total_monto"],
            y=df_clean["dimension"],
            orientation="h",
            marker=dict(color=bar_colors),
            text=text_labels,
            textposition="outside",
            cliponaxis=False,
            hovertemplate=f"{lang_dict.get('chart_dimension', 'Dimension')}: %{{y}}<br>{lang_dict.get('chart_budget', 'Budget')}: %{{x:,.0f}}<extra></extra>"
        )
    )

    margin_r = lang_dict.get("conc_margin_r", 110)
    fig.update_layout(
        xaxis=dict(showgrid=False, visible=False),
        yaxis=dict(
            showgrid=False,
            showline=False,
            tickfont=dict(size=12, color=_get_colors().get("secondary", "#1E293B")),
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=margin_r, t=10, b=10),
        height=350,
    )
    st.plotly_chart(fig, width="stretch")


# ----------------------------------------------------
# 8. AI RESPONSE ADAPTER & HELPER FUNCTIONS
# ----------------------------------------------------
def _prepare_ranking_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Dynamically maps a DataFrame's columns to ['dimension', 'total_monto']
    by inferring the categorical (dimension) and numeric (total_monto) columns.
    """
    cols = list(df.columns)
    if len(cols) < 2:
        return df

    numeric_col = None
    categorical_col = None

    if "total_monto" in cols:
        numeric_col = "total_monto"
    if "dimension" in cols:
        categorical_col = "dimension"

    if not numeric_col or not categorical_col:
        for col in cols:
            if pd.api.types.is_numeric_dtype(df[col]) and not numeric_col:
                numeric_col = col
            elif not categorical_col:
                categorical_col = col

    if not numeric_col:
        numeric_col = cols[1] if len(cols) > 1 else cols[0]
    if not categorical_col:
        categorical_col = cols[0]

    if numeric_col == categorical_col:
        remaining = [c for c in cols if c != numeric_col]
        if remaining:
            categorical_col = remaining[0]

    rename_dict = {categorical_col: "dimension", numeric_col: "total_monto"}
    return df.rename(columns=rename_dict)[["dimension", "total_monto"]]


def _prepare_comparison_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Maps columns to ['dimension', 'pim', 'devengado'] dynamically.
    """
    cols = list(df.columns)
    if len(cols) < 3:
        return df

    dim_col = None
    pim_col = None
    dev_col = None

    for col in cols:
        col_lower = str(col).lower()
        if "pim" in col_lower:
            pim_col = col
        elif "dev" in col_lower or "exec" in col_lower or "monto" in col_lower:
            dev_col = col
        elif "dim" in col_lower or "nombre" in col_lower or "sector" in col_lower or "dept" in col_lower or "gov" in col_lower:
            dim_col = col

    remaining_numeric = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    remaining_non_numeric = [c for c in cols if not pd.api.types.is_numeric_dtype(df[c])]

    if not dim_col:
        dim_col = remaining_non_numeric[0] if remaining_non_numeric else cols[0]
    if not pim_col:
        pim_col = [c for c in remaining_numeric if c != dev_col][0] if len([c for c in remaining_numeric if c != dev_col]) > 0 else cols[1]
    if not dev_col:
        dev_col = [c for c in remaining_numeric if c != pim_col][0] if len([c for c in remaining_numeric if c != pim_col]) > 0 else cols[2]

    rename_map = {dim_col: "dimension", pim_col: "pim", dev_col: "devengado"}
    return df.rename(columns=rename_map)[["dimension", "pim", "devengado"]]


def _prepare_geographic_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Maps columns to ['department', 'fiscal_year', 'pim', 'devengado', 'execution_rate'] dynamically.
    """
    cols = list(df.columns)
    dept_col = None
    year_col = None
    rate_col = None
    pim_col = None
    dev_col = None

    for col in cols:
        col_lower = str(col).lower()
        if "dept" in col_lower or "geo" in col_lower or "name" in col_lower or "prov" in col_lower or "dist" in col_lower:
            dept_col = col
        elif "year" in col_lower or "ano" in col_lower or "eje" in col_lower:
            year_col = col
        elif "rate" in col_lower or "porcent" in col_lower or "tasa" in col_lower or "ejec" in col_lower:
            rate_col = col
        elif "pim" in col_lower:
            pim_col = col
        elif "dev" in col_lower or "monto" in col_lower:
            dev_col = col

    if not dept_col:
        dept_col = cols[0]
    if not year_col:
        year_col = cols[1] if len(cols) > 1 else cols[0]
    if not pim_col:
        pim_col = cols[2] if len(cols) > 2 else cols[0]
    if not dev_col:
        dev_col = cols[3] if len(cols) > 3 else cols[0]
    if not rate_col:
        rate_col = cols[4] if len(cols) > 4 else cols[0]

    rename_map = {
        dept_col: "department",
        year_col: "fiscal_year",
        pim_col: "pim",
        dev_col: "devengado",
        rate_col: "execution_rate"
    }

    res_df = df.rename(columns=rename_map).copy()

    if "execution_rate" not in res_df.columns or res_df["execution_rate"].isna().all():
        if "pim" in res_df.columns and "devengado" in res_df.columns:
            res_df["execution_rate"] = (res_df["devengado"] / res_df["pim"].replace(0, float('nan'))) * 100.0
            res_df["execution_rate"] = res_df["execution_rate"].fillna(0.0)

    expected_cols = ["department", "fiscal_year", "pim", "devengado", "execution_rate"]
    safe_cols = [c for c in expected_cols if c in res_df.columns]
    return res_df[safe_cols]


def _render_trend_line_chart(df: pd.DataFrame, lang_dict: dict = None) -> None:
    """
    Renders a premium, minimal timeseries trend line chart using Plotly.
    """
    if lang_dict is None:
        lang_dict = {}

    cols = list(df.columns)
    if len(cols) < 2:
        st.warning("Insufficient data columns to plot trend line chart.")
        return

    x_col = None
    y_col = None

    for col in cols:
        col_lower = str(col).lower()
        if "year" in col_lower or "ano" in col_lower or "mes" in col_lower or "fecha" in col_lower or "date" in col_lower:
            x_col = col
            break

    if not x_col:
        x_col = cols[0]

    y_cols = [c for c in cols if c != x_col and pd.api.types.is_numeric_dtype(df[c])]
    if not y_cols:
        y_cols = [cols[1]] if len(cols) > 1 else [cols[0]]

    fig = go.Figure()
    colors = [_get_colors().get("primary", "#8B0000"), "#475569", "#0F172A"]

    for idx, y_col in enumerate(y_cols[:3]):
        fig.add_trace(
            go.Scatter(
                x=df[x_col],
                y=df[y_col],
                mode="lines+markers",
                name=str(y_col).replace("_", " ").title(),
                line=dict(color=colors[idx % len(colors)], width=3),
                marker=dict(size=7, symbol="circle"),
                hovertemplate="%{x}: S/. %{y:,.2f}<extra></extra>"
            )
        )

    fig.update_layout(
        xaxis=dict(
            showgrid=False,
            tickfont=dict(size=11, color=_get_colors().get("secondary", "#1E293B")),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#F1F5F9",
            tickfont=dict(size=11, color=_get_colors().get("secondary", "#1E293B")),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11, color=_get_colors().get("secondary", "#1E293B")),
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=40, b=10),
        height=350,
    )

    st.plotly_chart(fig, width="stretch")


def _route_visualization(intent: str, chart_type: str, chart_title: str, df: pd.DataFrame, lang_dict: dict) -> None:
    """
    Deterministic visualization router. Maps AI intent to Plotly components.
    """
    if chart_title and isinstance(chart_title, str) and chart_title.strip():
        st.markdown(f"**{chart_title.strip()}**")

    intent_lower = str(intent).lower() if intent else ""
    type_lower = str(chart_type).lower() if chart_type else ""

    if intent_lower == "ranking" or type_lower == "horizontal_bar":
        try:
            ranking_df = _prepare_ranking_df(df)
            render_top_concentrations(ranking_df, lang_dict)
        except Exception as e:
            logger.error("Error in ranking visualization rendering: %s", e)

    elif intent_lower == "comparison" or type_lower == "grouped_bar":
        try:
            comp_df = _prepare_comparison_df(df)
            render_execution_variance(comp_df, lang_dict)
        except Exception as e:
            logger.error("Error in comparison visualization rendering: %s", e)

    elif intent_lower == "geographic" or type_lower == "heatmap":
        try:
            geo_df = _prepare_geographic_df(df)
            render_geographic_heatmap(geo_df)
        except Exception as e:
            logger.error("Error in geographic visualization rendering: %s", e)

    elif intent_lower == "trend" or type_lower == "line":
        try:
            _render_trend_line_chart(df, lang_dict)
        except Exception as e:
            logger.error("Error in trend line visualization rendering: %s", e)

    else:
        logger.warning("Unsupported or unknown visualization intent: %s / chart_type: %s", intent, chart_type)


def _set_pending_followup(label: str) -> None:
    """
    Callback function for follow-up buttons.
    Sets the selected follow-up as the pending prompt to be processed in the next rerun.
    """
    st.session_state.pending_prompt = label


def render_ai_response(summary_data: dict, lang_dict: dict = None) -> None:
    """
    Main adapter entry point. Renders AI response step-by-step defensively.
    """
    if not isinstance(summary_data, dict):
        logger.warning("render_ai_response received invalid summary_data type: %s", type(summary_data))
        return
    if lang_dict is None:
        lang_dict = {}

    try:
        # 1. Title
        title = summary_data.get("title")
        if title and isinstance(title, str) and title.strip():
            st.subheader(title.strip())

        # 2. Executive Summary
        summary = summary_data.get("executive_summary")
        if summary and isinstance(summary, str) and summary.strip():
            st.markdown(summary.strip())

        # 3. KPI Metric
        main_metric = summary_data.get("main_metric")
        if isinstance(main_metric, dict):
            label = main_metric.get("label")
            val_formatted = main_metric.get("formatted")
            val_numeric = main_metric.get("value")
            if label and isinstance(label, str):
                if val_formatted and isinstance(val_formatted, str):
                    st.metric(label=label.strip(), value=val_formatted.strip())
                elif val_numeric is not None:
                    try:
                        val_str = format_boardroom_currency(float(val_numeric), lang_dict)
                        st.metric(label=label.strip(), value=val_str)
                    except Exception:
                        pass

        # 4. Visualization
        chart = summary_data.get("chart")
        intent = summary_data.get("intent")
        if isinstance(chart, dict):
            chart_data = chart.get("data")
            chart_type = chart.get("type")
            chart_title = chart.get("title")
            if chart_data and isinstance(chart_data, list):
                try:
                    df = pd.DataFrame(chart_data)
                    if not df.empty:
                        _route_visualization(intent, chart_type, chart_title, df, lang_dict)
                except Exception as e:
                    logger.error("Failed to parse and render visualization: %s", e)

        # 5. Insights
        insights = summary_data.get("insights")
        if isinstance(insights, list) and insights:
            valid_insights = [i.strip() for i in insights if isinstance(i, str) and i.strip()]
            if valid_insights:
                st.markdown(f"**{lang_dict.get('insights_title', 'Key Insights')}**")
                for insight in valid_insights:
                    st.markdown(f"- {insight}")

        # 6. Followups
        followups = summary_data.get("followups")
        if isinstance(followups, list) and followups:
            valid_followups = [f.strip() for f in followups if isinstance(f, str) and f.strip()]
            if valid_followups:
                cols = st.columns(len(valid_followups))
                for idx, label in enumerate(valid_followups):
                    with cols[idx]:
                        clean_label = "".join(c for c in label if c.isalnum())[:20]
                        st.button(
                            label,
                            key=f"ai_followup_{idx}_{clean_label}",
                            use_container_width=True,
                            on_click=_set_pending_followup,
                            args=(label,)
                        )

    except Exception as err:
        logger.error("Unhandled error in render_ai_response adapter: %s", err)
