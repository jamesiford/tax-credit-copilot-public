"""Shared contract fixtures: every operational-store adapter, one suite. [DATA-2]

SQLite runs always. The Warehouse runs only with `TCC_FABRIC_TESTS=1`, against
the Warehouse named by WAREHOUSE_SERVER / WAREHOUSE_DATABASE, with a client_id
range unique to this run that is deleted afterwards — so a live run never
touches a real client's rows and never leaves its own behind.
"""
from __future__ import annotations

import os
import random
import time

import pytest

LIVE = os.getenv("TCC_FABRIC_TESTS") == "1"

#: Far above any real AccountId. Each run takes its own block of 1,000.
_BASE = 900_000_000


def _run_block() -> int:
    return _BASE + (int(time.time()) % 50_000) * 1_000 + random.randint(0, 9) * 100


class ClientIds:
    """Hands out distinct client_ids and remembers them for cleanup."""

    def __init__(self, start: int) -> None:
        self._next = start
        self.issued: list[int] = []

    def __call__(self) -> int:
        self._next += 1
        self.issued.append(self._next)
        return self._next


@pytest.fixture
def client_ids(request) -> ClientIds:
    ids = ClientIds(_run_block() if LIVE else 1000)
    request.node._issued_client_ids = ids
    return ids


def _purge_warehouse(tables: tuple[str, ...], ids: list[int]) -> None:
    from infrastructure.persistence.fabric_warehouse import OPS_SCHEMA, FabricWarehouseConnection
    from infrastructure.persistence.tenant_sql import TenantScopedQuery, run_in_transaction

    connection = FabricWarehouseConnection().open()
    try:
        for client_id in ids:
            scoped = TenantScopedQuery(client_id)

            def work(cursor, scoped=scoped):
                for table in tables:
                    scoped.execute(cursor, f"DELETE FROM {OPS_SCHEMA}.{table} WHERE " + "{tenant}")

            run_in_transaction(connection, work)
    finally:
        connection.close()


_CLAIM_TABLES = ("program_claim", "program_engagement")
_FINDING_TABLES = ("agent_finding_resolution",)

_PARAMS = ["sqlite", pytest.param("warehouse", marks=pytest.mark.skipif(
    not LIVE, reason="set TCC_FABRIC_TESTS=1 to run the contract suite against the live Warehouse"))]


@pytest.fixture(params=_PARAMS)
def claim_repo(request, tmp_path, client_ids):
    if request.param == "sqlite":
        from infrastructure.persistence.sqlite_claims import SqliteClaimRepository

        repo = SqliteClaimRepository(tmp_path / "claims.db")
        yield repo
        repo.close()
        return
    from infrastructure.persistence.warehouse_claims import WarehouseClaimRepository

    yield WarehouseClaimRepository()
    _purge_warehouse(_CLAIM_TABLES, client_ids.issued)


@pytest.fixture(params=_PARAMS)
def finding_repo(request, tmp_path, client_ids):
    if request.param == "sqlite":
        from infrastructure.persistence.sqlite_findings import SqliteFindingRepository

        repo = SqliteFindingRepository(tmp_path / "findings.db")
        yield repo
        repo.close()
        return
    from infrastructure.persistence.warehouse_findings import WarehouseFindingRepository

    yield WarehouseFindingRepository()
    _purge_warehouse(_FINDING_TABLES, client_ids.issued)


_ARTIFACT_TABLES = ("artifact_access", "artifact")


@pytest.fixture(params=_PARAMS)
def artifact_repo(request, tmp_path, client_ids):
    if request.param == "sqlite":
        from infrastructure.persistence.sqlite_artifacts import SqliteArtifactRepository

        repo = SqliteArtifactRepository(tmp_path / "artifacts.db")
        yield repo
        repo.close()
        return
    from infrastructure.persistence.warehouse_artifacts import WarehouseArtifactRepository

    yield WarehouseArtifactRepository()
    _purge_warehouse(_ARTIFACT_TABLES, client_ids.issued)


AZURE = os.getenv("TCC_AZURE_TESTS") == "1"

#: Per-run marker so a live run can find and delete exactly the rows it wrote in
#: the channel tables, none of which is keyed by client_id alone.
RUN_TAG = f"t{int(time.time())}x{random.randint(100, 999)}"


def _purge_channel_rows(user_prefix: str) -> None:
    from infrastructure.persistence.fabric_warehouse import OPS_SCHEMA, FabricWarehouseConnection
    from infrastructure.persistence.tenant_sql import run_in_transaction, tenant_exempt

    cleanup = tenant_exempt("contract-test cleanup of this run's own channel rows")
    connection = FabricWarehouseConnection().open()
    try:
        def work(cursor):
            for table in ("channel_audit", "channel_user", "channel_confirmation"):
                cleanup.execute(cursor, f"DELETE FROM {OPS_SCHEMA}.{table} WHERE user_oid LIKE ?", [f"{user_prefix}%"])
            cleanup.execute(cursor, f"DELETE FROM {OPS_SCHEMA}.agent_action_audit WHERE agent_name LIKE ?", [f"{user_prefix}%"])

        run_in_transaction(connection, work)
    finally:
        connection.close()


@pytest.fixture
def user_prefix() -> str:
    """Every user oid and agent name a channel contract test uses starts with this."""
    return f"contract-{RUN_TAG}-"


def _channel_fixture(request, tmp_path, user_prefix, sqlite_factory, warehouse_factory):
    if request.param == "sqlite":
        repo = sqlite_factory(tmp_path / "channel.db")
        yield repo
        repo.close()
        return
    yield warehouse_factory()
    _purge_channel_rows(user_prefix)


@pytest.fixture(params=_PARAMS)
def channel_audit_repo(request, tmp_path, user_prefix, client_ids):
    from infrastructure.persistence.sqlite_channel import SqliteChannelAuditRepository
    from infrastructure.persistence.warehouse_channel import WarehouseChannelAuditRepository

    yield from _channel_fixture(request, tmp_path, user_prefix, SqliteChannelAuditRepository, WarehouseChannelAuditRepository)
    if request.param == "warehouse":
        _purge_warehouse(("channel_audit",), client_ids.issued)


@pytest.fixture(params=_PARAMS)
def agent_action_repo(request, tmp_path, user_prefix):
    from infrastructure.persistence.sqlite_channel import SqliteAgentActionAuditRepository
    from infrastructure.persistence.warehouse_channel import WarehouseAgentActionAuditRepository

    yield from _channel_fixture(request, tmp_path, user_prefix, SqliteAgentActionAuditRepository, WarehouseAgentActionAuditRepository)


@pytest.fixture(params=_PARAMS)
def writer_repo(request, tmp_path, user_prefix):
    from infrastructure.persistence.sqlite_channel_state import SqliteWriterRepository
    from infrastructure.persistence.warehouse_channel_state import WarehouseWriterRepository

    yield from _channel_fixture(request, tmp_path, user_prefix, SqliteWriterRepository, WarehouseWriterRepository)


@pytest.fixture(params=_PARAMS)
def confirmation_repo(request, tmp_path, user_prefix):
    from infrastructure.persistence.sqlite_channel_state import SqliteConfirmationRepository
    from infrastructure.persistence.warehouse_channel_state import WarehouseConfirmationRepository

    yield from _channel_fixture(request, tmp_path, user_prefix, SqliteConfirmationRepository, WarehouseConfirmationRepository)


@pytest.fixture(params=["local", pytest.param("blob", marks=pytest.mark.skipif(
    not AZURE, reason="set TCC_AZURE_TESTS=1 and ARTIFACT_BLOB_ACCOUNT_URL to run the store contract against Blob"))])
def artifact_store(request, tmp_path):
    if request.param == "local":
        from infrastructure.storage.local_store import LocalArtifactStore

        return LocalArtifactStore(tmp_path / "store")
    from infrastructure.storage.blob_store import BlobArtifactStore

    return BlobArtifactStore()
