"""Is the operational store usable, and if not, what is the first thing to do? [03.7]

Claims, engagements, findings and run manifests live in the operational store (`tcc_ops`). Nothing
copies them anywhere else, so when it is unreachable, never initialised, or behind its migrations the
right answer is to say so, with the remedy, instead of letting a page render as "no claims yet".

The check itself is an adapter (`infrastructure/persistence/store_probe.py`), reached through
`application.services.get_store_probe`. What lives here is the vocabulary and the part that needs no
database: settings that are probably mistakes (a placeholder host left in `.env`, SQLite claims while
a warehouse is configured).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Finding:
    """One thing wrong or suspicious. `problem` stops the store being used; `warning` does not."""

    code: str
    message: str
    remedy: str
    severity: str = "problem"

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity, "message": self.message, "remedy": self.remedy}


class StoreProbe(Protocol):
    """What the readiness check needs of an adapter: its findings, given the migration files if known."""

    def probe(self, available_migrations: list[Any] | None = None) -> list[Finding]: ...


_PLACEHOLDER_MARKERS = ("<", ">", "your-", "example", "changeme", "xxxx", "todo")


def looks_like_placeholder(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return bool(lowered) and any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def settings_findings(environ: Mapping[str, str] | None = None) -> list[Finding]:
    """Warnings that need no connection: a setting that is almost certainly not what was meant."""
    from application.deployment import store_choice
    from config import resolve_environ

    env = resolve_environ(environ)
    out: list[Finding] = []
    if "SOURCE_SCHEMA" in env and not (env["SOURCE_SCHEMA"] or "").strip():
        out.append(Finding(
            "source_schema_blank",
            "SOURCE_SCHEMA is blank: treating the lakehouse as not schema-enabled (Tables/<table>).",
            "If the lakehouse is schema-enabled set SOURCE_SCHEMA=dbo (or its schema name); remove the line to use the "
            "default schema. `python scripts/check-onelake-access.py --probe-layout` tells you which layout opens the table.",
            "warning",
        ))
    for name in ("WAREHOUSE_SERVER", "WAREHOUSE_DATABASE", "LAKEHOUSE_SQL_SERVER", "FABRIC_WORKSPACE", "FABRIC_LAKEHOUSE"):
        if looks_like_placeholder(env.get(name, "")):
            out.append(Finding(
                "placeholder_setting", f"{name} looks like a placeholder ({env[name]!r}).",
                f"Set {name} to the real value, or remove the line so nothing tries to connect to it.", "warning",
            ))
    if (env.get("WAREHOUSE_SERVER") or "").strip():
        for name in ("CLAIM_STORE", "FINDING_STORE", "RUN_MANIFEST_STORE"):
            choice = store_choice(name, env)
            if choice != "warehouse":
                out.append(Finding(
                    "mixed_store_settings",
                    f"{name} is {choice!r} while a warehouse is configured (WAREHOUSE_SERVER is set).",
                    f"Set {name}=warehouse to record in the warehouse, or leave WAREHOUSE_SERVER unset for a local-only run. "
                    "Records written to a local store do not reach the warehouse and do not survive a redeploy.",
                    "warning",
                ))
    return out


def check_operational_store(available_migrations: list[Any] | None = None) -> dict[str, Any]:
    """The store's readiness: `{status, problems, warnings}`. `ready` means no problem was found.

    `available_migrations` (the migration files, which only a script may read) additionally reports a
    store that is behind them.
    """
    from application.services import get_store_probe

    findings = settings_findings()
    try:
        findings = get_store_probe().probe(available_migrations) + findings
    except Exception as exc:  # noqa: BLE001 - a probe that crashes is itself a finding, not a crash of the probe endpoint
        findings.insert(0, Finding(
            "probe_failed", f"the readiness check itself failed ({type(exc).__name__}).",
            "See the application log; the store may still be usable.", "warning",
        ))
    problems = [f.as_dict() for f in findings if f.severity == "problem"]
    warnings = [f.as_dict() for f in findings if f.severity != "problem"]
    return {"status": "degraded" if problems else "ready", "problems": problems, "warnings": warnings}
