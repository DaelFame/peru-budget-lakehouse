"""
SQLSemanticContractValidator

Independent semantic correctness layer for analytical SQL.
Sits between QueryValidationPolicy (security) and DuckDB execution.

Responsibilities:
  1. Grain Detection - infer analytical grain from GROUP BY columns
  2. Column Scope Validation - every column ref must exist in schema or CTE
  3. Aggregation Consistency - non-aggregated SELECT cols must be in GROUP BY
  4. CTE Dependency Graph Validation - all CTE refs exist, projections valid

Integration:
    from semantic_contract import SQLSemanticContractValidator
    result = SQLSemanticContractValidator.validate(sql)
    if not result.is_valid:
        raise ValueError(f"Semantic violation: {'; '.join(result.errors)}")
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

import sqlparse
from sqlparse.sql import (
    Case,
    Comparison,
    Function,
    Identifier,
    IdentifierList,
    Operation,
    Parenthesis,
    Where,
)
from sqlparse.tokens import (
    CTE,
    DML,
    Keyword,
    Punctuation,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    is_valid: bool = True
    grain: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Known star-schema metadata
# ---------------------------------------------------------------------------

STAR_SCHEMA_TABLES: dict[str, set[str]] = {
    "fact_presupuesto": {
        "sk_geografia_id", "sk_institucion_id", "sk_programatica_id",
        "sk_economica_id", "sk_financiamiento_id", "anio", "fase", "monto",
    },
    "dim_geografia": {
        "sk_geografia_id",
        "departamento_ejecutora", "departamento_ejecutora_nombre",
        "provincia_ejecutora", "provincia_ejecutora_nombre",
        "distrito_ejecutora", "distrito_ejecutora_nombre",
    },
    "dim_institucion": {
        "sk_institucion_id",
        "nivel_gobierno", "nivel_gobierno_nombre",
        "sector", "sector_nombre",
        "pliego", "pliego_nombre",
        "sec_ejec", "ejecutora", "ejecutora_nombre",
    },
    "dim_programatica": {
        "sk_programatica_id",
        "programa_ppto", "programa_ppto_nombre",
        "producto_proyecto", "producto_proyecto_nombre",
        "actividad_accion_obra", "actividad_accion_obra_nombre",
        "funcion", "funcion_nombre",
        "meta", "meta_nombre",
    },
    "dim_economica": {
        "sk_economica_id",
        "generica", "generica_nombre",
        "subgenerica", "subgenerica_nombre",
        "especifica", "especifica_nombre",
    },
    "dim_financiamiento": {
        "sk_financiamiento_id",
        "fuente_financiamiento", "fuente_financiamiento_nombre",
        "rubro", "rubro_nombre",
        "tipo_recurso", "tipo_recurso_nombre",
        "categoria_gasto", "categoria_gasto_nombre",
    },
}

DEFAULT_ALIASES: dict[str, str] = {
    "f": "fact_presupuesto",
    "g": "dim_geografia",
    "i": "dim_institucion",
    "p": "dim_programatica",
    "e": "dim_economica",
    "fi": "dim_financiamiento",
}

ALL_TABLE_COLUMNS: dict[str, set[str]] = {}
for tbl, cols in STAR_SCHEMA_TABLES.items():
    ALL_TABLE_COLUMNS[tbl] = set(cols)
    ALL_TABLE_COLUMNS[tbl.lower()] = set(cols)

_COLUMN_FREQ: dict[str, int] = defaultdict(int)
for cols in STAR_SCHEMA_TABLES.values():
    for c in cols:
        _COLUMN_FREQ[c] += 1

UNIQUE_COLUMN_OWNER: dict[str, str] = {}
for c, freq in _COLUMN_FREQ.items():
    if freq == 1:
        for tbl, cols in STAR_SCHEMA_TABLES.items():
            if c in cols:
                UNIQUE_COLUMN_OWNER[c] = tbl
                break

AGGREGATE_FUNCTIONS: frozenset = frozenset({
    "SUM", "COUNT", "AVG", "MIN", "MAX",
    "STDDEV", "VARIANCE", "ARRAY_AGG",
})

GRAIN_SIGNATURES: dict[str, set[str]] = {
    "project-level": {
        "producto_proyecto_nombre", "producto_proyecto",
        "sk_programatica_id",
        "project", "proyecto",
    },
    "year-level": {
        "anio", "year",
    },
    "institution-level": {
        "pliego_nombre", "pliego",
        "sector_nombre", "sector",
        "nivel_gobierno_nombre", "nivel_gobierno",
        "ejecutora_nombre", "ejecutora",
        "sk_institucion_id",
        "institution",
    },
    "program-level": {
        "programa_ppto_nombre", "programa_ppto",
        "program", "programa",
    },
    "geography-level": {
        "departamento_ejecutora_nombre", "departamento_ejecutora",
        "provincia_ejecutora_nombre", "provincia_ejecutora",
        "distrito_ejecutora_nombre", "distrito_ejecutora",
        "department", "departamento",
    },
    "economic-level": {
        "generica_nombre", "generica",
        "subgenerica_nombre", "subgenerica",
        "especifica_nombre", "especifica",
    },
    "financing-level": {
        "fuente_financiamiento_nombre", "fuente_financiamiento",
        "rubro_nombre", "rubro",
        "tipo_recurso_nombre", "tipo_recurso",
        "categoria_gasto_nombre", "categoria_gasto",
    },
    "function-level": {
        "funcion_nombre", "funcion",
    },
    "activity-level": {
        "actividad_accion_obra_nombre", "actividad_accion_obra",
    },
}

COMPOSITE_GRAINS: dict[frozenset[str], str] = {
    frozenset({"project-level", "year-level"}):      "project_year-level",
    frozenset({"institution-level", "year-level"}):  "institution_year-level",
    frozenset({"program-level", "year-level"}):      "program_year-level",
    frozenset({"geography-level", "year-level"}):    "geography_year-level",
    frozenset({"economic-level", "year-level"}):     "economic_year-level",
    frozenset({"financing-level", "year-level"}):    "financing_year-level",
    frozenset({"function-level", "year-level"}):     "function_year-level",
    frozenset({"activity-level", "year-level"}):     "activity_year-level",
}


# ---------------------------------------------------------------------------
# Helper: identifier resolution
# ---------------------------------------------------------------------------


def _get_qualifier(identifier: Identifier) -> str | None:
    return identifier.get_parent_name()


def _get_alias(identifier: Identifier) -> str | None:
    alias = identifier.get_alias()
    return alias


def _resolve_table(alias: str, alias_map: dict[str, str],
                   cte_names: set[str]) -> str | None:
    if alias in alias_map:
        return alias_map[alias]
    if alias in DEFAULT_ALIASES:
        return DEFAULT_ALIASES[alias]
    if alias in cte_names:
        return alias
    return None


def _get_table_column_set(table_name: str) -> set[str]:
    if table_name in ALL_TABLE_COLUMNS:
        return ALL_TABLE_COLUMNS[table_name]
    for key, cols in ALL_TABLE_COLUMNS.items():
        if key.lower() == table_name.lower():
            return cols
    return set()


# ---------------------------------------------------------------------------
# SQL parsing helpers
# ---------------------------------------------------------------------------


@dataclass
class ColumnRef:
    expression: str
    alias: str | None
    table_qualifier: str | None
    is_aggregated: bool
    is_wildcard: bool = False


@dataclass
class QueryParts:
    select_columns: list[ColumnRef] = field(default_factory=list)
    from_tables: dict[str, str] = field(default_factory=dict)
    alias_to_table: dict[str, str] = field(default_factory=dict)
    where_columns: list[ColumnRef] = field(default_factory=list)
    join_columns: list[ColumnRef] = field(default_factory=list)
    group_by_exprs: list[str] = field(default_factory=list)
    order_by_exprs: list[str] = field(default_factory=list)
    has_aggregation: bool = False
    cte_references: set[str] = field(default_factory=set)


def _identifier_is_simple(ident: Identifier) -> bool:
    """Check if an Identifier is a simple column ref (not a function call etc)."""
    for t in ident.tokens:
        if isinstance(t, (Function, Case, Comparison, Parenthesis)):
            return False
        if t.is_whitespace:
            continue
        if t.ttype is Keyword and t.value.upper() in ('AS',):
            # Has an alias, but the main part is still simple
            # Check what's before AS
            break
    return True


def _collect_identifier_columns(token, collected: list[ColumnRef],
                                in_aggregate: bool = False) -> None:
    """Recursively extract column references from a token tree."""
    if isinstance(token, IdentifierList):
        for child in token.tokens:
            _collect_identifier_columns(child, collected, in_aggregate)
        return

    if isinstance(token, Identifier):
        has_complex = any(
            isinstance(t, (Function, Case, Comparison, Parenthesis, Operation))
            for t in token.tokens
        )
        if has_complex:
            alias = _get_alias(token)
            for t in token.tokens:
                if isinstance(t, (Function, Case, Comparison, Parenthesis, Operation)):
                    _collect_identifier_columns(t, collected, in_aggregate)
            if alias and collected:
                collected[-1].alias = alias
            return

        alias = _get_alias(token)
        real_name = token.get_real_name()
        parent = _get_qualifier(token)

        if real_name and real_name != '*':
            collected.append(ColumnRef(
                expression=real_name,
                alias=alias,
                table_qualifier=parent,
                is_aggregated=in_aggregate,
            ))
        elif not real_name:
            name = token.value.strip()
            if name and name != '*':
                collected.append(ColumnRef(
                    expression=name,
                    alias=alias,
                    table_qualifier=parent,
                    is_aggregated=in_aggregate,
                ))
        return

    if isinstance(token, Function):
        func_name = token.tokens[0].value.upper() if token.tokens else ""
        is_agg = func_name in AGGREGATE_FUNCTIONS
        for t in token.tokens:
            if t is token.tokens[0]:
                continue
            if isinstance(t, Parenthesis):
                _collect_identifier_columns(t, collected, in_aggregate or is_agg)
            elif not t.is_whitespace:
                _collect_identifier_columns(t, collected, in_aggregate or is_agg)
        return

    if isinstance(token, (Parenthesis, Case, Comparison, Where)):
        for t in token.tokens:
            _collect_identifier_columns(t, collected, in_aggregate)
        return

    if isinstance(token, sqlparse.sql.TokenList):
        for t in token.tokens:
            _collect_identifier_columns(t, collected, in_aggregate)


def _check_aggregation_in_token(token) -> bool:
    if isinstance(token, Function):
        func_name = token.tokens[0].value.upper() if token.tokens else ""
        if func_name in AGGREGATE_FUNCTIONS:
            return True
    if isinstance(token, (Parenthesis, sqlparse.sql.TokenList)):
        for t in token.tokens:
            if _check_aggregation_in_token(t):
                return True
    return False


def _iter_top_level_tokens(stmt):
    """Iterate top-level tokens of a statement, yielding (token, is_where)."""
    for token in stmt.tokens:
        if token.is_whitespace:
            continue
        if isinstance(token, Where):
            yield token, True
        else:
            yield token, False


def _get_token_keyword(token) -> str | None:
    """Get the keyword value of a token, if it's a simple keyword."""
    if hasattr(token, 'value'):
        val = token.value.upper().strip()
        if val:
            return val
    return None


# ---------------------------------------------------------------------------
# SELECT clause extraction
# ---------------------------------------------------------------------------


def _extract_select_columns(stmt) -> tuple[list[ColumnRef], bool]:
    """Extract column references from SELECT clause."""
    collected: list[ColumnRef] = []
    has_agg = False
    in_select = False

    for token in stmt.tokens:
        if token.is_whitespace:
            continue
        if in_select:
            kw = _get_token_keyword(token)
            if kw == 'FROM':
                break
            if isinstance(token, Where):
                break
            if isinstance(token, IdentifierList):
                for child in token.tokens:
                    _collect_identifier_columns(child, collected)
                    if _check_aggregation_in_token(child):
                        has_agg = True
            elif isinstance(token, (Identifier, Function, Case)):
                _collect_identifier_columns(token, collected)
                if _check_aggregation_in_token(token):
                    has_agg = True
            elif isinstance(token, sqlparse.sql.TokenList) and \
                    not isinstance(token, (Where, Comparison)):
                for t in token.tokens:
                    if isinstance(t, (Identifier, Function)):
                        _collect_identifier_columns(t, collected)
                        if _check_aggregation_in_token(t):
                            has_agg = True
        if token.ttype is DML and token.value.upper() == 'SELECT':
            in_select = True

    return collected, has_agg


# ---------------------------------------------------------------------------
# FROM / JOIN extraction
# ---------------------------------------------------------------------------


def _extract_from_tables(tokens: list) -> tuple[dict[str, str], dict[str, str], set[str]]:
    """Extract table references from FROM/JOIN clause tokens."""
    from_tables: dict[str, str] = {}
    alias_to_table: dict[str, str] = {}
    cte_refs: set[str] = set()

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.is_whitespace:
            i += 1
            continue

        if isinstance(token, (Where, Comparison, Function, Parenthesis)):
            i += 1
            continue

        val = _get_token_keyword(token)

        if val and (val.endswith('JOIN') or val in ('INNER', 'LEFT', 'RIGHT',
                   'FULL', 'CROSS', 'NATURAL', 'LATERAL')):
            i += 1
            # If the val was a qualifier like LEFT (not LEFT JOIN), look for JOIN
            if val in ('INNER', 'LEFT', 'RIGHT', 'FULL', 'CROSS', 'NATURAL', 'LATERAL'):
                while i < len(tokens) and tokens[i].is_whitespace:
                    i += 1
                kw2 = _get_token_keyword(tokens[i]) if i < len(tokens) else None
                if kw2 and kw2.endswith('JOIN'):
                    i += 1
            while i < len(tokens) and tokens[i].is_whitespace:
                i += 1
            if i < len(tokens) and isinstance(tokens[i], Identifier):
                _process_table_identifier(tokens[i], from_tables, alias_to_table, cte_refs)
                i += 1
            continue

        if val == 'ON':
            i += 1
            continue

        if isinstance(token, Identifier):
            _process_table_identifier(token, from_tables, alias_to_table, cte_refs)

        i += 1

    return from_tables, alias_to_table, cte_refs


def _process_table_identifier(token: Identifier, from_tables: dict[str, str],
                              alias_to_table: dict[str, str],
                              cte_refs: set[str]) -> None:
    name = token.get_real_name()
    if not name:
        name = token.value.strip()

    alias = _get_alias(token) or name

    for tbl_key in STAR_SCHEMA_TABLES:
        if tbl_key.lower() == name.lower():
            from_tables[alias] = tbl_key
            alias_to_table[alias] = tbl_key
            return

    alias_to_table[alias] = name
    cte_refs.add(name)


def _process_on_conditions(tokens: list, i: int,
                           join_columns: list[ColumnRef]) -> None:
    """Extract column refs from ON clause starting at i-th token."""
    j = i + 1
    condition_tokens = []
    while j < len(tokens):
        token = tokens[j]
        if token.is_whitespace:
            j += 1
            continue
        if isinstance(token, Where):
            break
        val = _get_token_keyword(token)
        if val and (val.endswith('JOIN') or val in ('WHERE', 'GROUP', 'ORDER', 'LIMIT', 'HAVING')):
            break
        condition_tokens.append(token)
        j += 1

    for t in condition_tokens:
        _collect_identifier_columns(t, join_columns)


# ---------------------------------------------------------------------------
# WHERE extraction
# ---------------------------------------------------------------------------


def _extract_where_columns(stmt) -> list[ColumnRef]:
    """Extract column references from WHERE clause."""
    cols: list[ColumnRef] = []
    for token in stmt.tokens:
        if isinstance(token, Where):
            _collect_identifier_columns(token, cols)
    return cols


# ---------------------------------------------------------------------------
# GROUP BY / ORDER BY extraction
# ---------------------------------------------------------------------------


_DIRECTIONAL = frozenset({'ASC', 'DESC', 'NULLS', 'FIRST', 'LAST'})
_CLAUSE_ENDS = frozenset({'ORDER', 'ORDER BY', 'LIMIT', 'HAVING'})


def _extract_group_by(stmt) -> list[str]:
    """Extract GROUP BY expressions directly from statement tokens."""
    exprs = []
    collecting = False
    for token in stmt.tokens:
        if token.is_whitespace:
            continue
        if isinstance(token, Where):
            if collecting:
                break
            continue
        kw = _get_token_keyword(token)
        if kw in ('GROUP BY', 'GROUP'):
            collecting = True
            continue
        if collecting:
            if kw in _CLAUSE_ENDS:
                break
            if isinstance(token, IdentifierList):
                for child in token.tokens:
                    if not child.is_whitespace and child.ttype is not Punctuation:
                        exprs.append(child.value.strip())
            elif isinstance(token, Identifier):
                exprs.append(token.value.strip())
            elif isinstance(token, (Function, Case, Comparison, Parenthesis)):
                exprs.append(token.value.strip())
            else:
                s = token.value.strip()
                if s and s.upper() not in _DIRECTIONAL:
                    exprs.append(s)
    return exprs


def _extract_order_by(stmt) -> list[str]:
    """Extract ORDER BY expressions directly from statement tokens."""
    exprs = []
    collecting = False
    for token in stmt.tokens:
        if token.is_whitespace:
            continue
        if isinstance(token, Where):
            if collecting:
                break
            continue
        kw = _get_token_keyword(token)
        if kw in ('ORDER BY', 'ORDER'):
            collecting = True
            continue
        if collecting:
            if kw in ('LIMIT', 'HAVING'):
                break
            if kw in _DIRECTIONAL:
                continue
            if isinstance(token, IdentifierList):
                for child in token.tokens:
                    if not child.is_whitespace and child.ttype is not Punctuation:
                        val = child.value.strip()
                        _strip_directional(val, exprs)
            elif isinstance(token, Identifier):
                val = token.value.strip()
                _strip_directional(val, exprs)
            elif isinstance(token, (Function, Case, Comparison, Parenthesis)):
                exprs.append(token.value.strip())
            else:
                s = token.value.strip()
                if s and s.upper() not in _DIRECTIONAL:
                    exprs.append(s)
    return exprs


def _strip_directional(val: str, exprs: list[str]) -> None:
    parts = val.rsplit(None, 1)
    if len(parts) == 2 and parts[1].upper() in _DIRECTIONAL:
        exprs.append(parts[0])
    else:
        exprs.append(val)


# ---------------------------------------------------------------------------
# From clause extraction (with Where boundary detection)
# ---------------------------------------------------------------------------


def _extract_from_clause_tokens(stmt) -> list:
    """Extract tokens from FROM through WHERE/GROUP/ORDER/LIMIT."""
    tokens = []
    in_from = False
    for token in stmt.tokens:
        if token.is_whitespace:
            if in_from:
                tokens.append(token)
            continue
        if isinstance(token, Where):
            if in_from:
                break
            continue
        kw = _get_token_keyword(token)
        if not in_from and kw == 'FROM':
            in_from = True
            continue
        if in_from:
            if kw and (kw in ('WHERE', 'GROUP', 'ORDER', 'LIMIT', 'HAVING',
                              'UNION', 'INTERSECT', 'EXCEPT')
                       or kw.endswith(' BY')):
                break
            tokens.append(token)
    return tokens


# ---------------------------------------------------------------------------
# SELECT output names extraction
# ---------------------------------------------------------------------------


def _get_select_output_names(stmt) -> list[str]:
    """Get the output column names of a SELECT statement.

    Uses sqlparse's alias detection to correctly map aliased expressions.
    """
    names: list[str] = []
    in_select = False
    for token in stmt.tokens:
        if token.is_whitespace:
            continue
        if token.ttype is DML and token.value.upper() == 'SELECT':
            in_select = True
            continue
        if in_select:
            kw = _get_token_keyword(token)
            if kw == 'FROM':
                break
            if isinstance(token, IdentifierList):
                for child in token.tokens:
                    if isinstance(child, Identifier):
                        alias = child.get_alias()
                        if alias:
                            names.append(alias)
                        else:
                            real = child.get_real_name()
                            names.append(real or child.value.strip())
            elif isinstance(token, Identifier):
                alias = token.get_alias()
                if alias:
                    names.append(alias)
                else:
                    real = token.get_real_name()
                    names.append(real or token.value.strip())
    return names


# ---------------------------------------------------------------------------
# Full statement processing
# ---------------------------------------------------------------------------


def _process_select_statement(stmt) -> QueryParts:
    """Parse a SELECT statement into its constituent parts."""
    parts = QueryParts()

    parts.select_columns, parts.has_aggregation = _extract_select_columns(stmt)
    parts.where_columns = _extract_where_columns(stmt)

    from_tokens = _extract_from_clause_tokens(stmt)
    parts.from_tables, parts.alias_to_table, parts.cte_references = \
        _extract_from_tables(from_tokens)

    for i, token in enumerate(from_tokens):
        if not token.is_whitespace and _get_token_keyword(token) == 'ON':
            _process_on_conditions(from_tokens, i, parts.join_columns)

    parts.group_by_exprs = _extract_group_by(stmt)
    parts.order_by_exprs = _extract_order_by(stmt)

    return parts


# ---------------------------------------------------------------------------
# Alias resolution for GROUP BY
# ---------------------------------------------------------------------------


def _resolve_group_by_alias(expr: str, select_cols: list[ColumnRef]) -> str:
    """Resolve a GROUP BY expression to the underlying column name."""
    if expr.isdigit():
        idx = int(expr) - 1
        if 0 <= idx < len(select_cols):
            col = select_cols[idx]
            if col.table_qualifier:
                return f"{col.table_qualifier}.{col.expression}"
            return col.expression
        return expr

    for col in select_cols:
        if col.alias and col.alias.lower() == expr.lower():
            if col.table_qualifier:
                return f"{col.table_qualifier}.{col.expression}"
            return col.expression

    return expr


# ---------------------------------------------------------------------------
# CTE parsing
# ---------------------------------------------------------------------------


def _split_ctes(stmt) -> tuple[dict[str, str], object | None]:
    """Extract CTE definitions and main query from a WITH statement.

    Uses string-based parsing for CTE boundaries.
    Returns (cte_name -> subquery_sql_string, main_query_statement).
    """
    cte_map: dict[str, str] = {}
    main_stmt = None

    has_with = False
    for token in stmt.tokens:
        if token.is_whitespace:
            continue
        if token.ttype is CTE or \
           (hasattr(token, 'value') and token.value.upper().strip() == 'WITH'):
            has_with = True
            break
        break

    if not has_with:
        main_parsed = sqlparse.parse(str(stmt))
        return cte_map, main_parsed[0] if main_parsed else stmt

    full_sql = str(stmt).strip()

    without_with = full_sql
    if full_sql.upper().startswith('WITH'):
        without_with = full_sql[4:].strip()

    depth = 0
    main_select_pos = -1
    i = 0
    while i < len(without_with):
        ch = without_with[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif depth == 0 and i + 6 <= len(without_with) and \
                without_with[i:i+6].upper() == 'SELECT':
            main_select_pos = i
            break
        i += 1

    if main_select_pos < 0:
        return cte_map, None

    cte_definition_str = without_with[:main_select_pos].strip()
    main_sql_str = without_with[main_select_pos:].strip()

    cte_entries = _split_cte_entries(cte_definition_str)

    for entry in cte_entries:
        entry = entry.strip()
        if not entry:
            continue

        paren_idx = entry.find('(')
        if paren_idx < 0:
            continue

        before_paren = entry[:paren_idx]
        as_idx = before_paren.upper().rfind(' AS ')
        if as_idx < 0:
            continue

        name_part = before_paren[:as_idx].strip()
        subquery_sql = entry[paren_idx:]

        cte_name = name_part
        col_paren = name_part.find('(')
        if col_paren >= 0:
            cte_name = name_part[:col_paren].strip()

        if subquery_sql.startswith('('):
            if _is_balanced_parens(subquery_sql):
                subquery_sql = subquery_sql[1:-1].strip()

        cte_map[cte_name] = subquery_sql

    if main_sql_str:
        main_parsed = sqlparse.parse(main_sql_str)
        if main_parsed:
            main_stmt = main_parsed[0]

    return cte_map, main_stmt


def _split_cte_entries(cte_str: str) -> list[str]:
    entries = []
    depth = 0
    current = []
    for ch in cte_str:
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            entries.append(''.join(current))
            current = []
        else:
            current.append(ch)
    if current:
        entries.append(''.join(current))
    return entries


def _is_balanced_parens(s: str) -> bool:
    if not s.startswith('('):
        return False
    depth = 0
    for i, ch in enumerate(s):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0 and i != len(s) - 1:
                return False
    return depth == 0


# ---------------------------------------------------------------------------
# Validation functions
# ---------------------------------------------------------------------------


def _validate_column_scope(
    col_refs: list[ColumnRef],
    from_tables: dict[str, str],
    alias_to_table: dict[str, str],
    cte_columns: dict[str, set[str]],
    errors: list[str],
    label: str = "",
) -> None:
    for col in col_refs:
        if col.is_wildcard or col.is_aggregated:
            continue

        col_name = col.expression
        qualifier = col.table_qualifier

        if qualifier:
            resolved = _resolve_table(qualifier, alias_to_table,
                                      set(cte_columns.keys()))
            if resolved is None:
                errors.append(
                    f"{label}Unknown table alias '{qualifier}' in column "
                    f"'{qualifier}.{col_name}'"
                )
                continue

            if resolved in cte_columns:
                if col_name not in cte_columns[resolved]:
                    errors.append(
                        f"{label}Column '{col_name}' not projected in "
                        f"CTE '{resolved}'"
                    )
                continue

            table_cols = _get_table_column_set(resolved)
            if col_name not in table_cols:
                errors.append(
                    f"{label}Column '{col_name}' not found in table "
                    f"'{resolved}'"
                )
        else:
            found_in_cte = False
            for cte_name, cte_cols in cte_columns.items():
                if col_name in cte_cols:
                    found_in_cte = True
                    break

            if found_in_cte:
                continue

            found_in_table = False
            ambiguous = False
            for alias, tbl_name in from_tables.items():
                tbl_cols = _get_table_column_set(tbl_name)
                if col_name in tbl_cols:
                    if found_in_table:
                        ambiguous = True
                    found_in_table = True

            if not found_in_table and col_name in UNIQUE_COLUMN_OWNER and from_tables:
                found_in_table = True

            if not found_in_table:
                errors.append(
                    f"{label}Column '{col_name}' not found in any "
                    f"known table or CTE"
                )
            elif ambiguous:
                errors.append(
                    f"{label}Column '{col_name}' is ambiguous "
                    f"(exists in multiple tables)"
                )


def _validate_aggregation_consistency(
    select_cols: list[ColumnRef],
    group_by_exprs: list[str],
    errors: list[str],
    label: str = "",
) -> None:
    has_group_by = len(group_by_exprs) > 0
    has_aggregation = any(c.is_aggregated for c in select_cols)

    if not has_group_by and has_aggregation:
        non_agg_cols = [c for c in select_cols if not c.is_aggregated]
        if non_agg_cols:
            names = ", ".join(c.expression for c in non_agg_cols)
            errors.append(
                f"{label}Non-aggregated columns {names} must appear "
                f"in GROUP BY clause"
            )
        return

    if has_group_by:
        for col in select_cols:
            if col.is_aggregated or col.is_wildcard:
                continue

            col_name = col.expression
            if col.table_qualifier:
                col_key = f"{col.table_qualifier}.{col_name}"
            else:
                col_key = col_name

            resolved_group_by = [
                _resolve_group_by_alias(gb, select_cols)
                for gb in group_by_exprs
            ]

            matched = False
            for gb_expr in resolved_group_by:
                if gb_expr.lower() == col_key.lower():
                    matched = True
                    break
                if '.' in gb_expr:
                    if gb_expr.split('.')[1].lower() == col_name.lower():
                        matched = True
                        break
                if '.' not in gb_expr and col.table_qualifier:
                    qualified_gb = f"{col.table_qualifier}.{gb_expr}"
                    if qualified_gb.lower() == col_key.lower():
                        matched = True
                        break

            if not matched:
                errors.append(
                    f"{label}Column '{col_key}' is not aggregated and "
                    f"not in GROUP BY"
                )


def _detect_grain(
    group_by_exprs: list[str],
    select_cols: list[ColumnRef],
) -> str | None:
    if not group_by_exprs:
        has_agg = any(c.is_aggregated for c in select_cols)
        if has_agg:
            non_agg = [c for c in select_cols if not c.is_aggregated]
            if not non_agg:
                return "scalar"
        return None

    resolved = [
        _resolve_group_by_alias(gb, select_cols)
        for gb in group_by_exprs
    ]

    bare_columns = []
    for expr in resolved:
        if '.' in expr:
            bare_columns.append(expr.split('.')[1])
        else:
            bare_columns.append(expr)

    grain_levels: set[str] = set()
    for col in bare_columns:
        matched = False
        for grain, signatures in GRAIN_SIGNATURES.items():
            if col.lower() in signatures:
                grain_levels.add(grain)
                matched = True
                break
        if not matched:
            alias_resolved = False
            for sc in select_cols:
                if sc.alias and sc.alias.lower() == col.lower():
                    sc_bare = sc.expression
                    for grain, signatures in GRAIN_SIGNATURES.items():
                        if sc_bare.lower() in signatures:
                            grain_levels.add(grain)
                            alias_resolved = True
                            break
                    break
            if not alias_resolved:
                grain_levels.add("unknown-level")

    if len(grain_levels) == 1:
        return next(iter(grain_levels))

    for composite_signature, composite_name in COMPOSITE_GRAINS.items():
        if grain_levels == composite_signature:
            return composite_name

    if len(grain_levels) > 1:
        return "mixed"

    return None


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------


class SQLSemanticContractValidator:
    """Semantic correctness layer for analytical SQL."""

    @classmethod
    def validate(cls, sql: str) -> ValidationResult:
        if not sql or not sql.strip():
            return ValidationResult(is_valid=False, errors=["Empty SQL statement"])

        parsed = sqlparse.parse(sql)
        if not parsed:
            return ValidationResult(is_valid=False, errors=["Unable to parse SQL"])

        stmt = parsed[0]
        errors: list[str] = []
        warnings: list[str] = []

        raw_sql = str(stmt).strip()
        if not raw_sql or raw_sql.startswith('--'):
            return ValidationResult(is_valid=False, errors=["No valid SQL found"])

        cte_map, main_stmt = _split_ctes(stmt)

        if main_stmt is None:
            return ValidationResult(is_valid=False, errors=["No main SELECT query found"])

        main_sql_str = str(main_stmt).strip().upper()
        if not main_sql_str.startswith('SELECT') and not main_sql_str.startswith('WITH'):
            return ValidationResult(is_valid=False, errors=["Main query is not a SELECT"])

        cte_projected_columns: dict[str, set[str]] = {}
        cls._validate_ctes(cte_map, cte_projected_columns, errors)

        if errors:
            return ValidationResult(is_valid=False, errors=errors)

        main_parts = _process_select_statement(main_stmt)

        full_alias_table: dict[str, str] = {}
        full_alias_table.update(DEFAULT_ALIASES)
        full_alias_table.update(main_parts.alias_to_table)

        full_from_tables: dict[str, str] = {}
        full_from_tables.update(main_parts.from_tables)

        _validate_column_scope(
            main_parts.select_columns, full_from_tables, full_alias_table,
            cte_projected_columns, errors, label="SELECT: ",
        )
        _validate_column_scope(
            main_parts.where_columns, full_from_tables, full_alias_table,
            cte_projected_columns, errors, label="WHERE: ",
        )
        _validate_column_scope(
            main_parts.join_columns, full_from_tables, full_alias_table,
            cte_projected_columns, errors, label="JOIN: ",
        )

        _validate_aggregation_consistency(
            main_parts.select_columns, main_parts.group_by_exprs, errors,
        )

        grain = _detect_grain(main_parts.group_by_exprs, main_parts.select_columns)
        if grain == "mixed":
            errors.append("Query has mixed or ambiguous analytical grain")

        for cte_ref in main_parts.cte_references:
            if cte_ref not in cte_map and cte_ref not in DEFAULT_ALIASES:
                is_known = any(
                    tbl.lower() == cte_ref.lower()
                    for tbl in STAR_SCHEMA_TABLES
                )
                if not is_known:
                    errors.append(
                        f"CTE or table '{cte_ref}' referenced but not defined"
                    )

        if errors:
            return ValidationResult(is_valid=False, grain=grain, errors=errors, warnings=warnings)

        return ValidationResult(is_valid=True, grain=grain, warnings=warnings)

    @classmethod
    def _validate_ctes(
        cls,
        cte_map: dict[str, str],
        cte_projected_columns: dict[str, set[str]],
        errors: list[str],
    ) -> None:
        if not cte_map:
            return

        deps: dict[str, set[str]] = {}
        cte_parts_cache: dict[str, QueryParts] = {}

        for cte_name, cte_sql in cte_map.items():
            sub_parsed = sqlparse.parse(cte_sql)
            if not sub_parsed:
                errors.append(f"CTE '{cte_name}' could not be parsed")
                continue
            cte_stmt = sub_parsed[0]
            parts = _process_select_statement(cte_stmt)
            cte_parts_cache[cte_name] = parts

            cte_deps = set()
            for ref in parts.cte_references:
                if ref in cte_map:
                    cte_deps.add(ref)
            deps[cte_name] = cte_deps

        sorted_ctes = cls._topological_sort(deps, errors)
        if errors:
            return

        for cte_name in sorted_ctes:
            cte_parts = cte_parts_cache[cte_name]
            cte_stmt = sqlparse.parse(cte_map[cte_name])[0]

            cte_alias_table: dict[str, str] = {}
            cte_alias_table.update(DEFAULT_ALIASES)
            cte_alias_table.update(cte_parts.alias_to_table)

            cte_from_tables: dict[str, str] = {}
            cte_from_tables.update(cte_parts.from_tables)

            _validate_column_scope(
                cte_parts.select_columns, cte_from_tables, cte_alias_table,
                cte_projected_columns, errors, label=f"CTE '{cte_name}' SELECT: ",
            )
            _validate_column_scope(
                cte_parts.where_columns, cte_from_tables, cte_alias_table,
                cte_projected_columns, errors, label=f"CTE '{cte_name}' WHERE: ",
            )
            _validate_column_scope(
                cte_parts.join_columns, cte_from_tables, cte_alias_table,
                cte_projected_columns, errors, label=f"CTE '{cte_name}' JOIN: ",
            )

            _validate_aggregation_consistency(
                cte_parts.select_columns, cte_parts.group_by_exprs, errors,
                label=f"CTE '{cte_name}': ",
            )

            output_names = _get_select_output_names(cte_stmt)
            cte_projected_columns[cte_name] = set(output_names)

    @classmethod
    def _topological_sort(
        cls, deps: dict[str, set[str]], errors: list[str]
    ) -> list[str]:
        visited: dict[str, str] = {}
        result: list[str] = []

        def dfs(node: str) -> bool:
            if node in visited:
                if visited[node] == 'visiting':
                    errors.append(f"Cyclic CTE dependency detected involving '{node}'")
                    return False
                return True
            visited[node] = 'visiting'
            for dep in deps.get(node, set()):
                if dep not in deps and dep not in DEFAULT_ALIASES:
                    continue
                if dep in deps:
                    if not dfs(dep):
                        return False
            visited[node] = 'visited'
            result.append(node)
            return True

        for cte in deps:
            if cte not in visited:
                if not dfs(cte):
                    return []

        return result
