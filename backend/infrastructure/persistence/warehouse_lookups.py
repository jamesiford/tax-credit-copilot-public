"""`LookupOverrideStore` over the Fabric Warehouse: `tcc_ops.lookup_override` and `lookup_audit` (migration 0003). [07]

Same append-style semantics as the SQLite adapter. Every statement is tenant-scoped through `tenant_sql`: a client's
rows are read under its own `client_id`, and the GLOBAL rows live under the sentinel `client_id` 0, read by a second
scoped statement, so no statement ever runs without a tenant predicate and a read for one client cannot return another's
rows. Not exercised against a live Warehouse in this repository's tests (LIVE-CHECK-REQUIRED).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from data.lookups.store import GLOBAL_CLIENT, OverrideEntry
from infrastructure.persistence.fabric_warehouse import names, FabricWarehouseConnection
from infrastructure.persistence.tenant_sql import TenantScopedQuery, run_in_transaction
from infrastructure.persistence.warehouse_claims import rows_as_dicts, to_db_instant

_OVERRIDE = f"{names.ops.lookup_override}"
_AUDIT = f"{names.ops.lookup_audit}"
_COLUMNS = ("override_id", "lookup_name", "client_id", "key_kind", "key_value", "value_json", "effective_from",
            "effective_to", "authored_by", "authored_on", "basis", "inferred", "superseded_at")


def _now() -> datetime:
    return to_db_instant(datetime.now(timezone.utc))


class WarehouseLookupStore:
    """Durable app-owned lookup rows in the Warehouse."""

    is_durable = True

    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        self._connection = connection or FabricWarehouseConnection()

    def _live(self, lookup: str, client_id: int) -> list[dict[str, Any]]:
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                TenantScopedQuery(client_id).execute(
                    cursor, f"SELECT {', '.join(_COLUMNS)} FROM {_OVERRIDE} WHERE {{tenant}} AND lookup_name = ? AND superseded_at IS NULL",
                    [lookup])
                return rows_as_dicts(cursor)
            finally:
                cursor.close()

    def entries(self, lookup: str, client_id: int) -> list[OverrideEntry]:
        rows = self._live(lookup, client_id) + (self._live(lookup, GLOBAL_CLIENT) if client_id != GLOBAL_CLIENT else [])
        return [OverrideEntry(
            r["lookup_name"], int(r["client_id"]), r["key_kind"], r["key_value"], r["value_json"], r["authored_by"],
            r["basis"] or "", bool(r["inferred"]),
            r["effective_from"] if isinstance(r["effective_from"], date) else None,
            r["effective_to"] if isinstance(r["effective_to"], date) else None,
        ) for r in rows]

    def _audit(self, scoped: TenantScopedQuery, cursor: Any, action: str, entry: tuple, actor: str, basis: str = "") -> None:
        lookup, client_id, kind, key, value = entry
        scoped.insert(cursor, _AUDIT, ("audit_id", "lookup_name", "client_id", "action", "key_kind", "key_value", "value_json", "actor", "at", "basis"),
                      [[str(uuid.uuid4()), lookup, client_id, action, kind, key, value, actor, _now(), basis]])

    def put(self, entry: OverrideEntry) -> None:
        scoped = TenantScopedQuery(entry.client_id)
        now = _now()

        def work(cursor: Any) -> None:
            scoped.execute(cursor, f"UPDATE {_OVERRIDE} SET superseded_at = ? WHERE {{tenant}} AND lookup_name = ? AND key_kind = ? "
                           "AND key_value = ? AND superseded_at IS NULL", [now, entry.lookup, entry.key_kind, entry.key])
            scoped.insert(cursor, _OVERRIDE, _COLUMNS, [[
                str(uuid.uuid4()), entry.lookup, entry.client_id, entry.key_kind, entry.key, entry.value, entry.effective_from,
                entry.effective_to, entry.authored_by, now, entry.basis, int(entry.inferred), None]])
            self._audit(scoped, cursor, "put", (entry.lookup, entry.client_id, entry.key_kind, entry.key, entry.value), entry.authored_by, entry.basis)

        with self._connection.connect() as connection:
            run_in_transaction(connection, work)

    def remove(self, lookup: str, client_id: int, key_kind: str, key: str, actor: str) -> bool:
        scoped = TenantScopedQuery(client_id)
        closed: list[int] = []

        def work(cursor: Any) -> None:
            scoped.execute(cursor, f"UPDATE {_OVERRIDE} SET superseded_at = ? WHERE {{tenant}} AND lookup_name = ? AND key_kind = ? "
                           "AND key_value = ? AND superseded_at IS NULL", [_now(), lookup, key_kind, key])
            closed.append(cursor.rowcount)
            if cursor.rowcount:
                self._audit(scoped, cursor, "remove", (lookup, client_id, key_kind, key, None), actor)

        with self._connection.connect() as connection:
            run_in_transaction(connection, work)
        return bool(closed and closed[0])

    def audit(self, lookup: str | None = None) -> list[dict]:
        from infrastructure.persistence.tenant_sql import tenant_exempt

        sql = f"SELECT * FROM {_AUDIT}" + (" WHERE lookup_name = ?" if lookup else "") + " ORDER BY at, audit_id"
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                tenant_exempt("lookup audit is read across clients by the operator CLI").execute(cursor, sql, [lookup] if lookup else [])
                return rows_as_dicts(cursor)
            finally:
                cursor.close()
