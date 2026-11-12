"""Check the source mapping against the lake at boot, and keep the verdict for `/api/ready`. [06.4]

`SOURCE_SCHEMA_VALIDATION`: `off` (skip), `warn` (default: log and report, in the background, never delaying
start) or `fail` (refuse to start on an error, checked before the first request). Only the lakehouse source is
checked; any other source has no lake to compare with.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from config import get_settings

log = logging.getLogger("tax-credit-copilot")


class SourceSchemaInvalid(RuntimeError):
    """`SOURCE_SCHEMA_VALIDATION=fail` and the lake does not match the mapping."""


def validate_lake(schemas: dict[str, Any] | None = None):
    """The report for the configured lakehouse (or for `schemas`, supplied by a test or the CLI)."""
    from data.source import mapping

    if schemas is None:
        from data.source.from_fabric import FabricLakehouseReader

        reader = FabricLakehouseReader()
        reader.require_configured()
        schemas = reader.actual_schemas()
    current = mapping.mapping()
    physical = {name: mapping.physical_table(name) for name in current.tables}
    return mapping.validate.validate(current, schemas, physical)


def _applies() -> bool:
    from tools.fabric_source import active_data_source

    return get_settings().source_model.validation != "off" and active_data_source() == "lakehouse"


def run_boot_check() -> dict[str, Any]:
    """The verdict as plain data; raises `SourceSchemaInvalid` under `fail` when it has errors."""
    if not _applies():
        return {"status": "skipped"}
    try:
        report = validate_lake()
    except Exception as exc:  # noqa: BLE001 - an unreachable lake is a finding, not a crash of the check itself
        log.warning("source schema check could not run: %s", type(exc).__name__)
        return {"status": "unknown", "detail": type(exc).__name__}
    verdict = report.summary()
    from data.lookups import lookup_status

    for row in lookup_status({"entity_fiscal_year_rules": any(t.logical == "EntityFiscalYearRules" and t.present for t in report.tables)}):
        log.info("lookup %s: %s (%s)", row["lookup"], row["status"], row["affects"])
    for message in verdict["errors"]:
        log.error("source schema: %s", message)
    for message in verdict["warnings"]:
        log.warning("source schema: %s", message)
    if verdict["errors"] and get_settings().source_model.validation == "fail":
        raise SourceSchemaInvalid("; ".join(verdict["errors"]))
    return verdict


async def check_source_schema(state: Any) -> None:
    """Run the boot check off the request path and leave the verdict on `state.source_schema`."""
    try:
        state.source_schema = await asyncio.to_thread(run_boot_check)
    except SourceSchemaInvalid as exc:
        state.source_schema = {"status": "error", "errors": [str(exc)]}
        raise


async def start_source_schema_check(state: Any) -> "asyncio.Task":
    """Begin the boot check as a background task; under `fail` wait for it, so a bad mapping stops startup."""
    state.source_schema = {"status": "running"}
    task = asyncio.ensure_future(check_source_schema(state))
    if get_settings().source_model.validation == "fail":
        await task
    return task
