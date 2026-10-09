"""The write path, driven end to end against a recording writer.

`run_client_calculation` had no offline test at all. The consequence was a
`NameError` on a list that was declared in the replay helper and used in the
handler — code that every read path depends on, caught only when a backfill
against live Fabric fell over ten minutes in.

These do not assert figures; the parity gate owns those. They assert that the
command RUNS, and that the rows it hands the writer cover every year and every
method the grid will later read back. The bug this file exists to prevent is
"Gold holds one year while the screen offers six".
"""
from __future__ import annotations

import pytest

from application.commands.run_client_calculation import RunClientCalculationCommand

CLIENT = 1001
#: The CSV fixture carries 2024-2026. TY2023 is the LIVE reference client's
#: year and resolves only against the lakehouse.
YEAR = 2025
_METHODS = {"min_max", "pay_period"}

#: Every projection the handler must hand the writer.
_EXPECTED_TABLES = {
    "employee_period_fact", "employee_eligibility", "onezero_matrix",
    "unit_month_summary", "run_method_summary", "unit_year_master",
    "unit_credit_installment",
}


class _RecordingWriter:
    """Keeps the payload instead of writing it."""

    def __init__(self) -> None:
        self.payload: dict | None = None

    def write_run(self, payload: dict) -> dict[str, int]:
        self.payload = payload
        return {
            table: len(rows)
            for table, rows in payload.items()
            if isinstance(rows, list)
        }

    def validate(self) -> list[dict]:
        """The handler runs the writer's own post-write checks. Nothing was
        written here, so there is nothing to violate."""
        return []


@pytest.fixture()
def written(monkeypatch, tmp_path):
    """Run the command over the CSV fixture and return what it produced."""
    from application import wiring
    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository

    # The command does not only write Gold — it dispatches AssessClientCommand,
    # which records a CLAIM. Stubbing the writer alone left that going to the
    # real store, so every run of this file put `decided_by=tests` rows for
    # account 1001 at TY2024 and TY2025 into the operational database, where
    # the portfolio page read them back as a client's actual credit position.
    writer = _RecordingWriter()
    claims = SqliteClaimRepository(tmp_path / "claims.db")
    original = wiring.get_claim_repository()
    wiring.set_gold_writer(writer)
    wiring.set_claim_repository(claims)
    # The replay also reads saved base years (WI-21). Left to the environment,
    # that read went to the live warehouse whenever an earlier test had loaded
    # `.env` — and failed the whole class on a login, depending on test order.
    from infrastructure.persistence.memory_overrides import InMemoryManualOverrideRepository

    wiring.set_override_repository(InMemoryManualOverrideRepository())
    try:
        wiring.get_mediator().send(RunClientCalculationCommand(
            client_id=CLIENT, tax_year=YEAR, state="GA", actor="tests",
        ))
    finally:
        wiring.set_gold_writer(None)
        wiring.set_claim_repository(original)
        wiring.set_override_repository(None)
        claims.close()
    assert writer.payload is not None
    return writer.payload


def _years_and_methods(rows: list[tuple]) -> set[tuple[int, str]]:
    """`(tax_year, method)` sits at index 1 and 2 on every method-keyed row."""
    return {(row[1], row[2]) for row in rows}


class TestTheCommandRuns:
    def test_it_completes_and_hands_the_writer_every_table(self, written):
        assert _EXPECTED_TABLES <= set(written)

    def test_each_table_carries_rows(self, written):
        empty = [t for t in _EXPECTED_TABLES if not written[t]]
        assert not empty, f"wrote nothing to {empty}"

    def test_the_manifest_names_the_run(self, written):
        assert written["run_id"]
        assert written["run_manifest_row"]


class TestTheEmployeeGrainCoversEveryYear:
    """The gap that forced the read path to re-run the engine.

    `unit_year_master` held six years while `employee_eligibility` held one, so
    "who qualifies" could only be answered for whichever year the run was asked
    for — and answered it by replaying the engine for the rest.
    """

    def test_eligibility_covers_the_same_years_as_the_unit_series(self, written):
        unit_years = {row[5] for row in written["unit_year_master"]}
        eligibility_years = {row[1] for row in written["employee_eligibility"]}
        assert unit_years <= eligibility_years

    def test_the_matrix_covers_the_same_years(self, written):
        unit_years = {row[5] for row in written["unit_year_master"]}
        matrix_years = {row[1] for row in written["onezero_matrix"]}
        assert unit_years <= matrix_years

    def test_period_fact_covers_the_same_years(self, written):
        """Without it the near-threshold cohort is empty in every other year:
        it is what places an employee at a worksite."""
        unit_years = {row[5] for row in written["unit_year_master"]}
        period_years = {row[1] for row in written["employee_period_fact"]}
        assert unit_years <= period_years

    def test_both_methods_are_written_for_every_year(self, written):
        pairs = _years_and_methods(written["employee_eligibility"])
        years = {year for year, _ in pairs}
        for year in years:
            assert {(year, method) for method in _METHODS} <= pairs


class TestTheRunSummary:
    """One row per client-year-method, holding what only the run knew."""

    def test_one_row_per_year_and_method(self, written):
        rows = written["run_method_summary"]
        pairs = _years_and_methods(rows)
        assert len(rows) == len(pairs), "a duplicate (year, method) summary row"

    def test_it_covers_every_year_the_eligibility_table_does(self, written):
        assert (
            _years_and_methods(written["employee_eligibility"])
            == _years_and_methods(written["run_method_summary"])
        )

    def test_it_carries_the_twelve_measuring_dates(self, written):
        import json

        for row in written["run_method_summary"]:
            months = json.loads(row[-2])
            assert len(months) == 12, "the screen renders twelve month columns"

    def test_contested_months_is_a_count_not_a_flag(self, written):
        """The matrix is deduped before it is written, so this is the only
        place a contest survives the run."""
        for row in written["run_method_summary"]:
            assert isinstance(row[10], int)
            assert row[10] >= 0

    def test_the_requested_year_is_not_written_twice(self, written):
        """The handler computes the asked-for year directly and the replay
        computes it again; only one of them may reach the writer.

        The natural key differs by table. `onezero_matrix` is one row per
        employee per UNIT SEGMENT — the same person at two worksites is two
        legitimate rows — so employee id alone would read a correct fan-out as
        a duplicate.
        """
        keys = {
            "employee_eligibility": lambda row: row[4],
            "onezero_matrix": lambda row: (row[4], row[6], row[7]),
            "run_method_summary": lambda row: (row[1], row[2]),
        }
        for table, key in keys.items():
            requested = [
                row for row in written[table]
                if row[1] == YEAR and row[2] == "min_max"
            ]
            assert len(requested) == len({key(row) for row in requested}), (
                f"{table} duplicated the requested year"
            )
