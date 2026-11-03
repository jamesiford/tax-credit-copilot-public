"""The writer allow-list and the confirmation tokens over SQLite. [ADR-007]

Mirrors `tcc_ops.channel_user` and `tcc_ops.channel_confirmation`. The only
mutations are the two transitions those tables exist for: a grant's `removed_at`
and a confirmation's `consumed_at` (and, for an idempotent replay, the result
stored once the command has run). Nothing is ever deleted.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from domain.channel import Confirmation, WriterGrant, utcnow
from infrastructure.persistence.sqlite_channel import SqliteBase, parse_instant, utc_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS channel_user (
    user_oid TEXT NOT NULL, display_name TEXT, role TEXT NOT NULL,
    added_by TEXT NOT NULL, added_at TEXT NOT NULL, removed_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_channel_user_oid ON channel_user (user_oid);

CREATE TABLE IF NOT EXISTS channel_confirmation (
    confirmation_id TEXT PRIMARY KEY, token_sha256 TEXT NOT NULL, user_oid TEXT NOT NULL,
    tool_name TEXT NOT NULL, args_sha256 TEXT NOT NULL, idempotency_key TEXT,
    created_at TEXT NOT NULL, expires_at TEXT NOT NULL, consumed_at TEXT,
    outcome TEXT, result_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_channel_confirmation_token ON channel_confirmation (token_sha256);
"""

GRANT_COLUMNS = ("user_oid", "display_name", "role", "added_by", "added_at", "removed_at")
CONFIRMATION_COLUMNS = (
    "confirmation_id", "token_sha256", "user_oid", "tool_name", "args_sha256", "idempotency_key",
    "created_at", "expires_at", "consumed_at", "outcome", "result_json",
)
_GRANT_INSTANTS = ("added_at", "removed_at")
_CONFIRMATION_INSTANTS = ("created_at", "expires_at", "consumed_at")


def grant_from_row(row: dict[str, Any], *, parse=parse_instant) -> WriterGrant:
    return WriterGrant(
        user_oid=row["user_oid"], display_name=row["display_name"], role=row["role"],
        added_by=row["added_by"], added_at=parse(row["added_at"]), removed_at=parse(row["removed_at"]),
    )


def confirmation_from_row(row: dict[str, Any], *, parse=parse_instant) -> Confirmation:
    values = {c: row[c] for c in CONFIRMATION_COLUMNS}
    for column in _CONFIRMATION_INSTANTS:
        values[column] = parse(values[column])
    values["token_sha256"] = str(values["token_sha256"]).strip()
    values["args_sha256"] = str(values["args_sha256"]).strip()
    return Confirmation(**values)


def grant_values(grant: WriterGrant, *, instant=utc_iso) -> list[Any]:
    return [
        (instant(v) if (v := getattr(grant, c)) is not None and c in _GRANT_INSTANTS else v)
        for c in GRANT_COLUMNS
    ]


def confirmation_values(item: Confirmation, *, instant=utc_iso) -> list[Any]:
    return [
        (instant(v) if (v := getattr(item, c)) is not None and c in _CONFIRMATION_INSTANTS else v)
        for c in CONFIRMATION_COLUMNS
    ]


class SqliteWriterRepository(SqliteBase):
    schema = _SCHEMA

    def grant(self, grant: WriterGrant) -> WriterGrant:
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE channel_user SET removed_at = ? WHERE user_oid = ? AND removed_at IS NULL",
                (utc_iso(grant.added_at), grant.user_oid),
            )
            conn.execute(
                f"INSERT INTO channel_user ({', '.join(GRANT_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in GRANT_COLUMNS)})",
                grant_values(grant),
            )
        return grant

    def revoke(self, user_oid: str, at: datetime | None = None) -> bool:
        conn = self._connect()
        with conn:
            cursor = conn.execute(
                "UPDATE channel_user SET removed_at = ? WHERE user_oid = ? AND removed_at IS NULL",
                (utc_iso(at or utcnow()), user_oid),
            )
        return cursor.rowcount > 0

    def is_writer(self, user_oid: str) -> bool:
        row = self._connect().execute(
            "SELECT 1 FROM channel_user WHERE user_oid = ? AND removed_at IS NULL", (user_oid,)
        ).fetchone()
        return row is not None

    def live(self) -> list[WriterGrant]:
        rows = self._connect().execute(
            "SELECT * FROM channel_user WHERE removed_at IS NULL ORDER BY added_at, user_oid"
        ).fetchall()
        return [grant_from_row(dict(r)) for r in rows]


class SqliteConfirmationRepository(SqliteBase):
    schema = _SCHEMA

    def create(self, confirmation: Confirmation) -> Confirmation:
        conn = self._connect()
        with conn:
            conn.execute(
                f"INSERT INTO channel_confirmation ({', '.join(CONFIRMATION_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in CONFIRMATION_COLUMNS)})",
                confirmation_values(confirmation),
            )
        return confirmation

    def _one(self, sql: str, params: tuple) -> Confirmation | None:
        row = self._connect().execute(sql, params).fetchone()
        return confirmation_from_row(dict(row)) if row else None

    def find_by_token_hash(self, token_sha256: str) -> Confirmation | None:
        return self._one("SELECT * FROM channel_confirmation WHERE token_sha256 = ?", (token_sha256,))

    def find_by_idempotency_key(self, user_oid: str, key: str) -> Confirmation | None:
        return self._one(
            "SELECT * FROM channel_confirmation WHERE user_oid = ? AND idempotency_key = ? "
            "AND outcome IS NOT NULL ORDER BY created_at LIMIT 1",
            (user_oid, key),
        )

    def consume(self, confirmation_id: str, at: datetime, idempotency_key: str | None = None) -> bool:
        conn = self._connect()
        with conn:
            cursor = conn.execute(
                "UPDATE channel_confirmation SET consumed_at = ?, idempotency_key = ? "
                "WHERE confirmation_id = ? AND consumed_at IS NULL",
                (utc_iso(at), idempotency_key, confirmation_id),
            )
        return cursor.rowcount == 1

    def record_result(self, confirmation_id: str, outcome: str, result_json: str | None) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE channel_confirmation SET outcome = ?, result_json = ? WHERE confirmation_id = ?",
                (outcome, result_json, confirmation_id),
            )
