# tests/test_visualization_router.py
"""Tests for the internal visualization routing logic.
The router should call the appropriate rendering helper based on intent or chart type
and must never raise an exception, even for malformed inputs.
"""
import pandas as pd
import pytest

from src.dashboard.components import _route_visualization

# Mock streamlit to avoid UI errors
@pytest.fixture(autouse=True)
def mock_streamlit(monkeypatch):
    class Dummy:
        def subheader(self, *a, **kw): pass
        def markdown(self, *a, **kw): pass
        def metric(self, *a, **kw): pass
        def button(self, *a, **kw): return False
        def columns(self, n):
            return [self] * n
        def warning(self, *a, **kw): pass
        def error(self, *a, **kw): pass
    dummy = Dummy()
    monkeypatch.setattr('src.dashboard.components.st', dummy, raising=False)

# Helper to create minimal DataFrames
def df_one_row(cols, values):
    return pd.DataFrame([values], columns=cols)

def test_route_ranking_calls_render_top_concentrations(monkeypatch):
    dummy_called = {}
    def fake_render(df, lang):
        dummy_called['called'] = True
    monkeypatch.setattr('src.dashboard.components.render_top_concentrations', fake_render)
    df = df_one_row(["dimension", "total_monto"], ["A", 100])
    _route_visualization('ranking', None, 'Title', df, {})
    assert dummy_called.get('called') is True

def test_route_comparison_calls_render_execution_variance(monkeypatch):
    dummy_called = {}
    def fake_render(df, lang):
        dummy_called['called'] = True
    monkeypatch.setattr('src.dashboard.components.render_execution_variance', fake_render)
    df = df_one_row(["dimension", "pim", "devengado"], ["A", 100, 80])
    _route_visualization('comparison', None, None, df, {})
    assert dummy_called.get('called') is True

def test_route_geographic_calls_render_geographic_heatmap(monkeypatch):
    dummy_called = {}
    def fake_render(df):
        dummy_called['called'] = True
    monkeypatch.setattr('src.dashboard.components.render_geographic_heatmap', fake_render)
    df = df_one_row(["department", "fiscal_year", "pim", "devengado", "execution_rate"],
                    ["D1", 2023, 100, 80, 80.0])
    _route_visualization('geographic', None, None, df, {})
    assert dummy_called.get('called') is True

def test_route_trend_calls_render_trend_line_chart(monkeypatch):
    dummy_called = {}
    def fake_render(df, lang):
        dummy_called['called'] = True
    monkeypatch.setattr('src.dashboard.components._render_trend_line_chart', fake_render)
    df = df_one_row(["year", "value"], [2023, 100])
    _route_visualization('trend', None, None, df, {})
    assert dummy_called.get('called') is True

def test_route_unknown_intent_logs_warning(monkeypatch, caplog):
    # Ensure no exception is raised and a warning is logged
    df = pd.DataFrame()
    _route_visualization('unknown_intent', 'unknown_type', None, df, {})
    # Check that a warning containing 'Unsupported' appears in logs
    warnings = [rec.message for rec in caplog.records if rec.levelname == 'WARNING']
    assert any('Unsupported' in w for w in warnings)

def test_route_with_invalid_df_does_not_crash(monkeypatch):
    # Provide a DataFrame that lacks required columns; router should handle gracefully
    dummy_called = {}
    def fake_render(*args, **kwargs):
        dummy_called['called'] = True
    monkeypatch.setattr('src.dashboard.components.render_top_concentrations', fake_render)
    df = pd.DataFrame([{'a': 1}])  # missing expected columns
    # Should not raise, and render may be attempted (error caught internally)
    _route_visualization('ranking', None, None, df, {})
    # We don't assert call because it may error internally; just ensure no exception
    assert True
