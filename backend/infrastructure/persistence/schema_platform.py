"""Azure SQL as the target of the schema and migration tooling. [09]

The Fabric path resolves a Warehouse through the Fabric REST API and refuses any server that is not
that endpoint. Azure SQL has no such API in this stack, so the allow-list is the server FQDN and the
database name, with the same `bootstrap_approved` rule and the same promise: a mismatch raises
`TargetMismatch` BEFORE any statement runs.

The numbered migrations and the bootstrap are written to the Fabric T-SQL subset. That subset is valid
SQL Server except for one clause, so `sqlserver_sql` makes the one mechanical edit
`scripts/generate-schema-variants.py` makes, at apply time. That covers every migration, including
ones added later, without a generated copy that could fall behind.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from infrastructure.persistence.schema_admin import TargetMismatch, _host

_NOT_ENFORCED = re.compile(r"[ \t]+NOT[ \t]+ENFORCED\b", re.IGNORECASE)


def sqlserver_sql(sql: str) -> str:
    """Fabric T-SQL as SQL Server accepts it: advisory keys become enforced keys."""
    return _NOT_ENFORCED.sub("", sql)


@dataclass(frozen=True)
class AllowedSqlTarget:
    """One Azure SQL database a script may touch."""

    name: str
    server: str
    database: str
    bootstrap_approved: bool = False


def check_sql_target(allowed: AllowedSqlTarget, *, server: str, database: str) -> None:
    """Raise `TargetMismatch` unless the configured server and database are the allowed ones."""
    problems: list[str] = []
    if _host(server) != _host(allowed.server):
        problems.append(f"WAREHOUSE_SERVER {server!r} != allowed {allowed.server!r}")
    if (database or "").strip().lower() != allowed.database.strip().lower():
        problems.append(f"WAREHOUSE_DATABASE {database!r} != allowed {allowed.database!r}")
    if problems:
        raise TargetMismatch(f"target '{allowed.name}' refused: " + "; ".join(problems))


def load_pinned_sql_targets(path: Path) -> dict[str, AllowedSqlTarget]:
    """The `platform: azure_sql` entries of the pinned-target file. An absent file pins nothing."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        name: AllowedSqlTarget(
            name=name,
            server=entry["server"],
            database=entry["database"],
            bootstrap_approved=bool(entry.get("bootstrap_approved", False)),
        )
        for name, entry in data.items()
        if not name.startswith("_") and entry.get("platform") == "azure_sql"
    }
