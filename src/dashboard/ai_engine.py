"""
AI-Powered Conversational Engine for Budget Intelligence

Clean Architecture Layers:
  Domain:     QueryValidationPolicy, schema context (pure business logic)
  Application: AIEngine (orchestrates NL -> SQL -> execute -> synthesize)
  Infra:      Groq client adapter (via groq SDK)

Decoupled from Streamlit and DuckDB - dependencies injected via constructor.
"""

import json
import logging
from typing import Any, Callable

from groq import Groq
import sqlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DOMAIN LAYER: Security policy - SELECT-only enforcement
# ---------------------------------------------------------------------------
class QueryValidationPolicy:
    """Parses and validates that SQL statements are SELECT-only."""

    FORBIDDEN_KEYWORDS = frozenset({
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
        "TRUNCATE", "EXEC", "EXECUTE", "CALL", "MERGE", "REPLACE",
        "GRANT", "REVOKE", "ATTACH", "DETACH", "LOAD", "INSTALL",
        "COPY", "IMPORT", "EXPORT", "ALTER", "RENAME",
    })

    @classmethod
    def validate(cls, sql: str) -> str:
        parsed = sqlparse.parse(sql)
        if len(parsed) != 1:
            raise ValueError("Only single SELECT statements are allowed.")

        stmt = parsed[0]
        first = stmt.token_first(skip_cm=True, skip_ws=True)
        if first is None or first.value.upper() != "SELECT":
            raise ValueError("Only SELECT statements are permitted.")

        for token in stmt.flatten():
            if token.value.upper() in cls.FORBIDDEN_KEYWORDS:
                raise ValueError(
                    f"Forbidden keyword '{token.value}' detected."
                )

        return str(stmt).strip()


# ---------------------------------------------------------------------------
# DOMAIN LAYER: Star Schema context (describes the Gold layer to the LLM)
# ---------------------------------------------------------------------------
STAR_SCHEMA_DESCRIPTION = """
You are a DuckDB SQL expert for Peru's National Budget database (MEF).

SCHEMA (Gold Star Schema - Kimball dimensional model):

TABLE: fact_presupuesto (Fact table - 1.2B+ rows)
  sk_geografia_id      BIGINT  FK -> dim_geografia
  sk_institucion_id    BIGINT  FK -> dim_institucion
  sk_programatica_id   BIGINT  FK -> dim_programatica
  sk_economica_id      BIGINT  FK -> dim_economica
  sk_financiamiento_id BIGINT  FK -> dim_financiamiento
  ano_eje              INTEGER Fiscal year (2022, 2023, 2024)
  fase                 VARCHAR Budget phase: pim | certificado | devengado | girado (stored in strict lowercase)
  monto                DOUBLE  Amount in Peruvian Soles (S/)

TABLE: dim_geografia (Geography)
  sk_geografia_id         BIGINT  PK
  departamento_ejecutora  VARCHAR Code
  departamento_ejecutora_nombre VARCHAR Name (stored in strict lowercase and without accents, e.g. 'lima', 'cusco')
  provincia_ejecutora     VARCHAR Code
  provincia_ejecutora_nombre    VARCHAR Name
  distrito_ejecutora      VARCHAR Code
  distrito_ejecutora_nombre     VARCHAR Name

TABLE: dim_institucion (Institution)
  sk_institucion_id    BIGINT  PK
  nivel_gobierno       VARCHAR Code
  nivel_gobierno_nombre VARCHAR National | Regional | Local (stored in strict lowercase and without accents)
  sector               VARCHAR Code
  sector_nombre        VARCHAR Name (stored in strict lowercase and without accents, e.g. 'educacion', 'salud')
  pliego               VARCHAR Code
  pliego_nombre        VARCHAR Institutional name
  sec_ejec             VARCHAR Code
  ejecutora            VARCHAR Code
  ejecutora_nombre     VARCHAR Executing unit name

TABLE: dim_programatica (Programmatic classification)
  sk_programatica_id      BIGINT  PK
  programa_ppto           VARCHAR Budget program code
  programa_ppto_nombre    VARCHAR Budget program name
  producto_proyecto       VARCHAR Code
  producto_proyecto_nombre VARCHAR Product/project name
  actividad_accion_obra   VARCHAR Code
  actividad_accion_obra_nombre  VARCHAR Activity name
  funcion                 VARCHAR Code
  funcion_nombre          VARCHAR Function (stored in strict lowercase and without accents)
  meta                    VARCHAR Code
  meta_nombre             VARCHAR Goal description

TABLE: dim_economica (Economic classification)
  sk_economica_id     BIGINT  PK
  generica            VARCHAR Generic expense code
  generica_nombre     VARCHAR Generic expense name
  subgenerica         VARCHAR Code
  subgenerica_nombre  VARCHAR Name
  especifica          VARCHAR Code
  especifica_nombre   VARCHAR Name

TABLE: dim_financiamiento (Financing source)
  sk_financiamiento_id    BIGINT  PK
  fuente_financiamiento         VARCHAR Code
  fuente_financiamiento_nombre  VARCHAR Financing source name (stored in strict lowercase and without accents)
  rubro                         VARCHAR Code
  rubro_nombre                  VARCHAR Category name
  tipo_recurso                  VARCHAR Code
  tipo_recurso_nombre           VARCHAR Resource type
  categoria_gasto               VARCHAR Code
  categoria_gasto_nombre        VARCHAR Spending category

CRITICAL BUSINESS & SECURITY RULES:
  - THE 2026 RULE: NEVER allow the year 2026 under any circumstances. You must ALWAYS append `f.ano_eje <= 2025` in the generated SQL query (e.g. `WHERE f.ano_eje <= 2025` or `AND f.ano_eje <= 2025`). This is a strict business policy due to cloned source data.
  - PIM (Planned budget)  = SUM(monto) WHERE fase IN ('pim', 'certificado')
  - Devengado (Executed)  = SUM(monto) WHERE fase = 'devengado'
  - Execution rate (%)    = (Devengado / PIM) * 100
  - Girado (Disbursed)   = SUM(monto) WHERE fase = 'girado'

TEXT NORMALIZATION AND QUERY RULES:
  - Database dimensions (departments, sectors, phases, etc.) are in strict lowercase and without accents (accents/diacritics are removed).
  - You MUST always use `ILIKE '%term%'` for string filters instead of exact equality (`=`) to ensure case-insensitive matching and robustness against accents or trailing spaces.
  - Return ONLY the SQL. No markdown, backticks, or explanations.
  - Use DuckDB syntax: LEFT JOIN, CASE WHEN, COALESCE, NULLIF.
  - IMPORTANT: ALWAYS use these exact aliases for the tables:
      * fact_presupuesto AS f
      * dim_geografia AS g
      * dim_institucion AS i
      * dim_programatica AS p
      * dim_economica AS e
      * dim_financiamiento AS fi
  - NEVER use aliases that are not defined in the JOINs.
  - File paths are NOT needed - tables are already registered as views.
  - Never use INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, or any DDL/DML.
  - If a user asks multiple questions, consolidate all required data into ONE single SELECT query.

MULTILINGUAL EXECUTION:
  - Detect the language of the user's prompt and respond entirely in that exact same language.

EXAMPLES:
Q: What was the total PIM for 2024?
SQL: SELECT SUM(CASE WHEN f.fase IN ('pim', 'certificado') THEN f.monto ELSE 0 END) AS total_pim FROM fact_presupuesto f WHERE f.ano_eje = 2024 AND f.ano_eje <= 2025

Q: Which sector had the highest execution rate in 2023?
SQL: SELECT i.sector_nombre AS sector,
       SUM(CASE WHEN f.fase = 'devengado' THEN f.monto ELSE 0 END) /
       NULLIF(SUM(CASE WHEN f.fase IN ('pim', 'certificado') THEN f.monto ELSE 0 END), 0) * 100
       AS execution_rate
FROM fact_presupuesto f
LEFT JOIN dim_institucion i ON f.sk_institucion_id = i.sk_institucion_id
WHERE f.ano_eje = 2023 AND f.ano_eje <= 2025
GROUP BY sector ORDER BY execution_rate DESC

Q: Show top 5 departments by PIM in 2024
SQL: SELECT g.departamento_ejecutora_nombre AS department,
       SUM(CASE WHEN f.fase IN ('pim', 'certificado') THEN f.monto ELSE 0 END) AS total_pim
FROM fact_presupuesto f
LEFT JOIN dim_geografia g ON f.sk_geografia_id = g.sk_geografia_id
WHERE f.ano_eje = 2024 AND f.ano_eje <= 2025
GROUP BY department ORDER BY total_pim DESC LIMIT 5

Q: Compare PIM against Devengado for each government level in 2024
SQL: SELECT i.nivel_gobierno_nombre AS government_level,
       SUM(CASE WHEN f.fase IN ('pim', 'certificado') THEN f.monto ELSE 0 END) AS pim,
       SUM(CASE WHEN f.fase = 'devengado' THEN f.monto ELSE 0 END) AS devengado
FROM fact_presupuesto f
LEFT JOIN dim_institucion i ON f.sk_institucion_id = i.sk_institucion_id
WHERE f.ano_eje = 2024 AND f.ano_eje <= 2025
GROUP BY government_level ORDER BY pim DESC

Q: What is the budget by financing source for 2024?
SQL: SELECT fi.fuente_financiamiento_nombre AS financing_source,
       SUM(CASE WHEN f.fase IN ('pim', 'certificado') THEN f.monto ELSE 0 END) AS total_pim
FROM fact_presupuesto f
LEFT JOIN dim_financiamiento fi ON f.sk_financiamiento_id = fi.sk_financiamiento_id
WHERE f.ano_eje = 2024 AND f.ano_eje <= 2025
GROUP BY financing_source ORDER BY total_pim DESC
"""

SYSTEM_PROMPT_TEMPLATE = """{schema}

{language_instruction}
{conversation_history}
User question: {question}

SQL:"""

SYNTHESIS_PROMPT_TEMPLATE = """You are a senior financial analyst for Peru's National Budget.

Based on the query and results, provide a highly structured executive analysis.
You MUST respond with a single, valid JSON object following the exact schema below.

CRITICAL INSTRUCTIONS:
1. MULTILINGUAL EXECUTION: Detect the language used in the user's question. Write the "title", "executive_summary", "main_metric.label", "chart.title", "insights", and "followups" entirely in that exact same language (e.g., if the user writes in Spanish, respond entirely in Spanish; if in English, respond entirely in English).
2. TOKEN SAVING & ZERO HALLUCINATION: You only receive the resulting rows returned internally by DuckDB. If DuckDB returns 0 rows (the results list is empty), you MUST set "executive_summary" to "No data found" (or "No se encontraron datos" if responding in Spanish), set "main_metric" to null, set "chart" to null, and you are strictly forbidden from hallucinating or fabricating any numbers, metrics, or financial data.
3. INFORMATION DISCLOSURE: Never reveal any SQL queries, database/table names, or internal technical schema/alias names (such as f, g, i, p, e, fi, ano_eje, etc.) in the natural language text fields. Keep all text fields focused purely on clean, professional business and financial terms.
4. STRICT OUTPUT FORMAT: Return ONLY the raw JSON object. Do NOT wrap the JSON in markdown fences (e.g. do NOT use ```json ... ```). Do NOT use triple backticks. Do NOT explain the JSON. Do NOT include any introductory or concluding text.

JSON SCHEMA:
{{
  "intent": "ranking | trend | comparison | geographic | composition | anomaly | distribution | kpi",
  "title": "Short executive title (under 10 words)",
  "executive_summary": "Short executive-level insight (maximum 3 sentences summarizing the key takeaway)",
  "main_metric": {{
    "label": "Metric label (e.g., 'Total PIM 2024' or 'Arequipa Devengado')",
    "value": 0.0,
    "formatted": "S/. 0.0 M or similar formatted string in Peruvian Soles (use 'S/.' for currency)"
  }},
  "chart": {{
    "type": "horizontal_bar | line | grouped_bar | heatmap | stacked_bar | treemap | metric",
    "title": "Chart title",
    "x": "column_name for the x-axis from the results, or null",
    "y": "column_name for the y-axis from the results, or null",
    "data": [
      // array of objects representing the chart data matching the results rows
    ]
  }},
  "insights": [
    "Insight 1 (concise financial takeaway)",
    "Insight 2 (concise financial takeaway)"
  ],
  "followups": [
    "Suggested follow-up question 1",
    "Suggested follow-up question 2"
  ]
}}

User question: {question}
SQL query: {query}
Results ({row_count} total rows, showing top {displayed}):
{results}

{language_instruction}
JSON:"""


# ---------------------------------------------------------------------------
# APPLICATION LAYER: AI Engine (use case orchestrator)
# ---------------------------------------------------------------------------
class AIEngine:
    """
    Orchestrates the RAG pipeline: NL -> SQL -> execute -> synthesize.

    Decoupled from Streamlit and DuckDB. Accepts a connection factory
    function via dependency injection.
    """

    def __init__(
        self,
        api_key: str,
        db_connect_fn: Callable[[], Any],
        model_name: str = "llama-3.3-70b-versatile",
        max_result_rows: int = 20,
    ) -> None:
        self._client = Groq(api_key=api_key)
        self._model_name = model_name
        self._db_connect = db_connect_fn
        self._max_rows = max_result_rows

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------
    def ask(
        self,
        question: str,
        lang: str = "en",
        conversation_history: list[dict] | None = None,
    ) -> dict:
        """
        Full RAG pipeline: NL -> SQL -> Execute -> Synthesize.

        Args:
            question: User's natural language question.
            lang: 'en' or 'es'.
            conversation_history: Previous messages for context.

        Returns:
            dict with keys: question, sql, results, row_count, summary,
                            error, success.
        """
        try:
            sql = self._translate_to_sql(question, lang, conversation_history)
            sql = QueryValidationPolicy.validate(sql)
            results, row_count = self._execute(sql)
            summary = self._synthesize(question, sql, results, row_count, lang)

            return {
                "question": question,
                "sql": sql,
                "results": results,
                "row_count": row_count,
                "summary": summary,
                "error": None,
                "success": True,
            }

        except Exception as exc:
            logger.error("AIEngine error: %s", exc)
            return {
                "question": question,
                "sql": None,
                "results": [],
                "row_count": 0,
                "summary": None,
                "error": str(exc),
                "success": False,
            }

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------
    def _build_sql_messages(
        self,
        question: str,
        lang: str,
        conversation_history: list[dict] | None = None,
    ) -> list[dict]:
        lang_instruction = (
            "Answer in English. Use English column aliases."
            if lang == "en"
            else "Answer in Spanish. Use Spanish column aliases."
        )
        system_prompt = f"{STAR_SCHEMA_DESCRIPTION}\n\n{lang_instruction}"

        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            for msg in conversation_history[-6:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": f"User question: {question}\n\nSQL:"})
        return messages

    def _translate_to_sql(
        self,
        question: str,
        lang: str,
        conversation_history: list[dict] | None = None,
    ) -> str:
        messages = self._build_sql_messages(question, lang, conversation_history)
        response = self._client.chat.completions.create(
            model=self._model_name,
            messages=messages,
        )
        sql = response.choices[0].message.content.strip()

        if sql.startswith("```"):
            lines = sql.splitlines()
            sql = "\n".join(lines[1:-1]) if len(lines) > 2 else sql[3:]
        sql = sql.strip().rstrip(";")
        return sql

    def _execute(self, sql: str) -> tuple[list[dict], int]:
        con = self._db_connect()
        result = con.execute(sql).fetchall()
        columns = [desc[0] for desc in con.description] if con.description else []
        rows = [dict(zip(columns, row)) for row in result[: self._max_rows]]
        return rows, len(result)

    def _synthesize(
        self,
        question: str,
        sql: str,
        results: list[dict],
        row_count: int,
        lang: str,
    ) -> dict:
        results_str = json.dumps(
            results, indent=2, default=str, ensure_ascii=False
        )
        lang_instruction = (
            "Answer in English." if lang == "en" else "Answer in Spanish."
        )
        user_prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
            question=question,
            query=sql,
            results=results_str,
            row_count=row_count,
            displayed=len(results),
            language_instruction=lang_instruction,
        )
        response = self._client.chat.completions.create(
            model=self._model_name,
            messages=[
                {"role": "system", "content": "You are a senior financial analyst for Peru's National Budget. You respond ONLY with valid raw JSON."},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw_response = response.choices[0].message.content.strip()

        # Log the raw LLM response for debugging
        logger.debug("Raw LLM Response for Synthesis: %s", raw_response)

        # Clean markdown fences if they exist
        clean_response = raw_response
        if clean_response.startswith("```"):
            lines = clean_response.splitlines()
            if len(lines) > 2:
                if lines[0].strip().startswith("```"):
                    lines = lines[1:]
                if lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean_response = "\n".join(lines).strip()
            else:
                clean_response = clean_response.replace("```json", "").replace("```", "").strip()
        else:
            clean_response = clean_response.strip("`").strip()

        # Handle any trailing or leading accidental text from LLM gracefully by extracting the first { to last }
        try:
            first_brace = clean_response.index("{")
            last_brace = clean_response.rindex("}")
            clean_response = clean_response[first_brace:last_brace + 1].strip()
        except ValueError:
            pass

        try:
            parsed_json = json.loads(clean_response)
            logger.info("Successfully parsed structured JSON response from AI synthesis.")
            return parsed_json
        except Exception as err:
            logger.error("Failed to parse structured JSON response: %s", err)
            logger.error("Raw response that failed parsing: %s", raw_response)
            return {
                "intent": "error",
                "title": "AI Response Error",
                "executive_summary": "The AI response could not be parsed correctly.",
                "main_metric": None,
                "chart": None,
                "insights": [
                    "JSON parsing failed."
                ],
                "followups": []
            }
