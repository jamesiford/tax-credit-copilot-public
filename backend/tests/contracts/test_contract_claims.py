"""The claim-store contract: SQLite and the Warehouse behave the same. [DATA-2, DATA-3, DATA-4, DATA-7]

Each test runs once per adapter (see conftest). What is asserted is only what
BOTH promise: the Warehouse stores `effective_*` as DATE, so instants are
compared at date grain and same-day history is compared as a set with the live
row last.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from domain.claims import ClaimStatus, EngagementScope, ProgramClaim, ProgramEngagement, Provenance

DAY = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def _claim(client_id: int, *, year: int = 2024, status=ClaimStatus.ASSESSED, when=DAY, **kw) -> ProgramClaim:
    base = dict(
        client_id=client_id,
        program_code="GA_JTC",
        tax_year=year,
        status=status,
        provenance=Provenance.COMPUTED,
        identified_usd=Decimal("31500.25"),
        claimed_usd=Decimal("0"),
        certified_usd=Decimal("0"),
        average_headcount=61.5,
        base_average_headcount=40.0,
        threshold_jobs=2.0,
        effective_from=when,
    )
    base.update(kw)
    return ProgramClaim(**base)


def test_a_recorded_claim_round_trips(claim_repo, client_ids):
    client = client_ids()
    stored = _claim(
        client, identified_run_id="run-1", assumption_set_id="GDS-v8", rule_pack_version="2024.json",
        decided_by="analyst@example.com", decided_at=DAY, filed_on=date(2025, 4, 15),
        filing_reference="REF-1", entity_id=7,
    )
    claim_repo.record(stored)
    got = claim_repo.current(client, "ga_jtc", 2024)
    assert got is not None
    assert got.claim_id == stored.claim_id
    assert (got.client_id, got.program_code, got.tax_year) == (client, "GA_JTC", 2024)
    assert got.status is ClaimStatus.ASSESSED and got.provenance is Provenance.COMPUTED
    assert got.identified_usd == Decimal("31500.25") and isinstance(got.identified_usd, Decimal)
    assert got.claimed_usd == Decimal("0")
    assert got.average_headcount == pytest.approx(61.5)
    assert got.base_average_headcount == pytest.approx(40.0)
    assert got.threshold_jobs == pytest.approx(2.0)
    assert (got.identified_run_id, got.assumption_set_id, got.rule_pack_version) == ("run-1", "GDS-v8", "2024.json")
    assert got.filed_on == date(2025, 4, 15) and got.filing_reference == "REF-1"
    assert got.entity_id == 7
    assert got.decided_by == "analyst@example.com"
    assert abs(got.decided_at - DAY) < timedelta(seconds=1)
    assert got.effective_from.date() == DAY.date()
    assert got.effective_to is None and got.is_current


@pytest.mark.parametrize("flag", [True, False])
def test_is_base_year_round_trips(claim_repo, client_ids, flag):
    client = client_ids()
    claim_repo.record(_claim(client, is_base_year=flag, identified_usd=Decimal("0")))
    assert claim_repo.current(client, "GA_JTC", 2024).is_base_year is flag


def test_a_new_record_closes_the_live_one(claim_repo, client_ids):
    client = client_ids()
    first = _claim(client)
    second = _claim(client, status=ClaimStatus.PROPOSED, when=DAY + timedelta(days=2))
    claim_repo.record(first)
    claim_repo.record(second)

    assert claim_repo.current(client, "GA_JTC", 2024).claim_id == second.claim_id
    history = claim_repo.history(client, "GA_JTC", 2024)
    assert [c.claim_id for c in history] == [first.claim_id, second.claim_id]
    assert history[0].effective_to is not None
    assert history[0].effective_to.date() == second.effective_from.date()
    assert history[1].effective_to is None
    assert len(claim_repo.coverage(client)) == 1, "exactly one live row per cell"


def test_same_day_changes_keep_one_live_row(claim_repo, client_ids):
    client = client_ids()
    ids = []
    for status in (ClaimStatus.ASSESSED, ClaimStatus.PROPOSED, ClaimStatus.CLAIMED):
        c = _claim(client, status=status, when=DAY)
        ids.append(c.claim_id)
        claim_repo.record(c)
    history = claim_repo.history(client, "GA_JTC", 2024)
    assert {c.claim_id for c in history} == set(ids)
    assert history[-1].claim_id == ids[-1] and history[-1].is_current
    assert sum(1 for c in history if c.is_current) == 1
    assert claim_repo.current(client, "GA_JTC", 2024).status is ClaimStatus.CLAIMED


def test_coverage_narrows_by_program_and_year(claim_repo, client_ids):
    client = client_ids()
    for year in (2022, 2023, 2024):
        claim_repo.record(_claim(client, year=year))
    claim_repo.record(_claim(client, year=2024, program_code="SC_JTC"))

    assert [(c.program_code, c.tax_year) for c in claim_repo.coverage(client)] == [
        ("GA_JTC", 2022), ("GA_JTC", 2023), ("GA_JTC", 2024), ("SC_JTC", 2024),
    ]
    assert [c.tax_year for c in claim_repo.coverage(client, program_codes=["ga_jtc"], tax_years=[2023, 2024])] == [2023, 2024]
    assert claim_repo.coverage(client, program_codes=[]) == []
    assert claim_repo.coverage(client, tax_years=[]) == []


def test_a_declined_claim_keeps_its_reason(claim_repo, client_ids):
    client = client_ids()
    claim_repo.record(_claim(client, status=ClaimStatus.DECLINED, decline_reason="takes R&D credit instead"))
    got = claim_repo.current(client, "GA_JTC", 2024)
    assert got.status is ClaimStatus.DECLINED and got.decline_reason == "takes R&D credit instead"


def test_unknown_cell_is_none_and_empty(claim_repo, client_ids):
    client = client_ids()
    assert claim_repo.current(client, "GA_JTC", 2024) is None
    assert claim_repo.history(client, "GA_JTC", 2024) == []
    assert claim_repo.coverage(client) == []
    assert claim_repo.engagements(client) == []


# --------------------------------------------------------- tenant isolation


def test_one_clients_claims_are_never_returned_for_another(claim_repo, client_ids):
    a, b = client_ids(), client_ids()
    claim_repo.record(_claim(a, year=2024))
    claim_repo.record(_claim(a, year=2023))

    assert claim_repo.current(b, "GA_JTC", 2024) is None
    assert claim_repo.history(b, "GA_JTC", 2024) == []
    assert claim_repo.coverage(b) == []
    assert {c.client_id for c in claim_repo.coverage(a)} == {a}


def test_a_write_for_one_client_never_closes_anothers_row(claim_repo, client_ids):
    a, b = client_ids(), client_ids()
    claim_repo.record(_claim(a))
    claim_repo.record(_claim(b, status=ClaimStatus.PROPOSED, when=DAY + timedelta(days=1)))
    assert claim_repo.current(a, "GA_JTC", 2024).status is ClaimStatus.ASSESSED
    assert claim_repo.current(a, "GA_JTC", 2024).effective_to is None
    assert len(claim_repo.history(a, "GA_JTC", 2024)) == 1


def test_portfolio_coverage_spans_only_the_clients_asked_for(claim_repo, client_ids):
    a, b, c = client_ids(), client_ids(), client_ids()
    for client in (a, b, c):
        claim_repo.record(_claim(client))
    rows = claim_repo.portfolio_coverage(client_ids=[a, c])
    assert sorted({r.client_id for r in rows}) == [a, c]
    assert claim_repo.portfolio_coverage(client_ids=[]) == []
    assert {r.tax_year for r in claim_repo.portfolio_coverage(client_ids=[a, b], tax_years=[2024])} == {2024}


# --------------------------------------------------------------- engagement


def test_engagement_is_append_only_with_one_live_row_per_program(claim_repo, client_ids):
    a, b = client_ids(), client_ids()
    claim_repo.set_engagement(ProgramEngagement(a, "GA_JTC", EngagementScope.PROSPECTIVE, effective_from=DAY))
    claim_repo.set_engagement(ProgramEngagement(a, "GA_JTC", EngagementScope.IN_SCOPE, effective_from=DAY + timedelta(days=1), note="signed"))
    claim_repo.set_engagement(ProgramEngagement(a, "SC_JTC", EngagementScope.OUT_OF_SCOPE, effective_from=DAY))
    claim_repo.set_engagement(ProgramEngagement(b, "GA_JTC", EngagementScope.OUT_OF_SCOPE, effective_from=DAY))

    live = claim_repo.engagements(a)
    assert [(e.program_code, e.scope) for e in live] == [
        ("GA_JTC", EngagementScope.IN_SCOPE), ("SC_JTC", EngagementScope.OUT_OF_SCOPE),
    ]
    assert live[0].note == "signed" and live[0].effective_to is None
    assert [(e.client_id, e.scope) for e in claim_repo.engagements(b)] == [(b, EngagementScope.OUT_OF_SCOPE)]
