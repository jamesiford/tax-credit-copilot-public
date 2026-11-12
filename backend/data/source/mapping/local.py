"""Read table schemas from a lakehouse laid out on local disk (a sample lake, a test lake). [06.4, 05]

Same layout OneLake presents: `<root>/Tables/<schema>/<physical table>` (or `<root>/Tables/<physical table>`
when the lake has no schema). Only each table's Delta log is opened; no data is read.
"""
from __future__ import annotations

from pathlib import Path

from .resolver import mapping, physical_table


def local_schemas(root: str | Path, schema: str = "") -> dict[str, dict[str, str] | None]:
    """logical table -> {column: Delta type}, or None where the table directory is absent."""
    from deltalake import DeltaTable
    from deltalake.exceptions import TableNotFoundError

    base = Path(root) / "Tables" / schema if schema else Path(root) / "Tables"
    out: dict[str, dict[str, str] | None] = {}
    for logical in mapping().tables:
        target = base / physical_table(logical)
        try:
            fields = DeltaTable(str(target)).schema().fields
            out[logical] = {f.name: str(getattr(f.type, "type", f.type)) for f in fields}
        except TableNotFoundError:
            out[logical] = None
    return out
