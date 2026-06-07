"""
GrainRouter

Pre-LLM analytical grain classifier for multi-dimensional queries.
Sits BETWEEN natural language input and SQL generation.

Responsibilities:
  1. Classify a user question into canonical analytical grain(s)
  2. Validate grain combinations against allowed composites
  3. Produce a GrainPlan that constrains the LLM's SQL generation
  4. Signal when query decomposition is needed

Integration:
    router = GrainRouter()
    plan   = router.route("Show PIM by department for 2024")
    if plan.is_valid:
        prompt_suffix = plan.build_llm_constraint()
    else:
        # Decompose into sub-questions at each grain

Design principles:
  - Stateless classifier (no LLM, no DB, no Streamlit dependency)
  - Deterministic keyword-based grain detection
  - Single responsibility: grain classification + constraint building
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar


# ---------------------------------------------------------------------------
# Canonical grain taxonomy
# Every analytical query operates at exactly ONE dimension family,
# optionally joined with year-level (time).
# ---------------------------------------------------------------------------

# Maps dimension table → canonical grain name
# Each grain corresponds to a unique GROUP BY dimension family.
GRAIN_ECONOMIC   = "economic-level"
GRAIN_FINANCING  = "financing-level"
GRAIN_GEOGRAPHY  = "geography-level"
GRAIN_INSTITUTION = "institution-level"
GRAIN_PROGRAM    = "program-level"
GRAIN_PROJECT    = "project-level"
GRAIN_FUNCTION   = "function-level"
GRAIN_ACTIVITY   = "activity-level"
GRAIN_YEAR       = "year-level"

# Singleton grain for queries with no dimensional breakdown (total KPIs)
GRAIN_SCALAR     = "scalar"

# All grains that represent a dimension family (excludes year and scalar)
DIMENSION_GRAINS: frozenset[str] = frozenset({
    GRAIN_ECONOMIC,
    GRAIN_FINANCING,
    GRAIN_GEOGRAPHY,
    GRAIN_INSTITUTION,
    GRAIN_PROGRAM,
    GRAIN_PROJECT,
    GRAIN_FUNCTION,
    GRAIN_ACTIVITY,
})

# Valid composite grains: one dimension + optionally year-level.
# Cross-dimensional composites (e.g. geography + financing) are NOT valid
# and require query decomposition.
COMPOSITE_GRAINS: dict[frozenset[str], str] = {
    frozenset({GRAIN_ECONOMIC, GRAIN_YEAR}):      "economic_year-level",
    frozenset({GRAIN_FINANCING, GRAIN_YEAR}):     "financing_year-level",
    frozenset({GRAIN_GEOGRAPHY, GRAIN_YEAR}):     "geography_year-level",
    frozenset({GRAIN_INSTITUTION, GRAIN_YEAR}):   "institution_year-level",
    frozenset({GRAIN_PROGRAM, GRAIN_YEAR}):       "program_year-level",
    frozenset({GRAIN_PROJECT, GRAIN_YEAR}):       "project_year-level",
    frozenset({GRAIN_FUNCTION, GRAIN_YEAR}):      "function_year-level",
    frozenset({GRAIN_ACTIVITY, GRAIN_YEAR}):      "activity_year-level",
}


# Year-as-grain keywords (implies GROUP BY anio, not just a filter)
_YEAR_AS_GRAIN_KEYWORDS: frozenset[str] = frozenset({
    "year", "anio", "año",
    "annual", "anual", "annually", "anualmente",
    "yearly",
    "by year", "por anio", "por año",
    "each year", "cada anio", "cada año",
    "per year", "per anio", "por año",
    "year-over-year", "interanual",
    "year on year",
    "trend", "tendencia",
    "evolution", "evolucion", "evolución",
    "over time", "a lo largo del tiempo",
    "historical", "historico", "histórico",
    "time series", "serie temporal", "serie de tiempo",
})


# ---------------------------------------------------------------------------
# Keyword-to-grain mapping for deterministic question classification
# (English + Spanish)
# ---------------------------------------------------------------------------
GRAIN_KEYWORDS: dict[str, set[str]] = {
    GRAIN_ECONOMIC: {
        "economic", "economico", "economica",
        "expense category", "categoria de gasto", "categoria gasto",
        "generic expense", "generica", "genérica",
        "subgenerica", "subgenérica",
        "especifica", "específica",
    },
    GRAIN_FINANCING: {
        "financing source", "fuente financiamiento", "fuente de financiamiento",
        "financing", "financiamiento",
        "rubro",
        "resource type", "tipo recurso", "tipo de recurso",
    },
    GRAIN_GEOGRAPHY: {
        "department", "departamento",
        "region", "region", "regional",
        "province", "provincia",
        "district", "distrito",
        "geographic", "geografico", "geográfico",
        "geography", "geografia",
        "location", "ubicacion", "ubicación",
        "by department", "por departamento",
        "por region", "por región",
    },
    GRAIN_INSTITUTION: {
        "institution", "institucion", "institución",
        "sector",
        "government level", "nivel gobierno", "nivel de gobierno",
        "national", "nacional",
        "regional",
        "local",
        "pliego",
        "institutional", "institucional",
        "executing unit", "ejecutora", "unidad ejecutora",
    },
    GRAIN_PROGRAM: {
        "program", "programa",
        "budget program", "programa presupuestal",
        "programmatic", "programatica", "programática",
        "ppto",
    },
    GRAIN_PROJECT: {
        "project", "proyecto",
        "product", "producto",
        "investment", "inversion", "inversión",
    },
    GRAIN_FUNCTION: {
        "function", "funcion", "función",
        "government function", "funcion gobierno",
        "functional", "funcional",
    },
    GRAIN_ACTIVITY: {
        "activity", "actividad",
        "action", "accion", "acción",
        "obra",
    },
    GRAIN_YEAR: {
        "year", "anio", "año",
        "annual", "anual", "annually", "anualmente",
        "yearly",
        "by year", "por anio", "por año",
        "each year", "cada anio", "cada año",
        "per year", "per anio", "por año",
        "year-over-year", "interanual",
        "year on year",
        "trend", "tendencia",
        "evolution", "evolucion", "evolución",
        "over time", "a lo largo del tiempo",
        "historical", "historico", "histórico",
        "time series", "serie temporal", "serie de tiempo",
    },
}


# ---------------------------------------------------------------------------
# Domain model: GrainPlan
# ---------------------------------------------------------------------------


@dataclass
class GrainPlan:
    """Result of routing a user question through the GrainRouter.

    Fields:
        primary_grain:   The single dimension grain detected (None if multi-grain).
        has_year:        Whether year-level was detected alongside the dimension.
        detected_grains: All grains detected in the question.
        is_valid:        Whether the grain combination is valid (single dim + optional year).
        needs_decomposition: True when multiple dimension grains detected.
        llm_constraint:  Text string injected into the LLM prompt to constrain SQL.
    """
    primary_grain: str | None = None
    has_year: bool = False
    detected_grains: set[str] = field(default_factory=set)
    is_valid: bool = True
    needs_decomposition: bool = False
    llm_constraint: str = ""

    def to_composite_name(self) -> str | None:
        """Return the composite grain name if valid, else None."""
        if self.primary_grain is None:
            return None
        if self.primary_grain == GRAIN_YEAR:
            return GRAIN_YEAR
        if not self.has_year:
            return self.primary_grain
        key = frozenset({self.primary_grain, GRAIN_YEAR})
        return COMPOSITE_GRAINS.get(key)

    def build_llm_constraint(self) -> str:
        """Build the grain constraint string injected into the LLM prompt."""
        if not self.is_valid:
            return (
                "WARNING: This question spans multiple dimension families. "
                "You MUST decompose it into separate sub-queries connected "
                "via CTEs (WITH ... AS (...)). "
                "Do NOT group by columns from different dimension families "
                "in a single SELECT."
            )
        if self.primary_grain is None:
            return ""
        if self.primary_grain == GRAIN_SCALAR:
            return "Aggregate all rows without GROUP BY."
        composite = self.to_composite_name()
        if composite:
            return f"Analytical grain: {composite}. GROUP BY must stay within one dimension family plus optionally year."
        return f"Analytical grain: {self.primary_grain}. GROUP BY must only use columns from this dimension."


# ---------------------------------------------------------------------------
# GrainRouter: question classifier
# ---------------------------------------------------------------------------


class GrainRouter:
    """Stateless classifier that maps natural language to analytical grain.

    Usage:
        plan = GrainRouter.route("Show PIM by department for 2024")
        if plan.is_valid:
            prompt += plan.llm_constraint
        else:
            decompose(plan, question)
    """

    _keyword_cache: ClassVar[dict[str, str] | None] = None

    @classmethod
    def _build_keyword_index(cls) -> dict[str, str]:
        """Build a reverse index: lowercase keyword → grain name."""
        if cls._keyword_cache is not None:
            return cls._keyword_cache
        index: dict[str, str] = {}
        for grain, keywords in GRAIN_KEYWORDS.items():
            for kw in keywords:
                index[kw.lower()] = grain
        cls._keyword_cache = index
        return index

    @classmethod
    def route(cls, question: str) -> GrainPlan:
        """Classify a user question into an analytical GrainPlan.

        The classification is purely keyword-based, deterministic,
        and O(n) in the number of known keywords.

        Args:
            question: Raw user question string.

        Returns:
            GrainPlan with detected grains, validity flag, and LLM constraint.
        """
        if not question or not question.strip():
            return GrainPlan(
                primary_grain=GRAIN_SCALAR,
                detected_grains={GRAIN_SCALAR},
                is_valid=True,
                llm_constraint="Aggregate all rows without GROUP BY.",
            )

        q_lower = question.lower()
        keyword_index = cls._build_keyword_index()

        # Phase 1: detect all matching grains via keyword scan
        tokenized = cls._tokenize(q_lower)
        detected: set[str] = set()

        for token in tokenized:
            if token in keyword_index:
                detected.add(keyword_index[token])

        # Phase 2: extract primary dimension grain(s)
        has_year = GRAIN_YEAR in detected
        dimension_grains = detected & DIMENSION_GRAINS
        scalar = GRAIN_SCALAR if not dimension_grains and not has_year else None

        # Phase 3: validate grain combination
        if scalar:
            return GrainPlan(
                primary_grain=GRAIN_SCALAR,
                has_year=False,
                detected_grains={GRAIN_SCALAR},
                is_valid=True,
                needs_decomposition=False,
                llm_constraint="Aggregate all rows without GROUP BY.",
            )

        if len(dimension_grains) == 0 and has_year:
            return GrainPlan(
                primary_grain=GRAIN_YEAR,
                has_year=True,
                detected_grains={GRAIN_YEAR},
                is_valid=True,
                needs_decomposition=False,
                llm_constraint="Analytical grain: year-level. GROUP BY f.anio.",
            )

        if len(dimension_grains) == 1:
            primary = next(iter(dimension_grains))
            grain_set = {primary}
            if has_year:
                grain_set.add(GRAIN_YEAR)
            return GrainPlan(
                primary_grain=primary,
                has_year=has_year,
                detected_grains=grain_set,
                is_valid=True,
                needs_decomposition=False,
                llm_constraint="",
            )

        # Multiple dimension grains — requires decomposition
        all_grains = set(dimension_grains)
        if has_year:
            all_grains.add(GRAIN_YEAR)

        return GrainPlan(
            primary_grain=None,
            has_year=has_year,
            detected_grains=all_grains,
            is_valid=False,
            needs_decomposition=True,
            llm_constraint=(
                "WARNING: This question spans multiple dimension families. "
                "You MUST decompose it into separate sub-queries connected "
                "via CTEs (WITH ... AS (...)). "
                "Do NOT group by columns from different dimension families "
                "in a single SELECT."
            ),
        )

    @classmethod
    def _tokenize(cls, text: str) -> list[str]:
        """Split question into tokens for keyword matching.

        Generates unigram, bigram, and trigram candidates.
        Normalizes plurals by stripping trailing 's' from each word
        so 'programs' matches 'program', 'sectors' matches 'sector', etc.
        """
        raw_words = text.split()
        # Normalize: strip trailing 's' for plural handling (e.g. programs -> program)
        words = [
            w[:-1] if len(w) > 3 and w.endswith('s') and not w.endswith('ss') else w
            for w in raw_words
        ]
        tokens: list[str] = []

        for i in range(len(words)):
            tokens.append(words[i])
            if i + 1 < len(words):
                tokens.append(f"{words[i]} {words[i+1]}")
            if i + 2 < len(words):
                tokens.append(f"{words[i]} {words[i+1]} {words[i+2]}")

        return tokens
