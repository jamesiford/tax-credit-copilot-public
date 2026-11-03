"""`WriterRepository` and `ConfirmationRepository` over the Warehouse. [ADR-007]

`channel_user` and `channel_confirmation` belong to no client — who may write,
and which token was issued — so every statement here is tenant-exempt, with the
reason stated. They are the only exemptions in this file, and they touch only
those two tables (`test_architecture` enforces it).

The allow-list is append-only: a removal stamps `removed_at`; re-adding inserts
a new live row. A confirmation changes in two places only: `consumed_at` (once,
guarded by `consumed_at IS NULL` so two commits racing for one token cannot both
win) and the stored result an idempotent replay returns.
"""
from __future__ import annotations

from datetime import datetime

from domain.channel import Confirmation, WriterGrant, utcnow
from infrastructure.persistence.fabric_warehouse import OPS_SCHEMA, FabricWarehouseConnection
from infrastructure.persistence.sqlite_channel_state import (
    CONFIRMATION_COLUMNS, GRANT_COLUMNS, confirmation_from_row, confirmation_values,
    grant_from_row, grant_values,
)
from infrastructure.persistence.tenant_sql import run_in_transaction, tenant_exempt
from infrastructure.persistence.warehouse_channel import select_rows
from infrastructure.persistence.warehouse_claims import from_db_instant, to_db_instant

_WRITERS = tenant_exempt("channel_user allow-list is not per client")
_CONFIRMATIONS = tenant_exempt("channel_confirmation tokens are not per client")

_USERS = f"{OPS_SCHEMA}.channel_user"
_CONFIRM = f"{OPS_SCHEMA}.channel_confirmation"


def _db(value):
    return to_db_instant(value) if isinstance(value, datetime) else value


class WarehouseWriterRepository:
    is_durable = True

    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        self._connection = connection or FabricWarehouseConnection()

    def grant(self, grant: WriterGrant) -> WriterGrant:
        def work(cursor):
            _WRITERS.execute(
                cursor, f"UPDATE {_USERS} SET removed_at = ? WHERE user_oid = ? AND removed_at IS NULL",
                [to_db_instant(grant.added_at), grant.user_oid],
            )
            _WRITERS.execute(
                cursor,
                f"INSERT INTO {_USERS} ({', '.join(GRANT_COLUMNS)}) VALUES ({', '.join('?' for _ in GRANT_COLUMNS)})",
                grant_values(grant, instant=_db),
            )

        with self._connection.connect() as connection:
            run_in_transaction(connection, work)
        return grant

    def revoke(self, user_oid: str, at: datetime | None = None) -> bool:
        def work(cursor):
            _WRITERS.execute(
                cursor, f"UPDATE {_USERS} SET removed_at = ? WHERE user_oid = ? AND removed_at IS NULL",
                [to_db_instant(at or utcnow()), user_oid],
            )
            return cursor.rowcount

        with self._connection.connect() as connection:
            return run_in_transaction(connection, work) > 0

    def is_writer(self, user_oid: str) -> bool:
        with self._connection.connect() as connection:
            rows = select_rows(
                connection, _WRITERS.execute,
                f"SELECT user_oid FROM {_USERS} WHERE user_oid = ? AND removed_at IS NULL", [user_oid],
            )
        return bool(rows)

    def live(self) -> list[WriterGrant]:
        with self._connection.connect() as connection:
            rows = select_rows(
                connection, _WRITERS.execute,
                f"SELECT {', '.join(GRANT_COLUMNS)} FROM {_USERS} WHERE removed_at IS NULL "
                "ORDER BY added_at, user_oid", [],
            )
        return [grant_from_row(r, parse=from_db_instant) for r in rows]


class WarehouseConfirmationRepository:
    is_durable = True

    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        self._connection = connection or FabricWarehouseConnection()

    def create(self, confirmation: Confirmation) -> Confirmation:
        def work(cursor):
            _CONFIRMATIONS.execute(
                cursor,
                f"INSERT INTO {_CONFIRM} ({', '.join(CONFIRMATION_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in CONFIRMATION_COLUMNS)})",
                confirmation_values(confirmation, instant=_db),
            )

        with self._connection.connect() as connection:
            run_in_transaction(connection, work)
        return confirmation

    def _one(self, sql: str, params: list) -> Confirmation | None:
        with self._connection.connect() as connection:
            rows = select_rows(connection, _CONFIRMATIONS.execute, sql, params)
        return confirmation_from_row(rows[0], parse=from_db_instant) if rows else None

    def find_by_token_hash(self, token_sha256: str) -> Confirmation | None:
        return self._one(
            f"SELECT {', '.join(CONFIRMATION_COLUMNS)} FROM {_CONFIRM} WHERE token_sha256 = ?", [token_sha256]
        )

    def find_by_idempotency_key(self, user_oid: str, key: str) -> Confirmation | None:
        return self._one(
            f"SELECT TOP 1 {', '.join(CONFIRMATION_COLUMNS)} FROM {_CONFIRM} WHERE user_oid = ? "
            "AND idempotency_key = ? AND outcome IS NOT NULL ORDER BY created_at",
            [user_oid, key],
        )

    def consume(self, confirmation_id: str, at: datetime, idempotency_key: str | None = None) -> bool:
        def work(cursor):
            _CONFIRMATIONS.execute(
                cursor,
                f"UPDATE {_CONFIRM} SET consumed_at = ?, idempotency_key = ? "
                "WHERE confirmation_id = ? AND consumed_at IS NULL",
                [to_db_instant(at), idempotency_key, confirmation_id],
            )
            return cursor.rowcount

        with self._connection.connect() as connection:
            return run_in_transaction(connection, work) == 1

    def record_result(self, confirmation_id: str, outcome: str, result_json: str | None) -> None:
        def work(cursor):
            _CONFIRMATIONS.execute(
                cursor, f"UPDATE {_CONFIRM} SET outcome = ?, result_json = ? WHERE confirmation_id = ?",
                [outcome, result_json, confirmation_id],
            )

        with self._connection.connect() as connection:
            run_in_transaction(connection, work)
