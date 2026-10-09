"""A run is current for a CLIENT, not for a year.

Under the sweep model one run writes every year the payroll covers into
`tcc_gold`, but `run_manifest.tax_year` records only the year the run was
COMMANDED for. Narrowing the manifest lookup by that column made every other
year read as `not_calculated` while its rows sat in Gold -- 20 of 24
client-year combinations on the live data.

The existing fixtures could not catch it because they command and read the same
year. These deliberately differ.
"""
from __future__ import annotations

from infrastructure.persistence import gold_reader as gr


def _flat(statement):
    sql, values = statement
    return " ".join(sql.split()), values


# --- the manifest lookup ---------------------------------------------------


def test_the_live_run_is_resolved_without_a_year():
    """`tax_year` on the manifest is what was ASKED FOR, not what was produced."""
    sql, values = _flat(gr._stmt_latest_run(2001))

    assert "tax_year = ?" not in sql, (
        "a run commanded for TY2023 still produced TY2020..TY2025"
    )
    assert values == [2001]


def test_supersession_still_decides_which_run_is_live():
    """Dropping the year filter must not widen what counts as current."""
    sql, _ = _flat(gr._stmt_latest_run(2001))

    assert "run_status = 'success'" in sql
    assert "superseded_by_run_id IS NULL" in sql
    assert "run_completed_at IS NOT NULL" in sql
    assert "ORDER BY run_started_at DESC" in sql


def test_the_data_reads_are_still_year_scoped():
    """The year belongs on the tcc_gold read, which is where it now lives."""
    sql, values = _flat(gr._stmt_unit(2001, "GA_GA-010", 2021, "min_max"))

    assert "tax_year = ?" in sql
    assert "is_current = 1" in sql
    assert 2021 in values


# --- what the envelope tells a caller --------------------------------------


def _run(tax_year):
    return {
        "run_id": "r1", "run_completed_at": "2026-09-09T00:00:00",
        "run_started_at": "2026-09-09T00:00:00", "calculation_id": "c1",
        "code_commit": "abc", "rule_pack_version": "rules/ga_jtc/2023.json",
        "step1_assumption_set_id": "s1", "onezero_assumption_set_id": "o1",
        "triggered_by": "system", "tax_year": tax_year, "program_code": "GA_JTC",
    }


def test_a_year_the_run_did_not_name_is_still_calculated_when_gold_holds_it():
    """The bug, stated as the product behaviour it broke: click any unit on any
    year other than the one that client happened to be run for."""
    envelope = gr.run_envelope(_run(2023), None, has_rows=True)

    assert envelope["calculation_state"] == "calculated"
    assert envelope["run"]["tax_year"] == 2023, "provenance keeps what was asked for"


def test_a_year_with_no_gold_rows_is_not_calculated_even_though_a_run_exists():
    """The edge the fix must not trample. Candle Bottle holds TY2023 only, so
    TY2024 has no rows and must not claim to have been calculated. Null is not
    zero."""
    envelope = gr.run_envelope(_run(2023), None, has_rows=False)

    assert envelope["calculation_state"] == "not_calculated"


def test_no_run_at_all_is_still_not_calculated():
    envelope = gr.run_envelope(None, None, has_rows=False)

    assert envelope["calculation_state"] == "not_calculated"
    assert envelope["run"] is None


def test_rows_without_a_run_cannot_claim_to_be_calculated():
    """Gold rows with no current run behind them are orphans, not an answer."""
    envelope = gr.run_envelope(None, None, has_rows=True)

    assert envelope["calculation_state"] == "not_calculated"
