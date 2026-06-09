"""
Tests for GrainRouter: pre-LLM analytical grain classifier.

Covers:
  - single-dimension queries (valid, no decomposition)
  - single-dimension + year queries (valid composites)
  - multi-dimension queries (invalid, need decomposition)
  - scalar queries (no dimensions, aggregates only)
  - Spanish/English cross-language consistency
  - Plural normalization
  - Edge cases (empty, year-only)
"""

from dashboard.grain_router import (
    GrainRouter,
    GRAIN_YEAR,
    GRAIN_GEOGRAPHY,
    GRAIN_FINANCING,
    GRAIN_ECONOMIC,
    GRAIN_INSTITUTION,
    GRAIN_PROGRAM,
    GRAIN_PROJECT,
    GRAIN_SCALAR,
    COMPOSITE_GRAINS,
)


class TestGrainRouter:
    """Deterministic grain classification tests."""

    def test_single_dimension_geography(self):
        plan = GrainRouter.route("Show PIM by department for 2024")
        assert plan.is_valid
        assert plan.primary_grain == GRAIN_GEOGRAPHY
        assert plan.has_year is False
        assert plan.needs_decomposition is False
        assert plan.to_composite_name() == GRAIN_GEOGRAPHY

    def test_single_dimension_financing(self):
        plan = GrainRouter.route("What is the budget by financing source?")
        assert plan.is_valid
        assert plan.primary_grain == GRAIN_FINANCING
        assert plan.has_year is False
        assert plan.to_composite_name() == GRAIN_FINANCING

    def test_single_dimension_economic(self):
        plan = GrainRouter.route("Budget by economic category")
        assert plan.is_valid
        assert plan.primary_grain == GRAIN_ECONOMIC

    def test_single_dimension_institution(self):
        plan = GrainRouter.route("Compare PIM by sector")
        assert plan.is_valid
        assert plan.primary_grain == GRAIN_INSTITUTION

    def test_single_dimension_program(self):
        plan = GrainRouter.route("Top programs by PIM")
        assert plan.is_valid
        assert plan.primary_grain == GRAIN_PROGRAM

    def test_single_dimension_project(self):
        plan = GrainRouter.route("Which projects have the highest budget?")
        assert plan.is_valid
        assert plan.primary_grain == GRAIN_PROJECT

    def test_single_dimension_plus_year_composite(self):
        plan = GrainRouter.route("Show PIM by department by year")
        assert plan.is_valid
        assert plan.primary_grain == GRAIN_GEOGRAPHY
        assert plan.has_year is True
        assert plan.to_composite_name() == "geography_year-level"

    def test_all_composites_constructible(self):
        """Every COMPOSITE_GRAINS entry should be reachable from a query."""
        grain_kw = {
            GRAIN_ECONOMIC: "economic category",
            GRAIN_FINANCING: "financing source",
            GRAIN_GEOGRAPHY: "department",
            GRAIN_INSTITUTION: "sector",
            GRAIN_PROGRAM: "program",
            GRAIN_PROJECT: "project",
            "function-level": "function",
            "activity-level": "activity",
        }
        for composite_sig, composite_name in COMPOSITE_GRAINS.items():
            dim = [g for g in composite_sig if g != GRAIN_YEAR][0]
            keyword = grain_kw[dim]
            plan = GrainRouter.route(f"Show PIM by {keyword} by year")
            assert plan.is_valid, f"{dim} + year should be valid"
            assert plan.to_composite_name() == composite_name

    def test_multi_dimension_rejected(self):
        plan = GrainRouter.route("Show PIM by department and financing source for 2024")
        assert plan.is_valid is False
        assert plan.needs_decomposition is True
        assert plan.primary_grain is None
        assert GRAIN_GEOGRAPHY in plan.detected_grains
        assert GRAIN_FINANCING in plan.detected_grains

    def test_triple_grain_rejected(self):
        plan = GrainRouter.route("Show PIM by economic category and financing source annually")
        assert plan.is_valid is False
        assert plan.needs_decomposition is True
        assert len(plan.detected_grains) == 3
        assert GRAIN_ECONOMIC in plan.detected_grains
        assert GRAIN_FINANCING in plan.detected_grains
        assert GRAIN_YEAR in plan.detected_grains

    def test_scalar_no_dimensions(self):
        plan = GrainRouter.route("What was the total PIM for 2024?")
        assert plan.is_valid
        assert plan.primary_grain == GRAIN_SCALAR
        assert plan.has_year is False

    def test_year_only(self):
        plan = GrainRouter.route("Show budget trends over time")
        assert plan.is_valid
        assert plan.primary_grain == GRAIN_YEAR
        assert plan.has_year is True

    def test_spanish_single_dimension(self):
        plan = GrainRouter.route("Presupuesto por departamento por año")
        assert plan.is_valid
        assert plan.primary_grain == GRAIN_GEOGRAPHY
        assert plan.has_year is True

    def test_spanish_scalar(self):
        plan = GrainRouter.route("Cuanto fue el PIM total para 2024?")
        assert plan.is_valid
        assert plan.primary_grain == GRAIN_SCALAR
        assert plan.has_year is False

    def test_spanish_multi_dimension(self):
        plan = GrainRouter.route("presupuesto por sector y departamento")
        assert plan.is_valid is False
        assert plan.needs_decomposition is True

    def test_plural_normalization_english(self):
        plan = GrainRouter.route("Budget by sectors and departments")
        assert plan.is_valid is False
        assert plan.needs_decomposition is True
        assert GRAIN_INSTITUTION in plan.detected_grains
        assert GRAIN_GEOGRAPHY in plan.detected_grains

    def test_plural_normalization_spanish(self):
        plan = GrainRouter.route("presupuesto por sectores y departamentos")
        assert plan.is_valid is False
        assert plan.needs_decomposition is True

    def test_activities_plural(self):
        plan = GrainRouter.route("Budget by activities")
        assert plan.is_valid
        assert plan.primary_grain == "activity-level"

    def test_functions_plural(self):
        plan = GrainRouter.route("PIM by government functions")
        assert plan.is_valid
        assert plan.primary_grain == "function-level"

    def test_empty_query(self):
        plan = GrainRouter.route("")
        assert plan.is_valid
        assert plan.primary_grain == GRAIN_SCALAR

    def test_whitespace_only(self):
        plan = GrainRouter.route("   ")
        assert plan.is_valid
        assert plan.primary_grain == GRAIN_SCALAR

    def test_filter_year_not_mistaken_for_grain(self):
        """Numeric year filters (2024) must not trigger year-level grain."""
        plan = GrainRouter.route("PIM by department for 2024")
        assert plan.has_year is False
        assert plan.to_composite_name() == GRAIN_GEOGRAPHY

    def test_explicit_year_grain_with_filter(self):
        """Both explicit year grain and numeric filter year present."""
        plan = GrainRouter.route("Show PIM by department for 2024 by year")
        assert plan.is_valid
        assert plan.primary_grain == GRAIN_GEOGRAPHY
        assert plan.has_year is True
        assert plan.to_composite_name() == "geography_year-level"


class TestGrainPlan:
    """GrainPlan output formatting tests."""

    def test_valid_constraint(self):
        plan = GrainRouter.route("Show PIM by department for 2024")
        constraint = plan.build_llm_constraint()
        assert "geography-level" in constraint
        assert "GROUP BY" in constraint

    def test_multi_dim_constraint(self):
        plan = GrainRouter.route("Show PIM by department and financing source")
        constraint = plan.build_llm_constraint()
        assert "multiple dimension families" in constraint
        assert "CTEs" in constraint

    def test_scalar_constraint(self):
        plan = GrainRouter.route("What was total PIM?")
        constraint = plan.build_llm_constraint()
        assert "Aggregate all rows" in constraint

    def test_year_constraint(self):
        plan = GrainRouter.route("Show budget trends over time")
        constraint = plan.build_llm_constraint()
        assert "year-level" in constraint

    def test_composite_constraint(self):
        plan = GrainRouter.route("Show PIM by department by year")
        constraint = plan.build_llm_constraint()
        assert "geography_year-level" in constraint
