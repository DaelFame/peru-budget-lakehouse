"""
Executive Dashboard Frontend Components Module

Handles premium UI rendering using Streamlit and Plotly. It is styled and colored
following an elite, high data-to-ink ratio presentation strategy (minimal grids,
clear visual hierarchies, and high contrast labels).
"""

import logging
from typing import Dict, Any

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# Professional logging
logger = logging.getLogger(__name__)

# Try importing standard theme or fallback gracefully
try:
    from theme import UI_COLORS
except ImportError:
    try:
        from src.dashboard.theme import UI_COLORS
    except ImportError:
        # Fallback to premium slate and deep wine red executive palette
        UI_COLORS = {
            "primary": "#8B0000",        # Deep crimson/wine representing Peru
            "secondary": "#1E293B",      # Slate blue for hierarchy headers
            "background_card": "#F8FAFC", # Light gray/blue
            "border": "#E2E8F0",
            "success": "#10B981",
            "warning": "#F59E0B",
            "danger": "#EF4444",
        }

logger.info("Successfully configured component themes.")


# ----------------------------------------------------
# 0. CURRENCY FORMATTING HELPER
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
        if execution_rate < 50.0:
            warning_text = lang_dict.get("execution_warning", "⚠️ Low Execution (< 50%)")
            st.metric(
                label=lang_dict.get("kpi_rate", "Budget Execution Rate"),
                value=rate_str,
                delta=warning_text,
                delta_color="inverse"
            )
        else:
            st.metric(
                label=lang_dict.get("kpi_rate", "Budget Execution Rate"),
                value=rate_str
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
    bar_colors[-1] = UI_COLORS.get("primary", "#8B0000")  # Top bar highlighted

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
            tickfont=dict(size=12, color=UI_COLORS.get("secondary", "#1E293B")),
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
            marker=dict(color=UI_COLORS.get("primary", "#8B0000")),
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
            tickfont=dict(size=12, color=UI_COLORS.get("secondary", "#1E293B")),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11, color=UI_COLORS.get("secondary", "#1E293B")),
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
        [1.0, UI_COLORS.get("primary", "#8B0000")]
    ]

    # FIX: Configured colorbar using modern nested dictionary structure to resolve Plotly crash
    colorbar_config = dict(
        title=dict(
            text="Rate (%)",
            side="top"
        ),
        thickness=12,
        len=0.5,
        tickfont=dict(size=10, color=UI_COLORS.get("secondary", "#1E293B")),
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
            tickfont=dict(size=11, color=UI_COLORS.get("secondary", "#1E293B")),
        ),
        yaxis=dict(
            showgrid=False,
            showline=False,
            tickfont=dict(size=11, color=UI_COLORS.get("secondary", "#1E293B")),
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=40, b=10),
        height=500,
    )

    # Compliant with latest Streamlit parameters (width="stretch")
    st.plotly_chart(fig, width="stretch")
