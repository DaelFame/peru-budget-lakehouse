"""
Query Execution Trace Model

Complete structured trace for every user query from input to final output.
Captures all stages: LLM generation, semantic validation, SQL execution,
and dashboard rendering.

Usage:
    trace = TraceData(session_id="...", user_query="...")
    trace.start()
    # ... execute stages, each recording on trace ...
    trace.complete()
    trace.emit()  # writes structured JSON log
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: EXECUTION STAGES
# ═══════════════════════════════════════════════════════════════════════════════

class ExecutionStage(Enum):
    """Every stage a query passes through from input to output."""

    USER_INPUT = "USER_INPUT"
    """Raw question received from user or dashboard trigger."""

    INTENT_PARSING = "INTENT_PARSING"
    """LLM or rule-based intent extraction (dashboard section vs AI chat)."""

    SQL_GENERATION = "SQL_GENERATION"
    """LLM produces SQL from the question."""

    SEMANTIC_VALIDATION = "SEMANTIC_VALIDATION"
    """SQLSemanticContractValidator checks grain, scope, aggregation."""

    SQL_EXECUTION = "SQL_EXECUTION"
    """DuckDB executes the final, validated SQL."""

    RESULT_TRANSFORMATION = "RESULT_TRANSFORMATION"
    """Raw DuckDB result converted to DataFrame or JSON for rendering."""

    DASHBOARD_RENDERING = "DASHBOARD_RENDERING"
    """Streamlit + Plotly renders the result."""

    COMPLETED = "COMPLETED"
    """Query lifecycle finished (success or terminal failure)."""

    FAILED = "FAILED"
    """Unhandled exception at any stage."""


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: FAILURE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

class FailureType(Enum):
    """Taxonomy of every failure mode observed in the system."""

    SQL_SYNTAX_ERROR = "SQL_SYNTAX_ERROR"
    """DuckDB rejects the SQL as malformed (unclosed string, bad keyword, etc.).
       Detected at: SQL_EXECUTION stage.
       Root cause: LLM produces syntactically invalid SQL, or hand-written SQL
       has a typo."""

    MISSING_GROUP_BY = "MISSING_GROUP_BY"
    """Column in SELECT is not aggregated AND not in GROUP BY.
       Detected at: SEMANTIC_VALIDATION stage (aggregation consistency check).
       Root cause: LLM omits GROUP BY clause, or adds a non-aggregated column
       without including it in GROUP BY."""

    AMBIGUOUS_ANALYTICAL_GRAIN = "AMBIGUOUS_ANALYTICAL_GRAIN"
    """Grain detector cannot map GROUP BY columns to a known grain signature.
       Detected at: SEMANTIC_VALIDATION stage (grain detection).
       Root cause: LLM uses columns from multiple dimensions without a clear
       primary grain (e.g., GROUP BY sector, program, year simultaneously)."""

    SEMANTIC_CONTRACT_VIOLATION = "SEMANTIC_CONTRACT_VIOLATION"
    """Query fails one of the validator rules (column scope, CTE deps, alias).
       Detected at: SEMANTIC_VALIDATION stage.
       Root cause: LLM references a column not in the star schema, uses an
       undefined CTE alias, or breaks a composite rule."""

    LLM_INTENT_ERROR = "LLM_INTENT_ERROR"
    """LLM misinterprets the user question, producing wrong SQL logic.
       Detected at: SQL_GENERATION stage (output does not match intent).
       Root cause: Ambiguous phrasing in user question, insufficient LLM
       prompt context, or PIM definition inconsistency between dashboard
       and AI prompt."""

    LLM_OUTPUT_PARSE_ERROR = "LLM_OUTPUT_PARSE_ERROR"
    """LLM response cannot be parsed as valid JSON or SQL.
       Detected at: INTENT_PARSING or SQL_GENERATION stage.
       Root cause: LLM returns markdown-wrapped text, extra commentary,
       or malformed JSON that the parser rejects."""

    FILTER_STATE_INCONSISTENCY = "FILTER_STATE_INCONSISTENCY"
    """Active dashboard filters produce an impossible WHERE clause
       (e.g., year=2026 which is always blocked, or mutually exclusive
       dimension filters that return zero rows).
       Detected at: SQL_EXECUTION stage (zero rows returned) or during
       WHERE clause construction in database.py.
       Root cause: User selects filters that contradict each other or
       the 2026 blocking rule. Also triggered when LLM-generated SQL
       does not respect the same filter scope as the dashboard."""

    DATA_JOIN_MISMATCH = "DATA_JOIN_MISMATCH"
    """JOIN condition uses wrong surrogate key or mismatched grain.
       Detected at: SQL_EXECUTION stage (wrong results, not a crash).
       Root cause: LLM joins fact to dimension on wrong key, or the
       dashboard's conditional JOIN optimizer (_needs_geo_join /
       _needs_inst_join) skips a needed join for the active query."""

    EMPTY_RESULT_SET = "EMPTY_RESULT_SET"
    """SQL executes without error but returns zero rows.
       Detected at: SQL_EXECUTION stage (row_count == 0).
       Root cause: Filters too restrictive, wrong dimension JOIN
       eliminates all rows, or the query groups by a level with no
       matching data in the active year."""

    LLM_SYNTHESIS_ERROR = "LLM_SYNTHESIS_ERROR"
    """SQL executed successfully but the LLM synthesis prompt produces
       unparseable or hallucinated narrative.
       Detected at: RESULT_TRANSFORMATION stage.
       Root cause: LLM ignores actual results and fabricates numbers,
       or the synthesis JSON schema does not match the result shape."""

    DASHBOARD_CACHE_STALE = "DASHBOARD_CACHE_STALE"
    """Streamlit @st.cache_data returns stale results because cache
       invalidation did not trigger on filter change.
       Detected at: DASHBOARD_RENDERING stage.
       Root cause: Cache key does not include all filter parameters,
       or streamlit rerun did not clear the relevant cache entry."""


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: STAGE TIMING
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StageTiming:
    """Duration and status for a single execution stage."""

    stage: ExecutionStage
    status: str  # "entered" | "succeeded" | "failed" | "skipped"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None

    def complete(self, error: Optional[str] = None) -> None:
        self.completed_at = datetime.now(timezone.utc)
        self.duration_ms = (
            self.completed_at - self.started_at
        ).total_seconds() * 1000.0
        if error:
            self.status = "failed"
            self.error = error
        else:
            self.status = "succeeded"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: FILTER SNAPSHOT
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FilterSnapshot:
    """Point-in-time capture of all active dashboard filters and context."""

    fiscal_year: Optional[str] = None
    government_level: Optional[str] = None
    sector: Optional[str] = None
    department: Optional[str] = None
    language: Optional[str] = None
    dashboard_section: Optional[str] = None
    """Which section triggered the query: 'kpi_cards', 'concentrations',
       'variance', 'economic_composition', 'financing_structure',
       'programmatic_allocation', 'heatmap', 'ai_chat'."""
    concentration_toggle: Optional[str] = None
    """'Sector' or 'Department' when section is concentrations."""
    variance_toggle: Optional[str] = None
    """'Sector' or 'Department' when section is variance."""
    programmatic_toggle: Optional[str] = None
    """'Budget Program', 'Project', or 'Government Function' when
       section is programmatic_allocation."""
    session_state_keys: Dict[str, Any] = field(default_factory=dict)
    """Snapshot of relevant st.session_state keys for debugging cache
       behavior and stale state."""


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: CORE TRACE DATA MODEL
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TraceData:
    """
    Complete lifecycle trace for a single user query.

    Every mutation method returns self to allow chaining:
        trace = TraceData(session_id="...", user_query="...")
        trace.stage_entered(ExecutionStage.INTENT_PARSING)
        trace.set_llm_output(...)
        trace.stage_completed(ExecutionStage.INTENT_PARSING)
        ...
        trace.emit()
    """

    # ── Identity ──────────────────────────────────────────────────────────
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    session_id: str = ""
    """Correlates multiple queries within one Streamlit session."""

    # ── User input ────────────────────────────────────────────────────────
    user_query: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    origin: str = ""
    """'ai_chat' for free-form NL, or the section name for deterministic
       dashboard queries (e.g., 'kpi_cards', 'concentrations')."""

    # ── Intent ────────────────────────────────────────────────────────────
    parsed_intent: Optional[str] = None
    """For AI queries: the 'intent' field from the synthesis JSON
       (ranking, comparison, geographic, trend, composition, kpi, etc.).
       For dashboard queries: the deterministic section name."""

    # ── LLM layer ─────────────────────────────────────────────────────────
    llm_raw_output: Optional[str] = None
    """Raw LLM response text BEFORE any parsing or fence-stripping.
       Critical for debugging LLM_OUTPUT_PARSE_ERROR failures."""
    llm_structured_output: Optional[Dict[str, Any]] = None
    """Parsed JSON from LLM (the synthesis response). None if parse failed."""

    # ── SQL layer ─────────────────────────────────────────────────────────
    generated_sql: Optional[str] = None
    """The SQL string after LLM generation or hand-written for dashboard.
       For dashboard queries, this is the SQL built by database.py."""
    validated_sql: Optional[str] = None
    """The SQL string AFTER passing QueryValidationPolicy (SELECT-only).
       If no AI involved, same as generated_sql."""

    # ── Semantic validation ───────────────────────────────────────────────
    validated_grain: Optional[str] = None
    """Detected analytical grain from validator (e.g., 'project-level',
       'year-level', 'institution-level'). None if validation was not run."""
    semantic_validation_status: str = "not_run"
    """'passed' | 'failed' | 'not_run'"""
    semantic_validation_errors: List[str] = field(default_factory=list)
    """Error messages from SQLSemanticContractValidator."""

    # ── SQL execution ─────────────────────────────────────────────────────
    sql_execution_status: str = "not_run"
    """'success' | 'failed' | 'not_run'"""
    sql_error_message: Optional[str] = None
    """User-facing error message (the one shown to the user)."""
    duckdb_error: Optional[str] = None
    """Raw DuckDB exception string. NEVER shown to users — diagnostic only."""

    # ── Result metadata ───────────────────────────────────────────────────
    row_count_result: int = 0
    group_by_fields_detected: List[str] = field(default_factory=list)
    """List of columns in the GROUP BY clause (parsed from generated_sql)."""
    metric_detected: Optional[str] = None
    """Primary metric column identified: 'pim', 'devengado', 'execution_rate',
       'monto', or custom alias from LLM query."""

    # ── Performance ───────────────────────────────────────────────────────
    execution_time_ms: float = 0.0
    """Total wall-clock time from trace.start() to trace.complete()."""

    # ── Dashboard context ─────────────────────────────────────────────────
    filters: FilterSnapshot = field(default_factory=FilterSnapshot)
    dashboard_context: Optional[str] = None
    """Which module triggered the query — used to distinguish AI vs
       deterministic dashboard paths."""

    # ── Result preview ────────────────────────────────────────────────────
    result_preview: Optional[List[Dict[str, Any]]] = None
    """First N rows of the result as a list of dicts. Helps debug empty
       result sets and grain mismatches."""

    # ── Stage timing ──────────────────────────────────────────────────────
    stages: List[StageTiming] = field(default_factory=list)
    _start_time: float = field(default_factory=time.time, repr=False)

    # ── Failure details ───────────────────────────────────────────────────
    failure_type: Optional[FailureType] = None
    failure_description: Optional[str] = None
    """Human-readable description of the primary failure."""

    # ── Session metadata ──────────────────────────────────────────────────
    app_version: str = "2.0"
    streamlit_rerun_count: int = 0
    """Track how many Streamlit reruns occurred during this query."""

    # ════════════════════════════════════════════════════════════════════
    # LIFE CYCLE METHODS
    # ════════════════════════════════════════════════════════════════════

    def start(self) -> TraceData:
        self._start_time = time.time()
        return self

    def complete(self) -> TraceData:
        self.execution_time_ms = (time.time() - self._start_time) * 1000.0
        self.stages.append(StageTiming(stage=ExecutionStage.COMPLETED, status="succeeded"))
        return self

    def stage_entered(self, stage: ExecutionStage) -> TraceData:
        self.stages.append(
            StageTiming(stage=stage, status="entered")
        )
        return self

    def stage_completed(
        self,
        stage: ExecutionStage,
        error: Optional[str] = None,
    ) -> TraceData:
        for s in reversed(self.stages):
            if s.stage == stage and s.status == "entered":
                s.complete(error=error)
                break
        return self

    def fail(
        self,
        failure_type: FailureType,
        description: str,
        stage: Optional[ExecutionStage] = None,
    ) -> TraceData:
        self.failure_type = failure_type
        self.failure_description = description
        self.stages.append(
            StageTiming(
                stage=stage or ExecutionStage.FAILED,
                status="failed",
                error=description,
            )
        )
        return self

    # ════════════════════════════════════════════════════════════════════
    # FIELD MUTATORS (chained)
    # ════════════════════════════════════════════════════════════════════

    def set_user_query(self, query: str) -> TraceData:
        self.user_query = query
        return self

    def set_llm_output(self, raw: str, structured: Optional[Dict] = None) -> TraceData:
        self.llm_raw_output = raw
        self.llm_structured_output = structured
        return self

    def set_sql(self, sql: str) -> TraceData:
        self.generated_sql = sql
        self._detect_group_by(sql)
        return self

    def set_validated_sql(self, sql: str) -> TraceData:
        self.validated_sql = sql
        return self

    def set_semantic_result(
        self,
        is_valid: bool,
        grain: Optional[str],
        errors: List[str],
    ) -> TraceData:
        self.validated_grain = grain
        self.semantic_validation_status = "passed" if is_valid else "failed"
        self.semantic_validation_errors = errors
        return self

    def set_execution_result(
        self,
        status: str,
        row_count: int,
        error_message: Optional[str] = None,
        duckdb_error: Optional[str] = None,
        preview: Optional[List[Dict]] = None,
    ) -> TraceData:
        self.sql_execution_status = status
        self.row_count_result = row_count
        self.sql_error_message = error_message
        self.duckdb_error = duckdb_error
        self.result_preview = preview
        return self

    def set_filters(self, filters: FilterSnapshot) -> TraceData:
        self.filters = filters
        return self

    def set_metric(self, metric: Optional[str]) -> TraceData:
        self.metric_detected = metric
        return self

    def set_intent(self, intent: Optional[str]) -> TraceData:
        self.parsed_intent = intent
        return self

    # ════════════════════════════════════════════════════════════════════
    # INTERNAL
    # ════════════════════════════════════════════════════════════════════

    def _detect_group_by(self, sql: str) -> None:
        """Naive GROUP BY column extraction for trace metadata."""
        import re
        match = re.search(
            r"GROUP\s+BY\s+(.+)",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        if not match:
            self.group_by_fields_detected = []
            return

        group_clause = match.group(1).split("ORDER BY")[0].split("HAVING")[0]
        parts = [p.strip().strip(",") for p in group_clause.split(",")]
        # Remove numeric positional references (e.g., "GROUP BY 1, 2")
        self.group_by_fields_detected = [
            p for p in parts if p and not p.isdigit()
        ]

    # ════════════════════════════════════════════════════════════════════
    # SERIALIZATION
    # ════════════════════════════════════════════════════════════════════

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict for structured logging."""
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        d["failure_type"] = self.failure_type.value if self.failure_type else None
        d["stages"] = [
            {
                "stage": s.stage.value,
                "status": s.status,
                "started_at": s.started_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "duration_ms": round(s.duration_ms, 2) if s.duration_ms else None,
                "error": s.error,
            }
            for s in self.stages
        ]
        # Remove raw LLM output from default log to keep payload small;
        # it can be stored separately for full-reproduction debugging.
        d.pop("_start_time", None)
        return d

    def emit(self, logger_override: Optional[logging.Logger] = None) -> None:
        """Write structured JSON trace to the observability log.

        Output format per line:
            {"trace": <trace_id>, "event": "query_complete", ...fields}

        This is a single-line JSON object (not pretty-printed) for
        ingestion into log aggregators (ELK, Datadog, etc.).
        """
        log = logger_override or logger
        payload = {
            "trace": self.trace_id,
            "event": "query_complete",
            **self.to_dict(),
        }
        log.info(json.dumps(payload, default=str))


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: DASHBOARD-ORIGIN TRACE HELPER
# ═══════════════════════════════════════════════════════════════════════════════

def build_dashboard_trace(
    session_id: str,
    section: str,
    user_query: str,
    filters: FilterSnapshot,
) -> TraceData:
    """
    Factory for deterministic dashboard query traces (non-AI).

    Dashboard sections do not go through LLM stages, so those stages
    are marked 'skipped'. The trace still captures SQL execution and
    result metadata for end-to-end observability.
    """
    trace = TraceData(
        session_id=session_id,
        user_query=user_query,
        origin=section,
        parsed_intent=section,
        dashboard_context=section,
        filters=filters,
    )
    trace.start()
    trace.stage_entered(ExecutionStage.INTENT_PARSING)
    trace.stage_completed(ExecutionStage.INTENT_PARSING)
    trace.stage_entered(ExecutionStage.SQL_GENERATION)
    # SQL will be set by the calling code after database.py runs
    trace.stage_completed(ExecutionStage.SQL_GENERATION)
    return trace


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7: AI-ORIGIN TRACE HELPER
# ═══════════════════════════════════════════════════════════════════════════════

def build_ai_trace(
    session_id: str,
    question: str,
    filters: FilterSnapshot,
) -> TraceData:
    """
    Factory for AI chat query traces.

    Captures the full NL → SQL → validate → execute → synthesize pipeline.
    """
    trace = TraceData(
        session_id=session_id,
        user_query=question,
        origin="ai_chat",
        dashboard_context="ai_chat",
        filters=filters,
    )
    trace.start()
    return trace
