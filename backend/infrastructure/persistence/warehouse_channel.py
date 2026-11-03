"""`ChannelAuditRepository` and `AgentActionAuditRepository` over the Warehouse. [ADR-007]

Every statement goes through `tenant_sql`. An event that names a client is
written under `TenantScopedQuery` like any other row. The exemptions are exactly
the ones below, each with its reason, and each touches only `channel_audit` or
`agent_action_audit` — `test_architecture` enforces that this file reaches no
other table:

- a row that names no client (a book-wide read, a resolver turn) has no tenant
  to bind;
- a user's timeline and a correlation id span clients by design: the question
  is "what did this person do", not "what happened to this client".

Insert-only. There is no update and no delete here.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from domain.channel import AgentActionAudit, ChannelAuditEvent
from infrastructure.persistence.fabric_warehouse import OPS_SCHEMA, FabricWarehouseConnection
from infrastructure.persistence.sqlite_channel import (
    ACTION_COLUMNS, EVENT_COLUMNS, action_from_row, action_values, event_from_row, event_values,
)
from infrastructure.persistence.tenant_sql import TenantScopedQuery, run_in_transaction, tenant_exempt
from infrastructure.persistence.warehouse_claims import from_db_instant, rows_as_dicts, to_db_instant

_AUDIT_UNSCOPED = tenant_exempt("channel audit event that names no client has no tenant to bind")
_AUDIT_BY_USER = tenant_exempt("channel audit by user: an operator's timeline spans clients by design")
_AUDIT_BY_CORRELATION = tenant_exempt("channel audit by correlation id: one turn can touch several clients")
_ACTION_UNSCOPED = tenant_exempt("agent action that names no client has no tenant to bind")
_ACTION_RECENT = tenant_exempt("agent action trail read: the narrator's activity spans clients by design")

_AUDIT = f"{OPS_SCHEMA}.channel_audit"
_ACTIONS = f"{OPS_SCHEMA}.agent_action_audit"


def _db(value: Any) -> Any:
    return to_db_instant(value) if isinstance(value, datetime) else value


def _insert(connection: Any, table: str, columns: tuple[str, ...], values: list[Any],
            client_id: int | None, unscoped_execute: Callable[..., Any]) -> None:
    """One row. Under the client's tenant when it names one, else through the named exemption."""
    def work(cursor: Any) -> None:
        if client_id is None:
            unscoped_execute(
                cursor,
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                values,
            )
        else:
            TenantScopedQuery(client_id).insert(cursor, table, columns, [values])

    run_in_transaction(connection, work)


def select_rows(connection: Any, execute: Callable[..., Any], sql: str, params: list[Any]) -> list[dict[str, Any]]:
    """Run a read through a named exemption's `execute` and return dict rows."""
    cursor = connection.cursor()
    try:
        execute(cursor, sql, params)
        return rows_as_dicts(cursor)
    finally:
        cursor.close()


class WarehouseChannelAuditRepository:
    is_durable = True

    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        self._connection = connection or FabricWarehouseConnection()

    def append(self, event: ChannelAuditEvent) -> None:
        with self._connection.connect() as connection:
            _insert(
                connection, _AUDIT, EVENT_COLUMNS, event_values(event, instant=_db),
                event.client_id, _AUDIT_UNSCOPED.execute,
            )

    def for_user(
        self, user_oid: str, since: datetime | None = None, until: datetime | None = None,
        tool: str | None = None, limit: int = 200,
    ) -> list[ChannelAuditEvent]:
        sql, params = f"SELECT TOP {int(limit)} {', '.join(EVENT_COLUMNS)} FROM {_AUDIT} WHERE user_oid = ?", [user_oid]
        for clause, value in (
            (" AND occurred_at >= ?", since and to_db_instant(since)),
            (" AND occurred_at < ?", until and to_db_instant(until)),
            (" AND tool_name = ?", tool),
        ):
            if value is not None:
                sql, params = sql + clause, [*params, value]
        with self._connection.connect() as connection:
            rows = select_rows(connection, _AUDIT_BY_USER.execute, sql + " ORDER BY occurred_at DESC, event_seq DESC", params)
        return [event_from_row(r, parse=from_db_instant) for r in rows]

    def by_correlation(self, correlation_id: str) -> list[ChannelAuditEvent]:
        with self._connection.connect() as connection:
            rows = select_rows(
                connection, _AUDIT_BY_CORRELATION.execute,
                f"SELECT {', '.join(EVENT_COLUMNS)} FROM {_AUDIT} WHERE correlation_id = ? "
                "ORDER BY occurred_at, event_seq",
                [correlation_id],
            )
        return [event_from_row(r, parse=from_db_instant) for r in rows]


class WarehouseAgentActionAuditRepository:
    is_durable = True

    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        self._connection = connection or FabricWarehouseConnection()

    def append(self, action: AgentActionAudit) -> None:
        with self._connection.connect() as connection:
            _insert(
                connection, _ACTIONS, ACTION_COLUMNS, action_values(action, instant=_db),
                action.client_id, _ACTION_UNSCOPED.execute,
            )

    def recent(self, agent_name: str | None = None, limit: int = 100) -> list[AgentActionAudit]:
        sql, params = f"SELECT TOP {int(limit)} {', '.join(ACTION_COLUMNS)} FROM {_ACTIONS}", []
        if agent_name is not None:
            sql, params = sql + " WHERE agent_name = ?", [agent_name]
        with self._connection.connect() as connection:
            rows = select_rows(connection, _ACTION_RECENT.execute, sql + " ORDER BY occurred_at DESC, action_id", params)
        return [action_from_row(r, parse=from_db_instant) for r in rows]
