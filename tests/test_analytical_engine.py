import os
import sys
import importlib
import pytest
from unittest.mock import patch, MagicMock

# Ensure src is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

# Load 04_analytical_reports dynamically due to numeric prefix
analytical_reports = importlib.import_module("04_analytical_reports")

def test_initialize_analytical_engine():
    """
    Test initialize_analytical_engine using unittest.mock.patch to mock duckdb.connect.
    Asserts that:
      - The database connection is established to ':memory:' (in-memory).
      - Hardware optimization boundaries (threads and memory limit) are applied via PRAGMA statements.
      - Parquet views mapping is registered without real disk I/O.
    """
    with patch("duckdb.connect") as mock_connect:
        # Create a mock connection object and set up mock return value
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        # Execute target function
        con = analytical_reports.initialize_analytical_engine()

        # 1. Assert that the connection is made specifically to :memory:
        mock_connect.assert_called_once_with(database=':memory:')
        assert con == mock_conn

        # 2. Extract all calls made to con.execute(...)
        execute_calls = [call_args[0][0] for call_args in mock_conn.execute.call_args_list]

        # 3. Assert PRAGMA boundaries are applied correctly using config parameters
        expected_threads_pragma = f"PRAGMA threads={analytical_reports.MAX_THREADS};"
        expected_memory_pragma = f"PRAGMA memory_limit='{analytical_reports.MEMORY_LIMIT}';"

        assert expected_threads_pragma in execute_calls, f"Expected '{expected_threads_pragma}' to be executed."
        assert expected_memory_pragma in execute_calls, f"Expected '{expected_memory_pragma}' to be executed."

        # 4. Assert SQL views mapping creation occurred correctly
        assert any("CREATE VIEW fact_presupuesto" in stmt for stmt in execute_calls)
        assert any("CREATE VIEW dim_geografia" in stmt for stmt in execute_calls)
        assert any("CREATE VIEW dim_institucion" in stmt for stmt in execute_calls)
        assert any("CREATE VIEW dim_programatica" in stmt for stmt in execute_calls)
