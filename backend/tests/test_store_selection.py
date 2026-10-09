"""Adapter selection in the composition root. [ADR-002] [ADR-003]

The selection itself is worth a test because both failure modes are silent. A
typo in `CLAIM_STORE` that fell back to SQLite would write filing records to a
container filesystem that Container Apps discards on the next revision — the
app would look healthy and lose the data. And composition drifting back into a
router is how `application/` came to import `api/` in the first place.

Neither adapter is constructed against a live account here; constructing the
Warehouse adapter opens nothing, and a deployed process refuses a non-durable
store before it serves (`tests/test_deployment_config.py`).
"""
from __future__ import annotations

import pytest

from application import wiring
from infrastructure.persistence.sqlite_claims import SqliteClaimRepository
from infrastructure.persistence.sqlite_findings import SqliteFindingRepository


@pytest.fixture(autouse=True)
def _reset_adapters():
    wiring.set_claim_repository(None)
    wiring.set_finding_repository(None)
    yield
    wiring.set_claim_repository(None)
    wiring.set_finding_repository(None)


@pytest.mark.parametrize(
    "variable,getter,expected",
    [
        ("CLAIM_STORE", wiring.get_claim_repository, SqliteClaimRepository),
        ("FINDING_STORE", wiring.get_finding_repository, SqliteFindingRepository),
    ],
)
def test_sqlite_is_the_local_default(monkeypatch, variable, getter, expected):
    monkeypatch.delenv(variable, raising=False)
    assert isinstance(getter(), expected)


@pytest.mark.parametrize(
    "variable,getter",
    [
        ("CLAIM_STORE", wiring.get_claim_repository),
        ("FINDING_STORE", wiring.get_finding_repository),
    ],
)
def test_an_unknown_adapter_raises_rather_than_falling_back(monkeypatch, variable, getter):
    monkeypatch.setenv(variable, "postgres")

    with pytest.raises(ValueError, match="not a known adapter"):
        getter()


def test_both_stores_are_selected_independently(monkeypatch):
    """Claims on the Warehouse must not silently drag findings along, or vice versa."""
    from infrastructure.persistence.warehouse_findings import WarehouseFindingRepository

    monkeypatch.delenv("CLAIM_STORE", raising=False)
    monkeypatch.setenv("FINDING_STORE", "warehouse")

    assert isinstance(wiring.get_claim_repository(), SqliteClaimRepository)
    assert isinstance(wiring.get_finding_repository(), WarehouseFindingRepository)


@pytest.mark.parametrize("value", ["warehouse", "fabric", " Warehouse "])
def test_the_warehouse_is_selected_by_name_or_its_v1_alias(monkeypatch, value):
    """Constructing the adapter opens nothing, so this needs no Warehouse."""
    from infrastructure.persistence.warehouse_claims import WarehouseClaimRepository
    from infrastructure.persistence.warehouse_findings import WarehouseFindingRepository

    monkeypatch.setenv("CLAIM_STORE", value)
    monkeypatch.setenv("FINDING_STORE", value)
    assert isinstance(wiring.get_claim_repository(), WarehouseClaimRepository)
    assert isinstance(wiring.get_finding_repository(), WarehouseFindingRepository)


def test_memory_is_an_in_process_sqlite_store(monkeypatch):
    monkeypatch.setenv("CLAIM_STORE", "memory")
    monkeypatch.setenv("FINDING_STORE", "memory")
    claims, findings = wiring.get_claim_repository(), wiring.get_finding_repository()
    assert isinstance(claims, SqliteClaimRepository) and str(claims.path) == ":memory:"
    assert isinstance(findings, SqliteFindingRepository) and str(findings.path) == ":memory:"


@pytest.mark.parametrize("value", ["warehouse", "fabric"])
def test_run_manifests_and_overrides_accept_the_warehouse_name_and_alias(monkeypatch, value):
    from infrastructure.persistence.fabric_warehouse import (
        FabricManualOverrideRepository,
        FabricRunManifestRepository,
    )

    monkeypatch.setenv("RUN_MANIFEST_STORE", value)
    monkeypatch.delenv("OVERRIDE_STORE", raising=False)
    wiring.set_run_manifest_repository(None)
    wiring.set_override_repository(None)
    try:
        assert isinstance(wiring.get_run_manifest_repository(), FabricRunManifestRepository)
        assert isinstance(wiring.get_override_repository(), FabricManualOverrideRepository)
    finally:
        wiring.set_run_manifest_repository(None)
        wiring.set_override_repository(None)
