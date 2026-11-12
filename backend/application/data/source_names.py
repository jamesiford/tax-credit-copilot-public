"""Where the source tables' physical names come from, as this package sees them. [06.6]

This package is pure and portable (stdlib and siblings only), so it cannot read the source mapping itself.
The composition root installs an implementation (`bootstrap/data_wiring.py` binds `data.source.mapping`),
and the lakehouse datasets in `model_source.py` ask here for every table and column name. A renamed column
therefore reaches the governed data-query model through the mapping and nothing in this package changes.

Nothing is installed by default: asking before the root has installed one is a named error, never a guess
at a name.
"""
from __future__ import annotations

from typing import Protocol


class SourceNames(Protocol):
    """What the lakehouse datasets need to know about the lake they describe."""

    def physical_table(self, logical: str) -> str: ...

    def column(self, logical_table: str, field: str) -> str: ...

    def tenant_column(self, logical_table: str) -> str: ...

    def null_pay_date_mode(self) -> str: ...


_installed: SourceNames | None = None


def install(names: SourceNames | None) -> None:
    """Bind (or, with None, unbind) the implementation. Called by the composition root and by tests."""
    global _installed
    _installed = names


def _names() -> SourceNames:
    if _installed is None:
        raise RuntimeError(
            "no source names installed: the composition root must call bootstrap.data_wiring.install_source_names() "
            "before the lakehouse datasets are built"
        )
    return _installed


def physical_table(logical: str) -> str:
    return _names().physical_table(logical)


def column(logical_table: str, field: str) -> str:
    return _names().column(logical_table, field)


def tenant_column(logical_table: str) -> str:
    return _names().tenant_column(logical_table)


def null_pay_date_mode() -> str:
    return _names().null_pay_date_mode()
