import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "dashboard")))

from ai_engine import QueryValidationPolicy


class TestQueryValidationPolicy:
    """Validates that QueryValidationPolicy correctly accepts/rejects SQL."""

    def test_accepts_plain_select(self):
        result = QueryValidationPolicy.validate("SELECT 1")
        assert result == "SELECT 1"

    def test_accepts_select_with_group_by(self):
        sql = "SELECT a, SUM(b) FROM t GROUP BY a"
        result = QueryValidationPolicy.validate(sql)
        assert result == sql

    def test_accepts_cte_select(self):
        sql = "WITH x AS (SELECT 1) SELECT * FROM x"
        result = QueryValidationPolicy.validate(sql)
        assert result == sql

    def test_accepts_cte_with_aggregation(self):
        sql = (
            "WITH top AS (SELECT id, SUM(amount) AS total FROM t GROUP BY id ORDER BY total DESC LIMIT 1) "
            "SELECT tp.id, year, SUM(amount) AS annual "
            "FROM fact f CROSS JOIN top tp WHERE f.id = tp.id GROUP BY tp.id, year"
        )
        result = QueryValidationPolicy.validate(sql)
        assert result == sql

    def test_rejects_delete(self):
        with pytest.raises(ValueError, match="Only SELECT statements"):
            QueryValidationPolicy.validate("DELETE FROM fact_presupuesto")

    def test_rejects_update(self):
        with pytest.raises(ValueError, match="Only SELECT statements"):
            QueryValidationPolicy.validate("UPDATE fact_presupuesto SET monto = 0")

    def test_rejects_insert(self):
        with pytest.raises(ValueError, match="Only SELECT statements"):
            QueryValidationPolicy.validate("INSERT INTO t VALUES (1)")

    def test_rejects_drop(self):
        with pytest.raises(ValueError, match="Only SELECT statements"):
            QueryValidationPolicy.validate("DROP TABLE fact_presupuesto")

    def test_rejects_alter(self):
        with pytest.raises(ValueError, match="Only SELECT statements"):
            QueryValidationPolicy.validate("ALTER TABLE t ADD COLUMN x INT")

    def test_rejects_truncate(self):
        with pytest.raises(ValueError, match="Only SELECT statements"):
            QueryValidationPolicy.validate("TRUNCATE TABLE t")

    def test_rejects_create(self):
        with pytest.raises(ValueError, match="Only SELECT statements"):
            QueryValidationPolicy.validate("CREATE TABLE t (x INT)")

    def test_rejects_multi_statement(self):
        with pytest.raises(ValueError, match="Only single SELECT"):
            QueryValidationPolicy.validate("SELECT 1; DROP TABLE x")

    def test_rejects_cte_with_dml_inside(self):
        with pytest.raises(ValueError, match="Forbidden keyword"):
            QueryValidationPolicy.validate("WITH x AS (DELETE FROM t) SELECT * FROM x")

    def test_rejects_cte_with_dml_after(self):
        with pytest.raises(ValueError, match="Forbidden keyword"):
            QueryValidationPolicy.validate("WITH x AS (SELECT 1) DELETE FROM t")
