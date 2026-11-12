"""The override layer: app-owned lookup rows in the operational store. [07]

Rows are per client (`client_id` = the account) or global (`client_id` = 0, the sentinel), effective-dated, and carry
who authored them, when, why and whether they are inferred. Every write also appends an audit row. The store is a
port: SQLite for local runs and tests, the Warehouse (`tcc_ops.lookup_override` / `lookup_audit`, migration 0003)
when deployed. With no store installed the override layer is simply empty.

Per-client rows are tenant-bound through `tenant_sql` in the Warehouse adapter; global rows use the sentinel client
so one scoped statement reads both.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

GLOBAL_CLIENT = 0
KEY_KINDS = ("code", "category", "rule")


@dataclass(frozen=True)
class OverrideEntry:
    """One authored lookup row."""

    lookup: str
    client_id: int          # GLOBAL_CLIENT (0) for a global row
    key_kind: str           # code | category | rule
    key: str
    value: str              # canonical category, or a JSON object for `rule`
    authored_by: str
    basis: str = ""
    inferred: bool = False
    effective_from: date | None = None
    effective_to: date | None = None

    def active_on(self, day: date) -> bool:
        return (self.effective_from is None or self.effective_from <= day) and (self.effective_to is None or day <= self.effective_to)


class LookupOverrideStore(Protocol):
    """Where overrides live."""

    def entries(self, lookup: str, client_id: int) -> list[OverrideEntry]:
        """Live rows for this client AND the global rows, most specific first is the caller's job."""

    def put(self, entry: OverrideEntry) -> None:
        """Supersede any live row with the same key and insert this one; append an audit row."""

    def remove(self, lookup: str, client_id: int, key_kind: str, key: str, actor: str) -> bool:
        """Close the live row (never delete it); append an audit row. False if there was none."""

    def audit(self, lookup: str | None = None) -> list[dict]:
        """The audit trail, oldest first."""


_installed: LookupOverrideStore | None = None


def install(store: LookupOverrideStore | None) -> None:
    """Bind (or unbind) the store. Called by the composition root and by tests."""
    global _installed
    _installed = store


def get_store() -> LookupOverrideStore | None:
    return _installed
