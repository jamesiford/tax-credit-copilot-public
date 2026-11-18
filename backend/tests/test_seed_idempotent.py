"""Re-running the operational-store seed writes nothing new, and it refuses where it must. [DATA-8, 04.4]

`azd up` runs the seed after every provision. The store is append-only, so a
seed that re-recorded what is already live would grow a duplicate decision in
every cell's history on every deploy.

The seed also invents claims, so it must never run against customer data, must
be asked for explicitly, and must only write to an account whose NAME is the one
the seed expects: an id that merely coincides with a seeded one is somebody
else's client.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from bootstrap import wiring
from domain.claims import ClaimStatus, ProgramClaim, Provenance
from infrastructure.persistence.sqlite_claims import SqliteClaimRepository


@pytest.fixture(autouse=True)
def seeding_allowed(monkeypatch):
    monkeypatch.setenv("DATA_CLASSIFICATION", "synthetic")
    monkeypatch.setenv("ALLOW_SEED", "1")


def seed_book():
    from data import seed_claims

    return [{"account_id": i, "name": f"{name} Holdings"} for i, name in seed_claims._EXPECTED_NAMES.items()]


@pytest.fixture
def repo(tmp_path):
    store = SqliteClaimRepository(tmp_path / "seed.db")
    wiring.set_claim_repository(store)
    yield store
    wiring.set_claim_repository(None)
    store.close()


def _row_count(store: SqliteClaimRepository) -> tuple[int, int]:
    conn = store._connect()
    claims = conn.execute("SELECT COUNT(*) FROM program_claim").fetchone()[0]
    engagements = conn.execute("SELECT COUNT(*) FROM program_engagement").fetchone()[0]
    return claims, engagements


def test_a_second_seed_run_writes_nothing(repo):
    from data import seed_claims

    for client_id, program, year, _claimed, _note in seed_claims._ASSERTIONS:
        repo.record(ProgramClaim(
            client_id=client_id, program_code=program, tax_year=year,
            status=ClaimStatus.ASSESSED, provenance=Provenance.COMPUTED,
            identified_usd=Decimal("100000"),
        ))

    assert seed_claims.main(book=seed_book) == 0
    after_first = _row_count(repo)
    assert after_first[1] == len(seed_claims._ENGAGEMENTS)

    assert seed_claims.main(book=seed_book) == 0
    assert _row_count(repo) == after_first, "a re-run must not append to the history"


def test_the_seed_skips_cells_nobody_has_assessed(repo):
    from data import seed_claims

    assert seed_claims.main(book=seed_book) == 0
    claims, engagements = _row_count(repo)
    assert claims == 0
    assert engagements == len(seed_claims._ENGAGEMENTS)


def test_the_seed_refuses_in_a_customer_classified_environment(repo, monkeypatch, capsys):
    from data import seed_claims

    monkeypatch.setenv("DATA_CLASSIFICATION", "customer")
    assert seed_claims.main(book=seed_book) == 2
    assert "seed refused" in capsys.readouterr().out
    assert _row_count(repo) == (0, 0)


def test_the_seed_refuses_without_the_explicit_flag(repo, monkeypatch):
    from data import seed_claims

    monkeypatch.delenv("ALLOW_SEED")
    assert seed_claims.main(book=seed_book) == 2
    assert _row_count(repo) == (0, 0)


def test_the_seed_refuses_when_classification_is_unset(repo, monkeypatch):
    from data import seed_claims

    monkeypatch.delenv("DATA_CLASSIFICATION")
    assert seed_claims.main(book=seed_book) == 2


def test_an_account_that_only_shares_an_id_is_left_alone(repo):
    """An id that coincides with a seeded one but carries another name is a real client, not ours."""
    from data import seed_claims

    stranger = [{"account_id": i, "name": "Somebody Else Ltd"} for i in seed_claims._EXPECTED_NAMES]
    assert seed_claims.main(book=lambda: stranger) == 0
    assert _row_count(repo) == (0, 0)
    assert repo.engagements(1001) == []


def test_the_seed_runs_only_for_the_accounts_the_source_holds(repo):
    from data import seed_claims

    only_one = [c for c in seed_book() if c["account_id"] == 2004]
    assert seed_claims.main(book=lambda: only_one) == 0
    assert _row_count(repo)[1] == 1
