"""Demo-mode rendering contract.

The committed demo dataset is a row-level sample of a long-format fact table:
it keeps a `pim` row while dropping the `devengado` sibling of the same entity.
Any ratio built from both phases is therefore invalid in demo mode, while
monetary totals and the geographic distribution remain usable.
"""

from unittest.mock import patch

import pandas as pd

from src.dashboard.components import render_geographic_heatmap, render_kpi_cards

LANG = {
    "kpi_pim": "Total Planned Budget (PIM)",
    "kpi_executed": "Total Executed Budget",
    "kpi_rate": "Budget Execution Rate",
    "kpi_gap": "Unexecuted Budget Gap",
    "kpi_coverage": "PIM/devengado pair coverage",
    "kpi_coverage_help": "help",
    "kpi_ratio_disabled": "rates disabled",
}

METRICS = {
    "pim": 1_000_000.0,
    "devengado": 500_000.0,
    "execution_rate": 50.0,
    "unexecuted_gap": 500_000.0,
}

COVERAGE = {"coverage_pct": 0.057, "complete_entity_years": 250, "total_entity_years": 440_240}


def label_of(call) -> str:
    return call.kwargs.get("label", "")


@patch("src.dashboard.components.st")
def test_demo_mode_replaces_ratio_kpis_with_coverage(mock_st):
    render_kpi_cards(METRICS, LANG, coverage=COVERAGE, demo_mode=True)

    labels = [label_of(call) for call in mock_st.metric.call_args_list]

    assert LANG["kpi_coverage"] in labels
    assert LANG["kpi_pim"] in labels
    assert LANG["kpi_executed"] in labels
    assert LANG["kpi_rate"] not in labels
    assert LANG["kpi_gap"] not in labels


@patch("src.dashboard.components.st")
def test_demo_mode_renders_three_cards(mock_st):
    render_kpi_cards(METRICS, LANG, coverage=COVERAGE, demo_mode=True)

    mock_st.columns.assert_called_once_with(3)


@patch("src.dashboard.components.st")
def test_demo_mode_shows_coverage_value(mock_st):
    render_kpi_cards(METRICS, LANG, coverage=COVERAGE, demo_mode=True)

    values = [call.kwargs.get("value") for call in mock_st.metric.call_args_list]

    assert "0.06%" in values


@patch("src.dashboard.components.st")
def test_full_mode_keeps_ratio_kpis(mock_st):
    render_kpi_cards(METRICS, LANG, demo_mode=False)

    labels = [label_of(call) for call in mock_st.metric.call_args_list]

    assert LANG["kpi_rate"] in labels
    assert LANG["kpi_gap"] in labels
    assert LANG["kpi_coverage"] not in labels
    mock_st.columns.assert_called_once_with(4)


def make_heatmap_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"department": "LIMA", "fiscal_year": 2024, "pim": 900.0, "devengado": 100.0, "execution_rate": 11.1},
            {"department": "CUSCO", "fiscal_year": 2024, "pim": 100.0, "devengado": 90.0, "execution_rate": 90.0},
        ]
    )


@patch("src.dashboard.components.st")
@patch("src.dashboard.components.go")
def test_demo_heatmap_maps_planned_budget_not_rate(mock_go, mock_st):
    render_geographic_heatmap(make_heatmap_frame(), demo_mode=True)

    z = mock_go.Heatmap.call_args.kwargs["z"]
    assert sorted(float(value) for value in z.ravel()) == [100.0, 900.0]
    assert "zmax" not in mock_go.Heatmap.call_args.kwargs


@patch("src.dashboard.components.st")
@patch("src.dashboard.components.go")
def test_full_heatmap_maps_execution_rate(mock_go, mock_st):
    render_geographic_heatmap(make_heatmap_frame(), demo_mode=False)

    z = mock_go.Heatmap.call_args.kwargs["z"]
    assert sorted(float(value) for value in z.ravel()) == [11.1, 90.0]
    assert mock_go.Heatmap.call_args.kwargs["zmax"] == 100
