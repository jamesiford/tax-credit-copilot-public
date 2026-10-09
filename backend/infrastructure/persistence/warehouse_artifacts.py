"""`ArtifactRepository` over the Fabric Warehouse: `tcc_ops.artifact` and `artifact_access`. [BLOB-3, ADR-007]

Every statement goes through `tenant_sql`. Two uses are deliberately exempt and
logged: the lookup by `artifact_id` that the download authorization starts from
(the caller's client is checked against the row it returns), and rows that
belong to no client (`rule_source` documents).
"""
from __future__ import annotations

from typing import Any

from application.artifacts import Artifact, ArtifactAccess
from infrastructure.persistence.fabric_warehouse import OPS_SCHEMA, FabricWarehouseConnection
from infrastructure.persistence.sqlite_artifacts import ACCESS_COLUMNS, ARTIFACT_COLUMNS, artifact_from_row
from infrastructure.persistence.tenant_sql import TenantScopedQuery, run_in_transaction, tenant_exempt
from infrastructure.persistence.warehouse_claims import from_db_instant, rows_as_dicts, to_db_instant

_LOOKUP = tenant_exempt("artifact lookup by id: the download authorization checks the owner it returns")
_UNOWNED = tenant_exempt("rule_source artifacts belong to no client")


def _value(obj: Any, column: str) -> Any:
    value = getattr(obj, column)
    if column in ("created_at", "superseded_at", "accessed_at"):
        return to_db_instant(value)
    return value


def _row(row: dict[str, Any]) -> Artifact:
    return artifact_from_row(row, parse=from_db_instant)


class WarehouseArtifactRepository:
    is_durable = True

    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        self._connection = connection or FabricWarehouseConnection()

    def record(self, artifact: Artifact) -> Artifact:
        values = [_value(artifact, c) for c in ARTIFACT_COLUMNS]
        table = f"{OPS_SCHEMA}.artifact"

        def work(cursor: Any) -> None:
            if artifact.client_id is None:
                _UNOWNED.execute(
                    cursor,
                    f"INSERT INTO {table} ({', '.join(ARTIFACT_COLUMNS)}) "
                    f"VALUES ({', '.join('?' for _ in ARTIFACT_COLUMNS)})",
                    values,
                )
                return
            scoped = TenantScopedQuery(artifact.client_id)
            if artifact.kind == "claim_package":
                scoped.execute(
                    cursor,
                    f"UPDATE {table} SET superseded_at = ? "
                    "WHERE {tenant} AND kind = ? AND tax_year = ? AND superseded_at IS NULL",
                    [to_db_instant(artifact.created_at), artifact.kind, artifact.tax_year],
                )
            scoped.insert(cursor, table, ARTIFACT_COLUMNS, [values])

        with self._connection.connect() as connection:
            run_in_transaction(connection, work)
        return artifact

    def find(self, artifact_id: str) -> Artifact | None:
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                _LOOKUP.execute(
                    cursor,
                    f"SELECT {', '.join(ARTIFACT_COLUMNS)} FROM {OPS_SCHEMA}.artifact WHERE artifact_id = ?",
                    [artifact_id],
                )
                rows = rows_as_dicts(cursor)
            finally:
                cursor.close()
        return _row(rows[0]) if rows else None

    def live(self, client_id: int, *, kind: str | None = None, tax_year: int | None = None) -> list[Artifact]:
        sql = (
            f"SELECT {', '.join(ARTIFACT_COLUMNS)} FROM {OPS_SCHEMA}.artifact "
            "WHERE {tenant} AND superseded_at IS NULL"
        )
        params: list[Any] = []
        if kind is not None:
            sql += " AND kind = ?"
            params.append(kind)
        if tax_year is not None:
            sql += " AND tax_year = ?"
            params.append(tax_year)
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                TenantScopedQuery(client_id).execute(cursor, sql + " ORDER BY created_at, artifact_id", params)
                return [_row(r) for r in rows_as_dicts(cursor)]
            finally:
                cursor.close()

    def record_access(self, access: ArtifactAccess) -> ArtifactAccess:
        values = [_value(access, c) for c in ACCESS_COLUMNS]
        table = f"{OPS_SCHEMA}.artifact_access"

        def work(cursor: Any) -> None:
            if access.client_id is None:
                _UNOWNED.execute(
                    cursor,
                    f"INSERT INTO {table} ({', '.join(ACCESS_COLUMNS)}) "
                    f"VALUES ({', '.join('?' for _ in ACCESS_COLUMNS)})",
                    values,
                )
            else:
                TenantScopedQuery(access.client_id).insert(cursor, table, ACCESS_COLUMNS, [values])

        with self._connection.connect() as connection:
            run_in_transaction(connection, work)
        return access

    def accesses(self, client_id: int) -> list[ArtifactAccess]:
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                TenantScopedQuery(client_id).execute(
                    cursor,
                    f"SELECT {', '.join(ACCESS_COLUMNS)} FROM {OPS_SCHEMA}.artifact_access "
                    "WHERE {tenant} ORDER BY accessed_at, access_id",
                )
                rows = rows_as_dicts(cursor)
            finally:
                cursor.close()
        return [
            ArtifactAccess(
                access_id=r["access_id"], artifact_id=r["artifact_id"],
                client_id=int(r["client_id"]) if r["client_id"] is not None else None,
                user_upn=r["user_upn"], user_oid=r["user_oid"], outcome=r["outcome"],
                accessed_at=from_db_instant(r["accessed_at"]),
            )
            for r in rows
        ]
