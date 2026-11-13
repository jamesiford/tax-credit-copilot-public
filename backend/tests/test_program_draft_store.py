"""The program draft store: the same behaviour on the SQLite adapter and the Warehouse adapter (over a fake connection). [F05.2]

The Warehouse adapter runs its real statements and the real `run_in_transaction` over a SQLite database behind a fake
connection; snapshot-isolation behaviour on a live Warehouse is a live check (LIVE-CHECK-REQUIRED).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domain.program_drafts import DraftConflict, DraftEvent, DraftStatus, ProgramDraft, documents_hash
from infrastructure.persistence.sqlite_program_drafts import _SCHEMA, SqliteProgramDraftRepository
from infrastructure.persistence.warehouse_program_drafts import WarehouseProgramDraftRepository
from tests import draft_world as dw
from tests.ddl_schema import warehouse_tables
from tests.test_run_batch_store import _FakeConnection

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(params=["sqlite", "warehouse"])
def repo(request):
    if request.param == "sqlite":
        r = SqliteProgramDraftRepository(":memory:")
        yield r
        r.close()
        return
    yield WarehouseProgramDraftRepository(_FakeConnection(_SCHEMA))


def _draft(draft_id="d1", code=dw.CODE, **kw) -> ProgramDraft:
    docs = dw.documents()
    base = dict(draft_id=draft_id, proposed_code=code, name="Fictional", jurisdiction_level="state", state=dw.STATE,
                status=DraftStatus.DRAFT, version=1, created_by="ann", created_at=NOW, updated_by="ann", updated_at=NOW,
                pack=docs["pack"], years=docs["years"])
    base.update(kw)
    return ProgramDraft(**base)


def _event(draft_id="d1", kind="created", **kw) -> DraftEvent:
    return DraftEvent(draft_id=draft_id, seq=0, event_type=kind, actor="ann", at=NOW, **kw)


def test_the_migration_and_the_sqlite_schema_name_the_same_columns():
    from infrastructure.persistence import program_draft_store as store

    tables = warehouse_tables()
    assert tables["tcc_ops.program_draft"] == list(store._COLUMNS)
    assert tables["tcc_ops.program_draft_event"] == list(store._EVENT_COLUMNS)
    assert tables["tcc_ops.program_draft_document"] == ["draft_id", "doc_key", "content_json", "content_sha256"]


def test_a_draft_round_trips_with_its_documents_and_a_stable_hash(repo):
    draft = _draft(validation={"errors": 0})
    repo.create(draft, _event())
    got = repo.get("d1")
    assert got.pack == draft.pack and got.years == draft.years and got.validation == {"errors": 0}
    assert got.content_sha256 == documents_hash(draft.pack, draft.years) and got.created_at == NOW


def test_a_save_needs_the_version_it_read_and_a_stale_one_changes_nothing(repo):
    repo.create(_draft(), _event())
    repo.save(_draft(version=2, name="Renamed"), 1, _event(kind="edited"))
    with pytest.raises(DraftConflict):
        repo.save(_draft(version=2, name="Lost"), 1, _event(kind="edited"))
    assert repo.get("d1").name == "Renamed" and [e.event_type for e in repo.events("d1")] == ["created", "edited"]


def test_events_are_appended_in_order_with_their_detail(repo):
    repo.create(_draft(), _event())
    repo.save(_draft(version=2), 1, _event(kind="validated", from_status="draft", to_status="draft", detail={"errors": 3}))
    first, second = repo.events("d1")
    assert (first.seq, second.seq) == (1, 2) and second.detail == {"errors": 3} and second.actor == "ann"


def test_a_document_over_the_column_limit_is_refused_not_truncated(repo):
    big = _draft(pack={**dw.pack(), "_note": "x" * 9000})
    with pytest.raises(ValueError, match="at most 8000"):
        repo.create(big, _event())
    assert repo.get("d1") is None


def test_live_for_code_ignores_withdrawn_and_exported_drafts(repo):
    repo.create(_draft(), _event())
    assert repo.live_for_code(dw.CODE).draft_id == "d1"
    repo.save(_draft(version=2, status=DraftStatus.WITHDRAWN), 1, _event(kind="withdrawn"))
    assert repo.live_for_code(dw.CODE) is None


def test_listing_pages_newest_first_and_filters_by_status(repo):
    for i in range(3):
        repo.create(_draft(f"d{i}", code=f"ZZ_CODE_{i}", updated_at=NOW.replace(minute=i)), _event(f"d{i}"))
    repo.save(_draft("d0", code="ZZ_CODE_0", version=2, status=DraftStatus.WITHDRAWN), 1, _event("d0", kind="withdrawn"))
    page, total = repo.list_drafts(limit=2)
    assert total == 3 and len(page) == 2
    only, count = repo.list_drafts(status="withdrawn")
    assert count == 1 and only[0].draft_id == "d0"
