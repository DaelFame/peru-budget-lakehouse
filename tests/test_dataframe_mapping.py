# tests/test_dataframe_mapping.py
"""Tests for the DataFrame preparation helper functions in components.
These helpers dynamically map arbitrary column names to the expected schema
used by the visualization adapters.
"""
import pandas as pd

from src.dashboard.components import (
    _prepare_ranking_df,
    _prepare_comparison_df,
    _prepare_geographic_df,
)

# Helper to create DataFrames with arbitrary column ordering
def make_df(columns, rows):
    return pd.DataFrame(rows, columns=columns)

# ---------- Ranking DF Tests ----------

def test_prepare_ranking_df_basic():
    df = make_df(["sector", "total_monto"], [["Health", 100], ["Edu", 200]])
    out = _prepare_ranking_df(df)
    assert list(out.columns) == ["dimension", "total_monto"]
    assert out.iloc[0]["dimension"] == "Health"

def test_prepare_ranking_df_infer_columns():
    # numeric column not named total_monto; categorical not named dimension
    df = make_df(["name", "value"], [["A", 10], ["B", 20]])
    out = _prepare_ranking_df(df)
    assert list(out.columns) == ["dimension", "total_monto"]
    # ensure the mapping kept original order
    assert out.iloc[0]["dimension"] == "A"
    assert out.iloc[0]["total_monto"] == 10

def test_prepare_ranking_df_single_column_returns_original():
    df = make_df(["only"], [[1], [2]])
    out = _prepare_ranking_df(df)
    pd.testing.assert_frame_equal(out, df)

# ---------- Comparison DF Tests ----------

def test_prepare_comparison_df_basic():
    df = make_df(["dimension", "pim", "devengado"], [["A", 100, 80]])
    out = _prepare_comparison_df(df)
    assert list(out.columns) == ["dimension", "pim", "devengado"]
    assert out.iloc[0]["pim"] == 100

def test_prepare_comparison_df_fuzzy_names():
    df = make_df(["dept_name", "plan", "exec"], [["X", 50, 45]])
    out = _prepare_comparison_df(df)
    # should map based on substrings
    assert list(out.columns) == ["dimension", "pim", "devengado"]
    assert out.iloc[0]["dimension"] == "X"
    assert out.iloc[0]["pim"] == 50
    assert out.iloc[0]["devengado"] == 45

def test_prepare_comparison_df_insufficient_columns_returns_original():
    df = make_df(["a", "b"], [[1, 2]])
    out = _prepare_comparison_df(df)
    pd.testing.assert_frame_equal(out, df)

# ---------- Geographic DF Tests ----------

def test_prepare_geographic_df_basic():
    df = make_df([
        "department",
        "fiscal_year",
        "pim",
        "devengado",
        "execution_rate",
    ], [["D1", 2023, 100, 80, 80.0]])
    out = _prepare_geographic_df(df)
    assert list(out.columns) == ["department", "fiscal_year", "pim", "devengado", "execution_rate"]
    assert out.iloc[0]["execution_rate"] == 80.0

#def test_prepare_geographic_df_compute_rate_when_missing():
    # omit execution_rate column; should be computed from devengado/pim
    #df = make_df(["departamento", "year", "pim", "devengado"], [["D", 2024, 200, 150]])
    #out = _prepare_geographic_df(df)
    #assert "execution_rate" in out.columns
    # 150/200 *100 = 75.0
    #assert round(float(out.iloc[0]["execution_rate"]), 1) == 75.0

def test_prepare_geographic_df_fallback_when_no_numeric():
    df = make_df(["a", "b", "c", "d", "e"], [["x", "y", "z", "w", "v"]])
    out = _prepare_geographic_df(df)
    # Should still return the renamed columns even if data is non‑numeric
    assert list(out.columns) == ["department", "fiscal_year", "pim", "devengado", "execution_rate"]
