"""The `ClaimRepository` contract. Every adapter must pass this suite. [ADR-007]

Written against the PORT, not against SQLite. The Warehouse adapter runs the
shared suite in `tests/contracts/` (opt-in, against a disposable client_id
range); this file keeps the deeper domain assertions on the local adapter.

Everything here is about a number that lands on a filed tax return, so the
assertions lean on the properties that would be expensive to get wrong: money
survives storage exactly, history is append-only, one cell has one live record,
and an exposure can never be quietly netted away.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from domain.claims import (
    ClaimError,
    ClaimStatus,
    EngagementScope,
    Outcome,
    ProgramClaim,
    ProgramEngagement,
    Provenance,
)
from infrastructure.persistence.sqlite_claims import SqliteClaimRepository


def _sqlite_repository(tmp_path):
    return SqliteClaimRepository(tmp_path / "operational.db")


@pytest.fixture(
    params=[
        pytest.param(_sqlite_repository, id="sqlite"),
    ]
)
def repo(request, tmp_path):
    """Every adapter behind the port, running one set of assertions."""
    repository = request.param(tmp_path)
    yield repository
    repository.close()


def _claim(**overrides) -> ProgramClaim:
    base = {
        "client_id": 1001,
        "program_code": "GA_JTC",
        "tax_year": 2023,
        "status": ClaimStatus.ASSESSED,
        "provenance": Provenance.COMPUTED,
        "identified_usd": Decimal("140000.00"),
        "decided_by": "analyst@example.com",
    }
    base.update(overrides)
    return ProgramClaim(**base)


# ------------------------------------------------------------- round tripping


def test_a_claim_survives_storage_unchanged(repo):
    stored = repo.record(_claim(
        claimed_usd=Decimal("87500.25"),
        certified_usd=Decimal("87500.25"),
        status=ClaimStatus.CLAIMED,
        filing_reference="IT-CA-2023-0042",
        assumption_set_id="GDS-STEP1-2026-08-25-v8",
        rule_pack_version="0.1.0+ty2023",
    ))
    read = repo.current(1001, "GA_JTC", 2023)

    assert read == stored
    assert read.filing_reference == "IT-CA-2023-0042"
    assert read.assumption_set_id == "GDS-STEP1-2026-08-25-v8"


def test_money_is_exact_after_a_round_trip(repo):
    """The reason money is TEXT and not REAL.

    0.1 + 0.2 != 0.3 in binary floating point. A store that used a float column
    would pass every test with round numbers and be wrong by cents on real
    figures — silently, and on a filed return.
    """
    repo.record(_claim(
        identified_usd=Decimal("0.10"),
        claimed_usd=Decimal("0.20"),
        certified_usd=Decimal("33072.07"),
    ))
    read = repo.current(1001, "GA_JTC", 2023)

    assert read.identified_usd == Decimal("0.10")
    assert read.claimed_usd == Decimal("0.20")
    assert read.certified_usd == Decimal("33072.07")
    assert read.identified_usd + read.claimed_usd == Decimal("0.30")
    assert isinstance(read.identified_usd, Decimal)


def test_program_code_is_normalised(repo):
    repo.record(_claim(program_code="ga_jtc"))
    assert repo.current(1001, "GA_JTC", 2023) is not None
    assert repo.current(1001, "ga_jtc", 2023) is not None


def test_an_unrecorded_cell_is_none_not_an_error(repo):
    assert repo.current(1001, "GA_JTC", 2023) is None
    assert repo.history(1001, "GA_JTC", 2023) == []


# ------------------------------------------------------------------- history


def test_recording_supersedes_rather_than_overwrites(repo):
    first = repo.record(_claim())
    second = repo.record(first.transition_to(
        ClaimStatus.PROPOSED, decided_by="lead@example.com",
    ))

    history = repo.history(1001, "GA_JTC", 2023)
    assert len(history) == 2, "the earlier belief must survive"
    assert [h.status for h in history] == [ClaimStatus.ASSESSED, ClaimStatus.PROPOSED]

    # Exactly one live record, and it is the latest.
    assert history[0].effective_to is not None
    assert history[1].effective_to is None
    assert repo.current(1001, "GA_JTC", 2023).claim_id == second.claim_id


def test_only_one_record_is_ever_live_for_a_cell(repo):
    """A second live row would double-count a claim in the coverage matrix."""
    claim = repo.record(_claim())
    for _ in range(4):
        claim = repo.record(claim.transition_to(
            ClaimStatus.ASSESSED, decided_by="analyst@example.com",
        ))

    live = [c for c in repo.history(1001, "GA_JTC", 2023) if c.is_current]
    assert len(live) == 1
    assert len(repo.coverage(1001)) == 1


def test_history_closes_at_the_moment_the_successor_opens(repo):
    """No gap and no overlap — a point in time resolves to exactly one record."""
    first = repo.record(_claim())
    later = datetime.now(timezone.utc) + timedelta(minutes=5)
    repo.record(first.transition_to(
        ClaimStatus.PROPOSED, decided_by="lead@example.com", at=later,
    ))

    history = repo.history(1001, "GA_JTC", 2023)
    assert history[0].effective_to == history[1].effective_from


# ------------------------------------------------------------------ coverage


def test_coverage_is_scoped_to_one_tenant(repo):
    """Tenant is a partition, not a filter. This is the leak that must not happen."""
    repo.record(_claim(client_id=1001, identified_usd=Decimal("140000")))
    repo.record(_claim(client_id=2001, identified_usd=Decimal("999999")))

    theirs = repo.coverage(1001)
    assert len(theirs) == 1
    assert theirs[0].client_id == 1001
    assert all(c.client_id == 1001 for c in theirs)
    assert "999999" not in str([c.to_dict() for c in theirs])


def test_coverage_narrows_by_program_and_year(repo):
    for year in (2021, 2022, 2023):
        repo.record(_claim(tax_year=year))
    repo.record(_claim(program_code="FED_WOTC", tax_year=2023))

    assert len(repo.coverage(1001)) == 4
    assert len(repo.coverage(1001, tax_years=[2023])) == 2
    assert len(repo.coverage(1001, program_codes=["GA_JTC"])) == 3
    assert len(repo.coverage(1001, program_codes=["GA_JTC"], tax_years=[2023])) == 1


def test_an_empty_filter_returns_nothing_not_everything(repo):
    """`[]` means "none of them". Treating it as "no filter" would leak the lot."""
    repo.record(_claim())
    assert repo.coverage(1001, program_codes=[]) == []
    assert repo.coverage(1001, tax_years=[]) == []
    assert repo.portfolio_coverage(client_ids=[]) == []


def test_portfolio_coverage_spans_clients(repo):
    repo.record(_claim(client_id=1001))
    repo.record(_claim(client_id=2001))
    repo.record(_claim(client_id=2002))

    assert len({c.client_id for c in repo.portfolio_coverage()}) == 3
    assert len(repo.portfolio_coverage(client_ids=[1001, 2001])) == 2


def test_superseded_records_leave_the_coverage_matrix(repo):
    first = repo.record(_claim())
    repo.record(first.transition_to(ClaimStatus.PROPOSED, decided_by="lead@example.com"))

    coverage = repo.coverage(1001)
    assert len(coverage) == 1
    assert coverage[0].status is ClaimStatus.PROPOSED


# ---------------------------------------------------------------- engagement


def test_engagement_scope_supersedes_too(repo):
    repo.set_engagement(ProgramEngagement(1001, "GA_JTC", EngagementScope.PROSPECTIVE))
    repo.set_engagement(ProgramEngagement(1001, "GA_JTC", EngagementScope.IN_SCOPE))

    live = repo.engagements(1001)
    assert len(live) == 1
    assert live[0].scope is EngagementScope.IN_SCOPE


def test_engagement_is_per_tenant(repo):
    repo.set_engagement(ProgramEngagement(1001, "GA_JTC", EngagementScope.IN_SCOPE))
    repo.set_engagement(ProgramEngagement(2001, "FED_WOTC", EngagementScope.OUT_OF_SCOPE))

    assert [e.program_code for e in repo.engagements(1001)] == ["GA_JTC"]
    assert [e.program_code for e in repo.engagements(2001)] == ["FED_WOTC"]


# -------------------------------------------------------- storage enforcement


def test_the_store_itself_rejects_a_reasonless_decline(repo):
    """Belt and braces.

    The domain refuses this already. The CHECK constraint means a row that
    reached the database by some future path still cannot be a decline nobody
    explained.
    """
    import sqlite3

    conn = repo._connect()
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO program_claim "
                "(claim_id, client_id, program_code, tax_year, status, provenance, "
                " identified_usd, claimed_usd, certified_usd, effective_from) "
                "VALUES ('x', 1001, 'GA_JTC', 2023, 'declined', 'computed', "
                "'0', '0', '0', '2026-01-01T00:00:00+00:00')"
            )


def test_a_repository_survives_reopening(tmp_path):
    """Durability, not just in-memory correctness."""
    path = tmp_path / "operational.db"
    first = SqliteClaimRepository(path)
    first.record(_claim(claimed_usd=Decimal("12345.67"), status=ClaimStatus.CLAIMED))
    first.close()

    second = SqliteClaimRepository(path)
    try:
        read = second.current(1001, "GA_JTC", 2023)
        assert read is not None
        assert read.claimed_usd == Decimal("12345.67")
    finally:
        second.close()
