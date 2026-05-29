# tests/test_ai_contract.py
"""Tests for AI JSON contract stability and defensive handling."""
import pytest
from src.dashboard.components import render_ai_response

# Mock streamlit to avoid UI runtime errors
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

valid_payload = {
    "intent": "ranking",
    "title": "Top Spending",
    "executive_summary": "Summary.",
    "main_metric": {"label": "Executed", "value": 12345, "formatted": "S/. 12.3 M"},
    "chart": {"type": "horizontal_bar", "title": "Top 5", "data": [{"sector": "Health", "total_monto": 100}]},
    "insights": ["Insight 1"],
    "followups": ["Q1", "Q2"]
}

@pytest.mark.parametrize("payload,desc", [
    (valid_payload, "fully valid payload"),
    ({"intent": "ranking", "title": "Only title"}, "missing optional keys"),
    ({"title": "No intent"}, "missing intent"),
    ({"intent": "unknown", "title": "Unknown intent", "chart": {"type": "unknown"}}, "unknown intent and chart type"),
    ({}, "empty dict"),
    ({"intent": "ranking", "chart": {"type": "horizontal_bar", "data": "not a list"}}, "malformed chart data"),
])
def test_render_ai_response_resilience(payload, desc):
    """Ensure render_ai_response never raises an exception for any payload."""
    try:
        render_ai_response(payload)
    except Exception as exc:
        pytest.fail(f"render_ai_response raised for {desc}: {exc}")
