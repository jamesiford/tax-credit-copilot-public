"""The data-query service, composed. [CH-16c]

Its own composition module, like `channel_wiring`, because the capabilities that call it
(CH-16d) run in the API process and the gateway must never load it: composing through
`application.wiring` would pull every query and command into whatever imports it. The
persistence adapters are imported inside the builder, only for the sources that are configured.

Settings (all non-secret; none required — absent means the defaults below):

- `DATA_QUERY_TIMEOUT_SECONDS` (20) — statement time limit; a query past it is `query_timeout`.
- `DATA_QUERY_MAX_ROWS` (500) — the server's row cap; it can only lower a specification's own limit.
- `DATA_QUERY_RATE_PER_MINUTE` (30) — per-person budget, refused (not queued) beyond it.
- `DATA_QUERY_MAX_CONCURRENCY` (4) — data queries in flight at once, across all people.
- `DATA_MIN_GROUP_SIZE` (5, never below 2) — the smallest group of people an aggregate over employee-level
  data may show; smaller groups are left out and counted (`small_groups.py`). Not mapped in Terraform: it is a
  privacy floor, so the code default is the deployed value unless an operator raises it by hand.
- `DATA_QUERY_SOURCE_ENABLED` (false) — switches ON the lakehouse source datasets (raw payroll);
  the Gold and ops datasets in the Warehouse are not behind it. Enabled by deployment, not by code.
- `LAKEHOUSE_SQL_SERVER` / `LAKEHOUSE_SQL_DATABASE` — the lakehouse SQL analytics endpoint
  (default: `WAREHOUSE_SERVER` / `FABRIC_LAKEHOUSE`), see `lakehouse_sql_connection`.
- `DATA_QUERY_SQLITE_DIR` — local runs only: a folder of `<schema>.db` files for the SQLite adapter.

Executor choice: the Warehouse where `WAREHOUSE_SERVER` and `WAREHOUSE_DATABASE` are set, SQLite
for a local `DATA_QUERY_SQLITE_DIR`, otherwise no executor, so a query is a typed
`data_source_unavailable`; there is never a silent fall back to another store.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from application.data.dialect import SchemaNames
from application.data.limits import (
    DEFAULT_MAX_CONCURRENCY, DEFAULT_RATE_PER_MINUTE, DEFAULT_TIMEOUT_S, QueryLimits,
)
from application.data.semantic_model import Source, default_model
from application.data.service import DataQueryService
from application.data.small_groups import DEFAULT_MIN_GROUP_SIZE, MIN_GROUP_SIZE_FLOOR
from application.data.spec import MAX_LIMIT
from application.rate_limit import RateLimiter

_TRUE = frozenset({"1", "true", "yes", "on"})
_service: DataQueryService | None = None


def _number(environ: Mapping[str, str], name: str, default: float, low: float, high: float) -> float:
    """A setting clamped to a sane range; an unparseable value is the default, not a crash at startup."""
    try:
        return min(high, max(low, float(environ.get(name, "") or default)))
    except ValueError:
        return default


def source_enabled(environ: Mapping[str, str] = os.environ) -> bool:
    """`DATA_QUERY_SOURCE_ENABLED`, false unless set to a truthy value."""
    return (environ.get("DATA_QUERY_SOURCE_ENABLED") or "").strip().lower() in _TRUE


def limits_from_env(environ: Mapping[str, str] = os.environ) -> QueryLimits:
    """The timeout, row cap, concurrency and group floor from settings, each clamped into its allowed range.

    `DATA_MIN_GROUP_SIZE` (5) can raise the smallest group a result may show but never lower it below 2:
    a smaller value is read as 2, not as "off".
    """
    return QueryLimits(
        timeout_s=_number(environ, "DATA_QUERY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_S, 1, 120),
        hard_max_rows=int(_number(environ, "DATA_QUERY_MAX_ROWS", MAX_LIMIT, 1, MAX_LIMIT)),
        max_concurrency=int(_number(environ, "DATA_QUERY_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY, 1, 16)),
        min_group_size=int(_number(environ, "DATA_MIN_GROUP_SIZE", DEFAULT_MIN_GROUP_SIZE, MIN_GROUP_SIZE_FLOOR, 1000)),
    )


def schemas_from_config() -> SchemaNames:
    """The deployed schema names, from the same configuration the Warehouse adapters use."""
    from config import GOLD_SCHEMA, OPS_SCHEMA, SOURCE_SCHEMA

    return SchemaNames(gold=GOLD_SCHEMA, ops=OPS_SCHEMA, source=SOURCE_SCHEMA)


def build_executors(environ: Mapping[str, str], schemas: SchemaNames) -> dict[Source, Any]:
    """One executor per configured source; the lakehouse only when its flag is on."""
    executors: dict[Source, Any] = {}
    if environ.get("WAREHOUSE_SERVER") and environ.get("WAREHOUSE_DATABASE"):
        from infrastructure.persistence.warehouse_data_query import WarehouseDataQueryExecutor

        executors[Source.WAREHOUSE] = WarehouseDataQueryExecutor()
    elif environ.get("DATA_QUERY_SQLITE_DIR"):
        from infrastructure.persistence.sqlite_data_query import SqliteDataQueryExecutor
        from infrastructure.persistence.sqlite_data_source import open_attached

        local = SqliteDataQueryExecutor(open_attached(environ["DATA_QUERY_SQLITE_DIR"], schemas))
        executors = {Source.WAREHOUSE: local, Source.LAKEHOUSE: local}
    if source_enabled(environ) and Source.LAKEHOUSE not in executors:
        from infrastructure.persistence.lakehouse_data_query import LakehouseDataQueryExecutor

        executors[Source.LAKEHOUSE] = LakehouseDataQueryExecutor()
    return executors


def build_data_query_service(environ: Mapping[str, str] = os.environ) -> DataQueryService:
    """A service from settings. Separate from the cached getter so tests can build one from a dict."""
    schemas = schemas_from_config()
    rate = int(_number(environ, "DATA_QUERY_RATE_PER_MINUTE", DEFAULT_RATE_PER_MINUTE, 1, 600))
    disabled = () if source_enabled(environ) else (Source.LAKEHOUSE,)
    return DataQueryService(
        default_model(), build_executors(environ, schemas), limits=limits_from_env(environ),
        budget=RateLimiter(rate), schemas=schemas, disabled=disabled,
    )


def get_data_query_service() -> DataQueryService:
    """The process's data-query service, built on first use."""
    global _service
    if _service is None:
        _service = build_data_query_service()
    return _service


def set_data_query_service(service: DataQueryService | None) -> None:
    """Replace (or, with None, clear) the service: for tests and for a different composition."""
    global _service
    _service = service
