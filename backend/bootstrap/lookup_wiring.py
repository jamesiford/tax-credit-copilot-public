"""Binds the lookup override store (`LOOKUP_STORE`): none, SQLite, or the Warehouse. [07]

The store is built lazily, on first use, so importing this never opens a connection. `none` (the default) leaves the
override layer empty: the resolver then uses the seed, or, under the `strict` policy, reports what is missing.
"""
from __future__ import annotations

from typing import Any

from config import get_settings
from data.lookups import store


class _LazyStore:
    """Defers building the adapter until a lookup is actually resolved."""

    def __init__(self) -> None:
        self._inner: Any = None

    def _store(self) -> Any:
        kind = get_settings().source_model.lookup_store
        if kind == "none":
            return _NoStore()
        if self._inner is None:
            if kind == "warehouse":
                from infrastructure.persistence.warehouse_lookups import WarehouseLookupStore

                self._inner = WarehouseLookupStore()
            else:
                from infrastructure.persistence.sqlite_lookups import SqliteLookupStore

                self._inner = SqliteLookupStore()
        return self._inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store(), name)


class _NoStore:
    """`LOOKUP_STORE=none`: reads are empty, writes are refused with the setting to change."""

    def entries(self, lookup: str, client_id: int) -> list:
        return []

    def audit(self, lookup: str | None = None) -> list:
        return []

    def put(self, entry: Any) -> None:
        raise RuntimeError("LOOKUP_STORE=none: set LOOKUP_STORE=sqlite (local) or warehouse before authoring overrides")

    remove = put


def install_lookup_store() -> None:
    """Bind the store the settings choose. A test that wants another calls `data.lookups.store.install`."""
    store.install(_LazyStore())


def lookup_store_selected() -> bool:
    return get_settings().source_model.lookup_store != "none"
