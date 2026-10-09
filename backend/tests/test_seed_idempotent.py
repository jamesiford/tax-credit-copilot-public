"""Re-running the operational-store seed writes nothing new. [DATA-8]

`azd up` runs the seed after every provision. The store is append-only, so a
seed that re-recorded what is already live would grow a duplicate decision in
every cell's history on every deploy.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from application import wiring
from domain.claims import ClaimStatus, ProgramClaim, Provenance
from infrastructure.persistence.sqlite_claims import SqliteClaimRepository


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

    assert seed_claims.main() == 0
    after_first = _row_count(repo)
    assert after_first[1] == len(seed_claims._ENGAGEMENTS)

    assert seed_claims.main() == 0
    assert _row_count(repo) == after_first, "a re-run must not append to the history"


def test_the_seed_skips_cells_nobody_has_assessed(repo):
    from data import seed_claims

    assert seed_claims.main() == 0
    claims, engagements = _row_count(repo)
    assert claims == 0
    assert engagements == len(seed_claims._ENGAGEMENTS)
