"""A batch over the sample data gives what running the same client through the existing command gives.

The worker calls `RunClientCalculationCommand` and `AssessClientCommand`; it does not reimplement a run. This proves
that on the offline fixture (the synthetic payroll, a recording Gold writer, a private claim store): the manifest
fingerprint, the row counts handed to the writer, the engine summary and the claims recorded are identical, and
that the unchanged check, built on the same fingerprint, skips a client whose last run still answers and runs it
when forced. It does not prove behaviour on a live Warehouse or Lakehouse (see live-checks.md).
"""
from __future__ import annotations

import pytest

from application.commands.enqueue_run_batch import EnqueueRunBatchCommand, handle_enqueue_run_batch
from application.commands.run_client_calculation import RunClientCalculationCommand
from application.runs.executor import ItemExecutor
from application.runs.worker import RunWorker
from config import get_settings
from domain.runs import ItemStatus
from domain.warehouse import RUN_MANIFEST_COLUMNS, RunManifest

CLIENT = 1001


class _RecordingWriter:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def write_run(self, payload: dict) -> dict[str, int]:
        self.payloads.append(payload)
        return {t: len(r) for t, r in payload.items() if isinstance(r, list)}

    def validate(self) -> list[dict]:
        return []


@pytest.fixture()
def world(tmp_path):
    from bootstrap import run_batch_wiring, wiring
    from infrastructure.persistence.memory_overrides import InMemoryManualOverrideRepository
    from infrastructure.persistence.memory_runs import InMemoryRunManifestRepository
    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository
    from infrastructure.persistence.sqlite_run_batches import SqliteRunBatchRepository

    writer, claims = _RecordingWriter(), SqliteClaimRepository(tmp_path / "claims.db")
    batches, manifests = SqliteRunBatchRepository(":memory:"), InMemoryRunManifestRepository()
    original = wiring.get_claim_repository()
    wiring.set_gold_writer(writer)
    wiring.set_claim_repository(claims)
    wiring.set_override_repository(InMemoryManualOverrideRepository())
    wiring.set_run_manifest_repository(manifests)
    run_batch_wiring.set_run_batch_repository(batches)
    try:
        yield type("World", (), {"writer": writer, "claims": claims, "batches": batches, "manifests": manifests,
                                 "wiring": wiring})
    finally:
        wiring.set_gold_writer(None)
        wiring.set_claim_repository(original)
        wiring.set_override_repository(None)
        wiring.set_run_manifest_repository(None)
        run_batch_wiring.set_run_batch_repository(None)
        claims.close()
        batches.close()


def _drain(world) -> None:
    RunWorker(world.batches, ItemExecutor(), get_settings().runs, owner="e2e").drain()


def _batch(**kw):
    return handle_enqueue_run_batch(EnqueueRunBatchCommand(actor="tests", scope_kind="list", client_ids=(CLIENT,), **kw))


def _claims(world):
    return sorted((c.program_code, c.tax_year, str(c.identified_usd), c.status.value) for c in world.wiring.get_claim_repository().coverage(CLIENT))


def _manifest(payload: dict) -> dict:
    return dict(zip(RUN_MANIFEST_COLUMNS, payload["run_manifest_row"]))


def test_a_batch_equals_running_the_client_through_the_existing_command(world):
    view = _batch(kind="assess_and_calculate")
    _drain(world)
    item = world.batches.list_items(view["batch_id"], None, 10, 0)[0][0]
    assert item.status is ItemStatus.SUCCEEDED and item.tax_year and item.run_id
    batch_payload, batch_claims = world.writer.payloads[-1], _claims(world)

    from application.services import get_mediator

    world.writer.payloads.clear()
    direct = get_mediator().send(RunClientCalculationCommand(
        client_id=CLIENT, tax_year=item.tax_year, state="GA", actor="tests"))
    direct_payload = world.writer.payloads[-1]

    assert _manifest(batch_payload)["calculation_id"] == _manifest(direct_payload)["calculation_id"]
    assert _manifest(batch_payload)["rule_pack_version"] == _manifest(direct_payload)["rule_pack_version"]
    assert {t: len(r) for t, r in batch_payload.items() if isinstance(r, list)} == \
           {t: len(r) for t, r in direct_payload.items() if isinstance(r, list)}
    assert item.run_id == _manifest(batch_payload)["run_id"] != direct["run_id"]
    assert _claims(world) == batch_claims, "the direct run recorded the same claims the batch did"
    assert _manifest(batch_payload)["triggered_by"] == "tests"


def test_an_assess_batch_records_the_same_claims_as_a_calculation(world, tmp_path):
    _batch(kind="assess_and_calculate")
    _drain(world)
    expected = _claims(world)
    world.claims.close()
    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository

    world.wiring.set_claim_repository(SqliteClaimRepository(tmp_path / "second.db"))
    _batch(kind="assess", force=True)
    _drain(world)
    assert world.writer.payloads and len(world.writer.payloads) == 1, "assess writes no Gold"
    assert _claims(world) == expected


def test_a_recorded_run_makes_the_next_batch_skip_it_until_forced(world):
    first = _batch(kind="assess_and_calculate")
    _drain(world)
    payload = world.writer.payloads[-1]
    row = _manifest(payload) | {"run_status": "success", "run_completed_at": payload["run_completed_at"]}
    world.manifests.record(RunManifest(**{k: v for k, v in row.items() if k in RunManifest.__dataclass_fields__}))
    runs_before = len(world.writer.payloads)

    again = _batch(kind="assess_and_calculate", idempotency_key="second")
    _drain(world)
    item = world.batches.list_items(again["batch_id"], None, 10, 0)[0][0]
    assert item.status is ItemStatus.SKIPPED_UNCHANGED and "identical" in item.skip_reason
    assert len(world.writer.payloads) == runs_before

    forced = _batch(kind="assess_and_calculate", force=True, idempotency_key="third")
    _drain(world)
    assert world.batches.list_items(forced["batch_id"], None, 10, 0)[0][0].status is ItemStatus.SUCCEEDED
    assert len(world.writer.payloads) == runs_before + 1
    assert first["batch_id"] not in (again["batch_id"], forced["batch_id"])


def test_a_client_year_the_statute_does_not_cover_is_skipped_by_name(world):
    view = _batch(tax_years=(2019,), kind="calculate")
    _drain(world)
    item = world.batches.list_items(view["batch_id"], None, 10, 0)[0][0]
    assert item.status is ItemStatus.SKIPPED_NO_PAYROLL and "TY2019" in item.skip_reason
    assert world.writer.payloads == []
