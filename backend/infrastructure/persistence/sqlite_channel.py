"""The channel audit trail and the agent-action trail over SQLite: development and CI. [ADR-007]

Mirrors `tcc_ops.channel_audit` and `tcc_ops.agent_action_audit`. Insert-only:
there is no update and no delete path in this class, so "append-only" is a
property of the code and not a convention.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from domain.channel import AgentActionAudit, ChannelAuditEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS channel_audit (
    audit_id TEXT NOT NULL, event_seq INTEGER NOT NULL, phase TEXT NOT NULL,
    correlation_id TEXT NOT NULL, occurred_at TEXT NOT NULL, elapsed_ms INTEGER,
    channel TEXT NOT NULL, user_oid TEXT NOT NULL, tenant_id TEXT,
    user_display_name TEXT, user_upn TEXT, identity_assurance TEXT NOT NULL,
    conversation_id TEXT, tool_name TEXT NOT NULL, action_kind TEXT NOT NULL,
    client_id INTEGER, tax_year INTEGER, request_summary TEXT, request_sha256 TEXT,
    confirmation_ref TEXT, outcome TEXT NOT NULL, error TEXT, run_id TEXT,
    trail_sha256 TEXT, numeric_guard TEXT NOT NULL, is_deterministic_path INTEGER NOT NULL,
    PRIMARY KEY (audit_id, event_seq)
);
CREATE INDEX IF NOT EXISTS ix_channel_audit_user ON channel_audit (user_oid, occurred_at);
CREATE INDEX IF NOT EXISTS ix_channel_audit_correlation ON channel_audit (correlation_id, occurred_at);

CREATE TABLE IF NOT EXISTS agent_action_audit (
    action_id TEXT PRIMARY KEY, run_id TEXT, client_id INTEGER, agent_name TEXT NOT NULL,
    agent_version TEXT, model_deployment TEXT, prompt_hash TEXT, tool_calls TEXT,
    input_summary TEXT, output_summary TEXT, user_upn TEXT, occurred_at TEXT NOT NULL,
    is_deterministic_path INTEGER NOT NULL
);
"""

EVENT_COLUMNS = (
    "audit_id", "event_seq", "phase", "correlation_id", "occurred_at", "elapsed_ms", "channel",
    "user_oid", "tenant_id", "user_display_name", "user_upn", "identity_assurance",
    "conversation_id", "tool_name", "action_kind", "client_id", "tax_year", "request_summary",
    "request_sha256", "confirmation_ref", "outcome", "error", "run_id", "trail_sha256",
    "numeric_guard", "is_deterministic_path",
)
ACTION_COLUMNS = (
    "action_id", "run_id", "client_id", "agent_name", "agent_version", "model_deployment",
    "prompt_hash", "tool_calls", "input_summary", "output_summary", "user_upn", "occurred_at",
    "is_deterministic_path",
)
_INSTANTS = ("occurred_at",)

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "operational.db"


def utc_iso(value: datetime) -> str:
    """UTC, so lexical order is chronological order."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def parse_instant(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def event_from_row(row: dict[str, Any], *, parse=parse_instant) -> ChannelAuditEvent:
    values = {c: row[c] for c in EVENT_COLUMNS}
    values["occurred_at"] = parse(values["occurred_at"])
    values["is_deterministic_path"] = bool(values["is_deterministic_path"])
    for key in ("event_seq", "elapsed_ms", "client_id", "tax_year"):
        if values[key] is not None:
            values[key] = int(values[key])
    for key in ("request_sha256", "trail_sha256"):
        if values[key] is not None:
            values[key] = str(values[key]).strip()
    return ChannelAuditEvent(**values)


def event_values(event: ChannelAuditEvent, *, instant=utc_iso) -> list[Any]:
    return [
        instant(getattr(event, c)) if c in _INSTANTS else getattr(event, c)
        for c in EVENT_COLUMNS
    ]


class SqliteBase:
    """One connection per thread over one file. Shared by the channel stores."""

    is_durable = False
    schema = _SCHEMA

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else Path(os.getenv("OPERATIONAL_DB", _DEFAULT_PATH))
        self._local = threading.local()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(self.schema)

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


class SqliteChannelAuditRepository(SqliteBase):
    def append(self, event: ChannelAuditEvent) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                f"INSERT INTO channel_audit ({', '.join(EVENT_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in EVENT_COLUMNS)})",
                event_values(event),
            )

    def for_user(
        self, user_oid: str, since: datetime | None = None, until: datetime | None = None,
        tool: str | None = None, limit: int = 200,
    ) -> list[ChannelAuditEvent]:
        sql, params = "SELECT * FROM channel_audit WHERE user_oid = ?", [user_oid]
        if since is not None:
            sql, params = sql + " AND occurred_at >= ?", [*params, utc_iso(since)]
        if until is not None:
            sql, params = sql + " AND occurred_at < ?", [*params, utc_iso(until)]
        if tool is not None:
            sql, params = sql + " AND tool_name = ?", [*params, tool]
        rows = self._connect().execute(
            sql + " ORDER BY occurred_at DESC, event_seq DESC LIMIT ?", [*params, int(limit)]
        ).fetchall()
        return [event_from_row(dict(r)) for r in rows]

    def by_correlation(self, correlation_id: str) -> list[ChannelAuditEvent]:
        rows = self._connect().execute(
            "SELECT * FROM channel_audit WHERE correlation_id = ? ORDER BY occurred_at, event_seq",
            (correlation_id,),
        ).fetchall()
        return [event_from_row(dict(r)) for r in rows]


def action_from_row(row: dict[str, Any], *, parse=parse_instant) -> AgentActionAudit:
    values = {c: row[c] for c in ACTION_COLUMNS}
    values["occurred_at"] = parse(values["occurred_at"])
    values["is_deterministic_path"] = bool(values["is_deterministic_path"])
    if values["client_id"] is not None:
        values["client_id"] = int(values["client_id"])
    if values["prompt_hash"] is not None:
        values["prompt_hash"] = str(values["prompt_hash"]).strip()
    return AgentActionAudit(**values)


def action_values(action: AgentActionAudit, *, instant=utc_iso) -> list[Any]:
    return [
        instant(getattr(action, c)) if c in _INSTANTS else getattr(action, c)
        for c in ACTION_COLUMNS
    ]


class SqliteAgentActionAuditRepository(SqliteBase):
    def append(self, action: AgentActionAudit) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                f"INSERT INTO agent_action_audit ({', '.join(ACTION_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in ACTION_COLUMNS)})",
                action_values(action),
            )

    def recent(self, agent_name: str | None = None, limit: int = 100) -> list[AgentActionAudit]:
        sql, params = "SELECT * FROM agent_action_audit", []
        if agent_name is not None:
            sql, params = sql + " WHERE agent_name = ?", [agent_name]
        rows = self._connect().execute(
            sql + " ORDER BY occurred_at DESC, action_id LIMIT ?", [*params, int(limit)]
        ).fetchall()
        return [action_from_row(dict(r)) for r in rows]
