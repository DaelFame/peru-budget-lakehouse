import os
import sys
import importlib
import pytest
import polars as pl

# Ensure src is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

# Load the numerically-prefixed module dynamically using importlib
qa_audit = importlib.import_module("etl_05_data_quality_audit")

def test_audit_financial_amounts_match():
    """
    Test 1: Silver and Gold totals match exactly.
    The function should execute without raising any errors.
    """
    # Create two LazyFrames with matching sums: 500.50
    df_silver = pl.DataFrame({"monto": [100.0, 250.25, 150.25]})
    df_gold = pl.DataFrame({"monto": [300.0, 200.50]})

    lazy_silver = df_silver.lazy()
    lazy_gold_fact = df_gold.lazy()

    # Should run and pass without errors
    qa_audit.audit_financial_amounts(lazy_silver, lazy_gold_fact)

def test_audit_financial_amounts_mismatch():
    """
    Test 2: Silver and Gold totals differ by more than 0.01 threshold.
    The function MUST assert that a ValueError is raised.
    """
    # Create two LazyFrames with mismatching sums (difference is 0.05, which is > 0.01)
    df_silver = pl.DataFrame({"monto": [100.0, 250.25, 150.25]})  # Sum: 500.50
    df_gold = pl.DataFrame({"monto": [300.0, 200.55]})            # Sum: 500.55

    lazy_silver = df_silver.lazy()
    lazy_gold_fact = df_gold.lazy()

    # Must raise a ValueError
    with pytest.raises(ValueError) as exc_info:
        qa_audit.audit_financial_amounts(lazy_silver, lazy_gold_fact)

    assert "Data quality audit failed" in str(exc_info.value)
    assert "Financial mismatch detected" in str(exc_info.value)
