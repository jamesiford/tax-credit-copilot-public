"""Shared plumbing for scripts/run-sql.py and scripts/apply-migrations.py.

Kept out of `backend/` because it reads `docs/` (the pinned-target file and the
DDL), which runtime code must never do. The logic it wires up lives in
`backend/infrastructure/persistence/schema_admin.py`, where it is unit-tested.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
SCHEMA_DIR = REPO / "docs" / "data" / "schema"
BOOTSTRAP_DDL = SCHEMA_DIR / "tcc-schema.fabric.sql"
MIGRATIONS_DIR = SCHEMA_DIR / "migrations"
PINNED_TARGETS = REPO / "docs" / "platform-v2" / "live-targets.json"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Exit codes the callers (and AGENTS.md) rely on.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_GUARD = 3


def load_env() -> None:
    """backend/.env for local runs; a deployed hook already has its environment."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is a backend dependency
        return
    load_dotenv(BACKEND / ".env", override=False)


def fabric_get_json(url: str, *, attempts: int = 4) -> dict:
    """GET a Fabric REST resource. Transport resets are retried; HTTP errors are not."""
    import time
    import urllib.error

    from azure.identity import DefaultAzureCredential

    token = DefaultAzureCredential().get_token("https://api.fabric.microsoft.com/.default").token
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https host
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if attempt == attempts:
                raise
            time.sleep(2 * attempt)
    raise RuntimeError("unreachable")


def allowed_target(name: str):
    """The allow-list entry a target name refers to.

    `deployed` is the Warehouse this environment's Terraform outputs name
    (FABRIC_WORKSPACE_ID / FABRIC_WAREHOUSE_ID). It may be bootstrapped only
    when TCC_FABRIC_CREATED=true, i.e. Terraform created it in this apply.
    Any other name must be pinned in docs/platform-v2/live-targets.json.
    """
    from infrastructure.persistence.schema_admin import AllowedTarget, TargetMismatch, load_pinned_targets

    if name == "deployed":
        workspace = os.getenv("FABRIC_WORKSPACE_ID", "").strip()
        item = os.getenv("FABRIC_WAREHOUSE_ID", "").strip()
        if not workspace or not item:
            raise TargetMismatch("target 'deployed' needs FABRIC_WORKSPACE_ID and FABRIC_WAREHOUSE_ID")
        return AllowedTarget(
            name="deployed",
            workspace_id=workspace,
            item_id=item,
            bootstrap_approved=os.getenv("TCC_FABRIC_CREATED", "").strip().lower() == "true",
        )
    pinned = load_pinned_targets(PINNED_TARGETS)
    if name not in pinned:
        raise TargetMismatch(f"unknown target '{name}'; allowed: deployed, {', '.join(sorted(pinned)) or '(none pinned)'}")
    return pinned[name]


def guarded_connection(target_name: str, *, resolve_only: bool = False):
    """Resolve, check, and only then connect. Returns (allowed, resolved, connection|None)."""
    from config import OPS_SCHEMA  # noqa: F401 - validates schema config before any connect
    from infrastructure.persistence.fabric_warehouse import FabricWarehouseConnection
    from infrastructure.persistence.schema_admin import check_target, resolve_via_fabric_api

    allowed = allowed_target(target_name)
    resolved = resolve_via_fabric_api(allowed.workspace_id, allowed.item_id, get_json=fabric_get_json)
    server = os.getenv("WAREHOUSE_SERVER", "")
    database = os.getenv("WAREHOUSE_DATABASE", "")
    check_target(allowed, resolved, server=server, database=database)
    if resolve_only:
        return allowed, resolved, None
    connection = FabricWarehouseConnection(server=server, database=database).open()
    connection.autocommit = True
    return allowed, resolved, connection


def check_lakehouse_endpoint(resolved, lakehouse_server: str, *, target: str = "deployed") -> None:
    """Refuse a lakehouse endpoint that is not on the guarded Warehouse's host.

    The guard proves the Warehouse is the allowed one; every item in a Fabric workspace shares
    one SQL endpoint host, so the same host proves the lakehouse is in the same workspace.
    """
    from infrastructure.persistence.schema_admin import TargetMismatch, _host

    if _host(lakehouse_server) != _host(resolved.endpoint):
        raise TargetMismatch(
            f"target '{target}' refused: LAKEHOUSE_SQL_SERVER {lakehouse_server!r} is not on the "
            f"guarded workspace's endpoint host {resolved.endpoint}"
        )


def guarded_lakehouse_connection(target_name: str):
    """Guard the Warehouse as usual, then open the lakehouse SQL analytics endpoint beside it."""
    from infrastructure.persistence.lakehouse_sql_connection import LakehouseSqlConnection

    allowed, resolved, _ = guarded_connection(target_name, resolve_only=True)
    lakehouse = LakehouseSqlConnection()
    lakehouse.require_configuration()
    check_lakehouse_endpoint(resolved, lakehouse.server, target=target_name)
    connection = lakehouse.open()
    connection.autocommit = True
    return allowed, resolved, connection
