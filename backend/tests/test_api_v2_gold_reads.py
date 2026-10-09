"""The v2 reads come from `tcc_gold`. Three states, never conflated.

The state tests run offline against a fake reader — the point is the contract,
not the connection. The live reads are opt-in and the restart proof is the gate,
not a test: no test can restart the process it runs in.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import pytest

import api.trend as trend_api


def _requires_fabric():
    if os.getenv("TCC_FABRIC_TESTS") != "1":
        pytest.skip("set TCC_FABRIC_TESTS=1 to run tests that reach live Fabric")


def test_the_fake_reader_answers_everything_the_real_one_does():
    """A stand-in that has fallen behind is worse than no stand-in.

    Adding `credit_columns` to `GoldReader` broke four tests here with an
    `AttributeError`, because the fake was hand-rolled and nothing tied the two
    surfaces together. The failure was loud that time. It would have been silent
    if the new method had only been reached on a branch these tests do not take,
    and the fake would then have been quietly asserting a contract the real
    reader no longer has.
    """
    from infrastructure.persistence.gold_reader import GoldReader

    real = {
        name for name in vars(GoldReader)
        if not name.startswith("_") and callable(getattr(GoldReader, name))
    }
    missing = sorted(name for name in real if not hasattr(_FakeReader, name))
    assert not missing, f"_FakeReader is behind GoldReader: {missing}"


def test_no_aggregate_is_aliased_to_a_bit_column_name():
    """`SUM(...) AS eligible` came back as `True`, and `int(True)` is 1.

    `_coerce` types a value by its COLUMN NAME, so an aggregate that borrows the
    name of a BIT column is silently collapsed to a boolean — 539 eligible
    employees reported as one, on a screen where nothing else looked wrong. The
    money aggregates have the mirror-image trap: a `SUM` aliased to a name
    `_MONEY_COLUMNS` does not carry falls through to float and loses exactness.

    Both are invisible in review because the SQL reads correctly. This asserts
    the alias, which is the part that has to be wrong for either to happen.
    """
    import re
    from pathlib import Path

    from infrastructure.persistence import gold_reader as gr

    module_text = Path(gr.__file__).read_text(encoding="utf-8")
    # Same line only. A negated class matches newlines, which pairs one
    # statement's aggregate with another's alias — and matches prose in a
    # docstring that happens to describe the trap.
    offenders = [
        f"{aggregate}(...) AS {alias}"
        for aggregate, alias in re.findall(
            r"(SUM|COUNT|MAX|MIN|AVG)[ \t]*\([^)\n]*\)[ \t]+AS[ \t]+(\w+)",
            module_text,
            re.IGNORECASE,
        )
        if alias in gr._BOOL_COLUMNS
    ]
    assert not offenders, (
        "these aggregates are aliased to BIT column names and will be coerced "
        f"to True/False: {offenders}"
    )


class _FakeReader:
    """Answers like `GoldReader` without a warehouse."""

    @contextmanager
    def scope(self):
        """The real one shares a connection; there is nothing to share here."""
        yield None

    def __init__(self, run=None, in_flight=None, items=None, total=None, unit=None):
        self._run = run
        self._in_flight = in_flight
        self._items = items or []
        self._total = total if total is not None else len(items or [])
        self._unit = unit
        self.unit_years_called = False

    def latest_run(self, client_id):
        return self._run

    def run_in_flight(self, client_id):
        return self._in_flight

    def unit_years(self, client_id, *, method, tax_year=None, program_code=None,
                   limit=25, offset=0):
        self.unit_years_called = True
        return self._items, self._total

    def unit_page(self, client_id, *, method, tax_year=None, program_code=None,
                  limit=25, offset=0):
        """Composed from the individual answers, so the two cannot disagree.

        The real one issues these as two batched round trips; what the endpoint
        must see is identical either way, including the early exit when there is
        no run.
        """
        if self._run is None:
            return {"run": None, "in_flight": self._in_flight, "items": [], "total": 0,
                    "months": [], "installments": [], "unit_totals": []}
        items, total = self.unit_years(
            client_id, method=method, tax_year=tax_year,
            program_code=program_code, limit=limit, offset=offset,
        )
        return {
            "run": self._run,
            "in_flight": self._in_flight,
            "items": items,
            "total": total,
            "months": self.month_summaries(),
            "installments": self.credit_columns(),
            "unit_totals": self.unit_totals(),
        }

    def unit(self, client_id, worksite_id, *, tax_year, method):
        return self._unit

    def unit_drill(self, client_id, worksite_id, *, tax_year, method, month=None):
        """Composed from the individual answers, as `unit_page` is."""
        if self._run is None:
            return {"run": None, "in_flight": self._in_flight, "unit": None,
                    "employees": [], "months": None, "near_threshold": []}
        return {
            "run": self._run,
            "in_flight": self._in_flight,
            "unit": self._unit,
            "employees": self.unit_employees(),
            "months": self.unit_months(),
            "near_threshold": self.unit_near_threshold(),
        }

    def unit_months(self, *a, **k):
        return None

    def month_summaries(self, *a, **k):
        return []

    def installments(self, *a, **k):
        return []

    def credit_columns(self, *a, **k):
        return []

    def unit_totals(self, *a, **k):
        return []

    def unit_employees(self, *a, **k):
        return []

    def unit_near_threshold(self, *a, **k):
        return []

    def eligibility_population(self, *a, **k):
        return {"run": None, "summary": None, "rows": [], "matching": 0}

    def proximity_candidates(self, *a, **k):
        return {"run": None, "rows": [], "counts": None}

    def cohort_periods(self, *a, **k):
        return {}

    def headcount_series(self, *a, **k):
        return {"run": None, "months": [], "month_ends": [], "annual_average": None}

    def client_year_series(self, *a, **k):
        return {"run": None, "years": []}

    def at_risk(self, *a, **k):
        return {"run": None, "rows": [], "counts": None}

    def employee_drill(self, *a, **k):
        return {"run": None, "verdicts": [], "segments": [], "periods": []}

    def onezero_matrix(self, *a, **k):
        return {"run": None, "summary": None, "matrix": [], "units": []}

    def employee(self, *a, **k):
        return []

    def employee_units(self, *a, **k):
        return []


_RUN = {
    "run_id": "R1",
    "run_completed_at": "2026-09-08T04:39:28",
    "run_started_at": "2026-09-08T03:23:00",
    "calculation_id": "abc",
    "code_commit": "d1beefe",
    "rule_pack_version": "rules/ga_jtc/2023.json",
    "step1_assumption_set_id": "GDS-STEP1-2026-08-25-v8",
    "onezero_assumption_set_id": "GDS-ONEZERO-2026-08-24-v7",
    "triggered_by": "someone@example.com",
    "tax_year": 2023,
    "program_code": "GA_JTC",
}


@pytest.fixture
def use_reader(monkeypatch):
    def _install(reader):
        from application import wiring

        monkeypatch.setattr(wiring, "get_gold_reader", lambda: reader)
        monkeypatch.setattr(trend_api, "get_gold_reader", lambda: reader, raising=False)
        return reader

    return _install


# --- state 2: the pipeline has not reached this client-year yet -------------


def test_a_client_with_no_run_says_so_rather_than_reporting_zero(client, use_reader):
    """The failure this guards is commercial, not technical.

    Rendering "not yet calculated" as $0 tells an operator the client has no
    payroll. That is a wrong statement to put in front of a customer, and it is
    indistinguishable from a real zero unless the API says which it is.
    """
    reader = use_reader(_FakeReader(run=None))

    response = client.get("/api/v2/clients/999999/units?year=2023&method=min_max")
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["calculation_state"] == "not_calculated"
    assert body["run"] is None
    assert body["items"] == []
    assert body["total"] == 0
    assert "Not yet calculated" in body["message"]
    # And it must not have gone looking for figures.
    assert reader.unit_years_called is False


# --- state 3: a run exists and the answer is genuinely zero ----------------


def test_a_run_that_found_nothing_is_a_real_answer_not_a_missing_one(client, use_reader):
    use_reader(_FakeReader(run=_RUN, items=[], total=0))

    response = client.get("/api/v2/clients/1001/units?year=2023&method=min_max")
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["calculation_state"] == "calculated"
    assert body["run"]["run_id"] == "R1"
    assert body["items"] == []
    assert body["total"] == 0
    assert body["message"] is None


def test_the_two_empty_states_are_distinguishable_from_the_payload_alone(client, use_reader):
    """`total: 0` is identical in both. `run` is the discriminator."""
    use_reader(_FakeReader(run=None))
    missing = client.get("/api/v2/clients/1/units?year=2023").json()

    use_reader(_FakeReader(run=_RUN, items=[], total=0))
    zero = client.get("/api/v2/clients/2/units?year=2023").json()

    assert missing["total"] == zero["total"] == 0
    assert missing["calculation_state"] != zero["calculation_state"]
    assert (missing["run"] is None) and (zero["run"] is not None)


# --- state 1: figures, with provenance and the whole credit layer ----------


def test_figures_carry_the_run_that_produced_them(client, use_reader):
    use_reader(_FakeReader(run=_RUN, items=[{"worksite_id": "GA_1", "tax_year": 2023}], total=1))

    body = client.get("/api/v2/clients/1001/units?year=2023").json()

    assert body["calculation_state"] == "calculated"
    assert body["run"]["produced_at"] == "2026-09-08T04:39:28"
    assert body["run"]["calculation_id"] == "abc"
    assert body["run"]["code_commit"] == "d1beefe"
    assert body["newer_run_in_flight"] is False


def test_a_newer_run_in_flight_is_surfaced(client, use_reader):
    use_reader(_FakeReader(
        run=_RUN,
        in_flight={"run_id": "R2", "run_started_at": "2026-09-08T05:00:00"},
        items=[], total=0,
    ))

    body = client.get("/api/v2/clients/1001/units?year=2023").json()

    assert body["newer_run_in_flight"] is True
    assert body["in_flight"]["run_id"] == "R2"


def test_the_reader_exposes_every_unit_year_master_column():
    """The audit found 13 of 34 reaching the API, and no `per_job_usd`.

    Without the rate, `annual_credit_usd` cannot be reconciled to
    `eligible_jobs` from the row that carries both — which is the reason the
    credit layer was put in Gold at all.
    """
    from infrastructure.persistence.gold_reader import UNIT_YEAR_MASTER_COLUMNS

    assert len(UNIT_YEAR_MASTER_COLUMNS) == 34
    for required in (
        "per_job_usd", "tranche_years", "annual_credit_usd", "eligible_jobs",
        "new_jobs_created", "high_water_mark", "net_new_vs_base",
        "months_reachable", "year_complete", "declined", "decline_reason",
        "threshold_source", "tier_source", "base_year_source",
        "base_year_overridden", "high_water_mark_overridden", "run_id",
        "is_current", "appended_at", "entity_fein", "backfilled",
    ):
        assert required in UNIT_YEAR_MASTER_COLUMNS, required


def test_money_is_a_string_and_headcount_is_a_number():
    """JSON has no decimal type. A money column serialised as a JSON number
    comes back as a binary approximation of a figure that was exact."""
    from decimal import Decimal

    from infrastructure.persistence.gold_reader import _value

    assert _value("per_job_usd", Decimal("3500.0000")) == "3500.0000"
    assert _value("annual_credit_usd", Decimal("12345678.91")) == "12345678.91"
    assert _value("average_headcount", Decimal("8.58")) == 8.58
    assert _value("qualified", 1) is True
    assert _value("qualified", 0) is False
    assert _value("per_job_usd", None) is None


# --- the live reads --------------------------------------------------------


def test_the_live_read_returns_the_certified_client_from_the_warehouse(client):
    """Opt-in. Proves the endpoint reads Gold, not the engine."""
    _requires_fabric()

    response = client.get("/api/v2/clients/1001/units?year=2023&method=min_max&limit=5")
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["calculation_state"] == "calculated"
    assert body["run"]["run_id"]
    assert body["total"] == 101, "1001 has 101 units in its live run"

    first = body["items"][0]
    assert first["program_code"] == "GA_JTC"
    assert first["tax_year"] == 2023
    assert first["is_current"] is True
    # The dollar is checkable from the row itself.
    assert first["per_job_usd"] is not None
    assert isinstance(first["per_job_usd"], str)
