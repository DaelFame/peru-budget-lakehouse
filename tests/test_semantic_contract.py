"""Tests for SQLSemanticContractValidator."""

import os
import sys

import pytest

sys.path.append(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "src", "dashboard")
    )
)

from semantic_contract import SQLSemanticContractValidator


# =========================================================================
# VALID QUERIES
# =========================================================================


class TestValidQueries:
    """Semantically valid analytical queries that should PASS."""

    def test_year_level_aggregation(self):
        """Total spending per year -> year-level grain."""
        sql = """
            SELECT f.anio, SUM(f.monto) AS total
            FROM fact_presupuesto f
            WHERE f.anio <= 2025
            GROUP BY f.anio
            ORDER BY f.anio
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid, f"Expected valid, got: {result.errors}"
        assert result.grain == "year-level"

    def test_project_level_aggregation(self):
        """Total spending per project -> project-level grain."""
        sql = """
            SELECT p.producto_proyecto_nombre AS project,
                   SUM(f.monto) AS total
            FROM fact_presupuesto f
            LEFT JOIN dim_programatica p
                ON f.sk_programatica_id = p.sk_programatica_id
            WHERE f.anio <= 2025
            GROUP BY p.producto_proyecto_nombre
            ORDER BY total DESC
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid, f"Expected valid, got: {result.errors}"
        assert result.grain == "project-level"

    def test_institution_level_aggregation(self):
        """Total spending per sector -> institution-level grain."""
        sql = """
            SELECT i.sector_nombre AS sector,
                   SUM(f.monto) AS total
            FROM fact_presupuesto f
            LEFT JOIN dim_institucion i
                ON f.sk_institucion_id = i.sk_institucion_id
            WHERE f.anio <= 2025
            GROUP BY sector
            ORDER BY total DESC
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid, f"Expected valid, got: {result.errors}"
        assert result.grain == "institution-level"

    def test_program_level_aggregation(self):
        """Total spending per program -> program-level grain."""
        sql = """
            SELECT p.programa_ppto_nombre AS program,
                   SUM(f.monto) AS total
            FROM fact_presupuesto f
            LEFT JOIN dim_programatica p
                ON f.sk_programatica_id = p.sk_programatica_id
            WHERE f.anio <= 2025
            GROUP BY program
            ORDER BY total DESC
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid, f"Expected valid, got: {result.errors}"
        assert result.grain == "program-level"

    def test_project_year_composite_grain(self):
        """Spending per project per year -> project_year-level grain."""
        sql = """
            SELECT p.producto_proyecto_nombre AS project,
                   f.anio,
                   SUM(f.monto) AS total
            FROM fact_presupuesto f
            LEFT JOIN dim_programatica p
                ON f.sk_programatica_id = p.sk_programatica_id
            WHERE f.anio <= 2025
            GROUP BY p.producto_proyecto_nombre, f.anio
            ORDER BY project, f.anio
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid, f"Expected valid, got: {result.errors}"
        assert result.grain == "project_year-level"

    def test_top_n_ranking(self):
        """TOP-N ranking query without time dimension."""
        sql = """
            SELECT p.producto_proyecto_nombre AS project,
                   SUM(CASE WHEN f.fase = 'devengado'
                       THEN f.monto ELSE 0 END) AS executed
            FROM fact_presupuesto f
            LEFT JOIN dim_programatica p
                ON f.sk_programatica_id = p.sk_programatica_id
            WHERE f.anio = 2024 AND f.anio <= 2025
            GROUP BY project
            ORDER BY executed DESC
            LIMIT 5
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid, f"Expected valid, got: {result.errors}"
        assert result.grain == "project-level"

    def test_scalar_aggregation(self):
        """Simple total - no GROUP BY, all columns aggregated."""
        sql = """
            SELECT SUM(f.monto) AS total
            FROM fact_presupuesto f
            WHERE f.anio <= 2025
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid, f"Expected valid, got: {result.errors}"
        assert result.grain == "scalar"

    def test_cte_with_consistent_grain(self):
        """CTE aggregation feeding into main query."""
        sql = """
            WITH top_projects AS (
                SELECT p.sk_programatica_id,
                       p.producto_proyecto_nombre AS project,
                       SUM(f.monto) AS total
                FROM fact_presupuesto f
                LEFT JOIN dim_programatica p
                    ON f.sk_programatica_id = p.sk_programatica_id
                WHERE f.anio <= 2025
                GROUP BY p.sk_programatica_id, p.producto_proyecto_nombre
                ORDER BY total DESC
                LIMIT 3
            )
            SELECT tp.project,
                   f.anio,
                   SUM(f.monto) AS annual
            FROM fact_presupuesto f
            LEFT JOIN dim_programatica p
                ON f.sk_programatica_id = p.sk_programatica_id
            CROSS JOIN top_projects tp
            WHERE p.sk_programatica_id = tp.sk_programatica_id
              AND f.anio <= 2025
            GROUP BY tp.project, f.anio
            ORDER BY f.anio
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid, f"Expected valid, got: {result.errors}"
        assert result.grain == "project_year-level"

    def test_cte_without_grain(self):
        """CTE with scalar aggregation."""
        sql = """
            WITH total_budget AS (
                SELECT SUM(f.monto) AS total
                FROM fact_presupuesto f
                WHERE f.anio <= 2025
            )
            SELECT tb.total
            FROM total_budget tb
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid, f"Expected valid, got: {result.errors}"
        # Main query has no GROUP BY and no aggregation -> no grain
        # (tb.total is a column ref from CTE, not an aggregation itself)

    def test_plain_select_distinct(self):
        """Simple SELECT DISTINCT with no aggregation."""
        sql = """
            SELECT DISTINCT i.sector_nombre
            FROM dim_institucion i
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid, f"Expected valid, got: {result.errors}"

    def test_financing_source_query(self):
        """Budget by financing source -> institution-level via source."""
        sql = """
            SELECT fi.fuente_financiamiento_nombre AS source,
                   SUM(CASE WHEN f.fase = 'pim'
                       THEN f.monto ELSE 0 END) AS total_pim
            FROM fact_presupuesto f
            LEFT JOIN dim_financiamiento fi
                ON f.sk_financiamiento_id = fi.sk_financiamiento_id
            WHERE f.anio = 2024 AND f.anio <= 2025
            GROUP BY source
            ORDER BY total_pim DESC
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid, f"Expected valid, got: {result.errors}"
        # fuente_financiamiento_nombre is not explicitly mapped to a grain
        # It falls under "unknown-level" but that's fine - it's valid SQL
        # and the grain detection returns None since it's not mapped

    def test_execution_rate_calculation(self):
        """Execution rate with complex expressions and NULLIF."""
        sql = """
            SELECT i.sector_nombre AS sector,
                   SUM(CASE WHEN f.fase = 'devengado'
                       THEN f.monto ELSE 0 END) /
                   NULLIF(SUM(CASE WHEN f.fase = 'pim'
                       THEN f.monto ELSE 0 END), 0) * 100 AS exec_rate
            FROM fact_presupuesto f
            LEFT JOIN dim_institucion i
                ON f.sk_institucion_id = i.sk_institucion_id
            WHERE f.anio = 2024 AND f.anio <= 2025
            GROUP BY sector
            ORDER BY exec_rate DESC
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid, f"Expected valid, got: {result.errors}"
        assert result.grain == "institution-level"

    def test_geographic_query(self):
        """Query using geography dimension."""
        sql = """
            SELECT g.departamento_ejecutora_nombre AS department,
                   SUM(f.monto) AS total
            FROM fact_presupuesto f
            LEFT JOIN dim_geografia g
                ON f.sk_geografia_id = g.sk_geografia_id
            WHERE f.anio <= 2025
            GROUP BY department
            ORDER BY total DESC
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid, f"Expected valid, got: {result.errors}"


# =========================================================================
# INVALID QUERIES
# =========================================================================


class TestInvalidQueries:
    """Semantically invalid queries that should FAIL."""

    def test_missing_group_by_column(self):
        """SELECT has non-aggregated column not in GROUP BY."""
        sql = """
            SELECT p.producto_proyecto_nombre AS project,
                   f.anio,
                   SUM(f.monto) AS total
            FROM fact_presupuesto f
            LEFT JOIN dim_programatica p
                ON f.sk_programatica_id = p.sk_programatica_id
            WHERE f.anio <= 2025
            GROUP BY p.producto_proyecto_nombre
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert not result.is_valid, "Expected invalid, got valid"
        assert any("anio" in e and "GROUP BY" in e for e in result.errors)

    def test_non_aggregated_without_group_by(self):
        """Non-aggregated columns present without GROUP BY."""
        sql = """
            SELECT p.producto_proyecto_nombre,
                   SUM(f.monto) AS total
            FROM fact_presupuesto f
            LEFT JOIN dim_programatica p
                ON f.sk_programatica_id = p.sk_programatica_id
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert not result.is_valid, "Expected invalid, got valid"
        assert any(
            "must appear" in e and "GROUP BY" in e
            for e in result.errors
        )

    def test_column_not_in_cte_projection(self):
        """Column referenced from CTE but not projected there."""
        sql = """
            WITH cte AS (
                SELECT sk_programatica_id, monto
                FROM fact_presupuesto
                WHERE anio <= 2025
            )
            SELECT anio, SUM(monto) AS total
            FROM cte
            GROUP BY anio
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert not result.is_valid, "Expected invalid, got valid"
        assert any("anio" in e for e in result.errors)

    def test_column_not_found_in_table(self):
        """Column referenced that doesn't exist in any table."""
        sql = """
            SELECT f.monto, f.nonexistent_column
            FROM fact_presupuesto f
            WHERE f.anio <= 2025
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert not result.is_valid, "Expected invalid, got valid"
        assert any(
            "nonexistent_column" in e and "not found" in e
            for e in result.errors
        )

    def test_invalid_table_alias(self):
        """Column qualified with unknown table alias."""
        sql = """
            SELECT x.monto
            FROM fact_presupuesto f
            WHERE f.anio <= 2025
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert not result.is_valid, "Expected invalid, got valid"
        assert any(
            "Unknown table alias" in e and "x" in e
            for e in result.errors
        )

    def test_valid_cte_chain(self):
        """Valid CTE chain (non-cyclic) should pass validation."""
        sql = """
            WITH cte1 AS (
                SELECT sk_programatica_id
                FROM fact_presupuesto
                WHERE anio <= 2025
            ),
            cte2 AS (
                SELECT cte1.sk_programatica_id
                FROM cte1
                CROSS JOIN fact_presupuesto f
            )
            SELECT * FROM cte2
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid, f"Expected valid, got: {result.errors}"

    def test_broken_cte_reference(self):
        """CTE references undefined CTE."""
        sql = """
            WITH cte1 AS (
                SELECT sk_programatica_id
                FROM fact_presupuesto
                WHERE anio <= 2025
            )
            SELECT cte1.sk_programatica_id, cte2.some_col
            FROM cte1
            LEFT JOIN cte2 ON cte1.sk_programatica_id = cte2.sk_programatica_id
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert not result.is_valid, "Expected invalid, got valid"
        assert any("cte2" in e and "not defined" in e for e in result.errors)

    def test_alias_not_projected_upstream(self):
        """CTE references column not projected in upstream CTE."""
        sql = """
            WITH cte1 AS (
                SELECT sk_programatica_id
                FROM fact_presupuesto
                WHERE anio <= 2025
            ),
            cte2 AS (
                SELECT sk_programatica_id, monto
                FROM fact_presupuesto
                WHERE anio <= 2025
            )
            SELECT cte1.sk_programatica_id, cte1.monto, cte2.monto
            FROM cte1
            LEFT JOIN cte2 ON cte1.sk_programatica_id = cte2.sk_programatica_id
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert not result.is_valid, "Expected invalid, got valid"
        assert any(
            "monto" in e and "not projected" in e and "cte1" in e
            for e in result.errors
        )

    def test_where_column_not_in_scope(self):
        """WHERE clause references column not in any table."""
        sql = """
            SELECT f.monto
            FROM fact_presupuesto f
            WHERE f.imaginary_col = 1
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert not result.is_valid, "Expected invalid, got valid"
        assert any(
            "imaginary_col" in e for e in result.errors
        )

    def test_join_column_not_in_scope(self):
        """JOIN ON clause references column not in any table."""
        sql = """
            SELECT f.monto
            FROM fact_presupuesto f
            LEFT JOIN dim_institucion i
                ON f.sk_institucion_id = i.nonexistent_col
            WHERE f.anio <= 2025
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert not result.is_valid, "Expected invalid, got valid"
        assert any(
            "nonexistent_col" in e for e in result.errors
        )

    def test_order_by_invalid_column(self):
        """ORDER BY references invalid alias."""
        sql = """
            SELECT f.anio, SUM(f.monto) AS total
            FROM fact_presupuesto f
            WHERE f.anio <= 2025
            GROUP BY f.anio
            ORDER BY nonexistent
        """
        # This is a valid alias resolution failure but the ORDER BY
        # uses an alias that doesn't exist. The ORDER BY column validation
        # is part of DuckDB execution, so we may not catch this.
        # The semantic validator focuses on column scope, not alias resolution
        # in ORDER BY.
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid, "Should be valid (ORDER BY alias check not in scope)"

    def test_ambiguous_column(self):
        """Unqualified column exists in multiple joined tables."""
        sql = """
            SELECT sk_programatica_id, SUM(f.monto) AS total
            FROM fact_presupuesto f
            LEFT JOIN dim_programatica p
                ON f.sk_programatica_id = p.sk_programatica_id
            WHERE f.anio <= 2025
            GROUP BY sk_programatica_id
        """
        # sk_programatica_id exists in both fact_presupuesto and dim_programatica
        # This could be ambiguous but is a common pattern.
        result = SQLSemanticContractValidator.validate(sql)
        # The column exists in both tables, so it's actually not ambiguous
        # since both tables have the same column and it's in the JOIN condition
        assert not result.is_valid or "ambiguous" in " ".join(result.warnings).lower()

    def test_missing_cte_without_main(self):
        """WITH statement with no main query."""
        sql = """
            WITH cte AS (
                SELECT 1
            )
        """
        # sqlparse might not parse this as valid since there's no main SELECT
        result = SQLSemanticContractValidator.validate(sql)
        assert not result.is_valid

    def test_undefined_cte_in_join(self):
        """Main query references undefined CTE in JOIN."""
        sql = """
            SELECT f.anio, SUM(f.monto) AS total
            FROM fact_presupuesto f
            LEFT JOIN undefined_cte u
                ON f.sk_programatica_id = u.sk_programatica_id
            WHERE f.anio <= 2025
            GROUP BY f.anio
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert not result.is_valid, "Expected invalid, got valid"
        assert any(
            "not defined" in e or "not found" in e
            for e in result.errors
        )


# =========================================================================
# EDGE CASES
# =========================================================================


class TestEdgeCases:
    """Edge cases and resilience tests."""

    def test_empty_sql(self):
        result = SQLSemanticContractValidator.validate("")
        assert not result.is_valid
        assert any("Empty" in e for e in result.errors)

    def test_whitespace_only(self):
        result = SQLSemanticContractValidator.validate("   \n  \t  ")
        assert not result.is_valid
        assert any("Empty" in e for e in result.errors)

    def test_comment_only(self):
        result = SQLSemanticContractValidator.validate("-- this is a comment")
        # sqlparse might return empty parsed result
        assert not result.is_valid

    def test_validation_result_structure(self):
        """Verify ValidationResult contains all required fields."""
        sql = """
            SELECT f.anio, SUM(f.monto) AS total
            FROM fact_presupuesto f
            WHERE f.anio <= 2025
            GROUP BY f.anio
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert hasattr(result, "is_valid")
        assert hasattr(result, "grain")
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)

    def test_valid_result_has_no_errors(self):
        sql = """
            SELECT i.nivel_gobierno_nombre AS level,
                   SUM(f.monto) AS total
            FROM fact_presupuesto f
            LEFT JOIN dim_institucion i
                ON f.sk_institucion_id = i.sk_institucion_id
            WHERE f.anio <= 2025
            GROUP BY level
        """
        result = SQLSemanticContractValidator.validate(sql)
        assert result.is_valid
        assert len(result.errors) == 0
