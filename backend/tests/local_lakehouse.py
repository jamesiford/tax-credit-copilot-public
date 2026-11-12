"""A local Delta lakehouse for offline tests: real Delta tables on disk, laid out as OneLake lays them out.

`write_lakehouse(root, dataset, ...)` writes each source table of a `SourceDataset` under
`<root>/Tables/<schema>/<physical>` (or `<root>/Tables/<physical>` with no schema), honouring the
current `SOURCE_TABLE_*` settings, and `use_local_lakehouse(monkeypatch, root)` points the reader at it.
Nothing here touches the network or an Azure credential.
"""
from __future__ import annotations

from pathlib import Path

from data.source import from_fabric, onelake
from data.source.schema import SourceDataset
from data.source.to_delta import PARTITION_BY, TABLE_SPECS, _to_arrow


def write_lakehouse(root: Path, dataset: SourceDataset, *, schema: str = "dbo", skip: tuple[str, ...] = ()) -> dict[str, Path]:
    """Write every table except those in `skip`; returns logical table -> directory."""
    from deltalake import write_deltalake

    written: dict[str, Path] = {}
    for table in TABLE_SPECS:
        if table in skip:
            continue
        uri = onelake.table_uri(table, workspace="ws", lakehouse="lh", schema=schema)
        target = Path(root) / "Tables" / uri.split("/Tables/", 1)[1]
        write_deltalake(str(target), _to_arrow(dataset, table), partition_by=PARTITION_BY.get(table))
        written[table] = target
    return written


def use_local_lakehouse(monkeypatch, root: Path) -> None:
    """Make `FabricLakehouseReader` read `<root>/Tables/...` with no credential."""
    def local(table, *, workspace, lakehouse, schema):
        return str(Path(root) / "Tables" / onelake.table_uri(table, workspace=workspace, lakehouse=lakehouse, schema=schema).split("/Tables/", 1)[1])

    monkeypatch.setattr(from_fabric, "table_uri", local)
    monkeypatch.setattr(from_fabric.FabricLakehouseReader, "_storage_options", lambda self: {})
    from_fabric.clear_cache()
