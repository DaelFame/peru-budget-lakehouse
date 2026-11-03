"""Acceptance tests for the demo sampling contract.

The demo must be a whole-entity sample: a fact row is never separated from the
rest of its record. Splitting records is what produced execution rates above
100% in the previous row-level sample.
"""

import pandas as pd
import pytest

from scripts.build_demo_dataset import (
    ENTITY_KEYS,
    check_gates,
    execution_rates,
    region_pim_shares,
    select_entities,
)


def make_sizes(sizes: list[int]) -> pd.DataFrame:
    rows = []
    for index, n_facts in enumerate(sizes):
        row = {key: index + 1 for key in ENTITY_KEYS}
        row["n_facts"] = n_facts
        rows.append(row)
    return pd.DataFrame(rows, columns=ENTITY_KEYS + ["n_facts"])


def make_facts(records: list[tuple[int, str, float]]) -> pd.DataFrame:
    """records: (year, fase, monto) for a single geography."""
    return pd.DataFrame(
        [
            {
                **{key: 1 for key in ENTITY_KEYS},
                "anio": year,
                "fase": fase,
                "monto": monto,
            }
            for year, fase, monto in records
        ],
        columns=ENTITY_KEYS + ["anio", "fase", "monto"],
    )


def make_geography(names_and_keys: list[tuple[int, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"sk_geografia_id": key, "departamento_ejecutora_nombre": name} for key, name in names_and_keys]
    )


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------
def test_select_entities_never_splits_a_record():
    sizes = make_sizes([4, 3, 2, 1])

    chosen = select_entities(sizes, target_rows=6)

    # 4 + 2 fills 6 exactly; the 3-fact entity does not fit and is skipped whole.
    assert chosen["n_facts"].sum() == 6
    assert sorted(chosen["n_facts"].tolist()) == [2, 4]


def test_select_entities_fills_remainder_with_small_records():
    sizes = make_sizes([5, 5, 1, 1])

    chosen = select_entities(sizes, target_rows=12)

    assert chosen["n_facts"].sum() == 12
    assert len(chosen) == 4


def test_select_entities_respects_target_ceiling():
    sizes = make_sizes([7, 7, 7])

    chosen = select_entities(sizes, target_rows=10)

    assert chosen["n_facts"].sum() == 7


def test_select_entities_is_deterministic():
    sizes = make_sizes([3, 1, 4, 1, 5])

    first = select_entities(sizes, target_rows=9)
    second = select_entities(sizes, target_rows=9)

    assert first.equals(second)


# ---------------------------------------------------------------------------
# Execution-rate gate
# ---------------------------------------------------------------------------
def test_execution_rate_reports_global_and_per_year():
    facts = make_facts([(2024, "pim", 100.0), (2024, "devengado", 80.0)])

    rates = execution_rates(facts)

    assert rates["global_execution_rate_pct"] == 80.0
    assert rates["by_year"][0]["execution_rate_pct"] == 80.0


def test_gate_rejects_execution_rate_above_100():
    # devengado survives, its PIM sibling does not: the row split artefact.
    facts = make_facts([(2024, "pim", 50.0), (2024, "devengado", 120.0)])
    geography = make_geography([(1, "lima")])

    failures, _ = check_gates(
        facts, geography, target_rows=len(facts), max_region_share=100.0, row_tolerance=0.001
    )

    assert any("outside [0, 100]" in failure for failure in failures)


def test_gate_accepts_consistent_sample():
    facts = make_facts([(2024, "pim", 100.0), (2024, "devengado", 80.0)])
    geography = make_geography([(1, "lima")])

    failures, _ = check_gates(
        facts, geography, target_rows=len(facts), max_region_share=100.0, row_tolerance=0.001
    )

    assert failures == []


def test_gate_flags_null_amounts():
    facts = make_facts([(2024, "pim", 100.0), (2024, "devengado", 80.0)])
    facts.loc[0, "monto"] = None
    geography = make_geography([(1, "lima")])

    failures, _ = check_gates(
        facts, geography, target_rows=len(facts), max_region_share=100.0, row_tolerance=0.001
    )

    assert any("null values" in failure for failure in failures)


# ---------------------------------------------------------------------------
# Geographic concentration
# ---------------------------------------------------------------------------
def test_region_share_gate_rejects_concentration():
    facts = make_facts([(2024, "pim", 100.0), (2024, "devengado", 80.0)])
    facts.loc[1, "sk_geografia_id"] = 2
    geography = make_geography([(1, "lima"), (2, "cusco")])

    failures, diagnostics = check_gates(
        facts, geography, target_rows=len(facts), max_region_share=50.0, row_tolerance=0.001
    )

    assert diagnostics["top_region_pim_share"][0]["department"] == "lima"
    assert any("holds 100.0% of PIM" in failure for failure in failures)


def test_region_shares_exclude_rows_without_geography():
    facts = make_facts([(2024, "pim", 100.0)])
    facts.loc[0, "sk_geografia_id"] = 99
    geography = make_geography([(1, "lima")])

    shares = region_pim_shares(facts, geography)

    assert shares == []


def test_row_target_gate_rejects_off_target_count():
    facts = make_facts([(2024, "pim", 100.0)])
    geography = make_geography([(1, "lima")])

    failures, _ = check_gates(
        facts, geography, target_rows=1000, max_region_share=100.0, row_tolerance=0.001
    )

    assert any("against a target of" in failure for failure in failures)


@pytest.mark.parametrize("rate", [0.0, 100.0])
def test_execution_rate_bounds_are_inclusive(rate):
    facts = make_facts([(2024, "pim", 100.0), (2024, "devengado", rate)])
    geography = make_geography([(1, "lima")])

    failures, _ = check_gates(
        facts, geography, target_rows=len(facts), max_region_share=100.0, row_tolerance=0.001
    )

    assert failures == []
