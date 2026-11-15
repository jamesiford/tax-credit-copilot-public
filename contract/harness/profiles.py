"""The two data profiles. See `world.py` for what each is."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .world import World, _wire_gold

#: Years the engine is replayed for, per synthetic client in P2 (the write path covers every authored year in one call).
P2_RUN_YEAR = 2025


def _lakehouse(work: Path, datasets: list[Any]) -> Path:
    """Write every dataset's source tables into one local Delta lakehouse, tenants concatenated per table.

    `tests/local_lakehouse.write_lakehouse` writes one dataset; the product's own `write_datasets` concatenates tenants per table
    but targets OneLake. This is the same layout with the same Arrow builder, on disk.
    """
    import pyarrow as pa
    from deltalake import write_deltalake

    from data.source import onelake
    from data.source.to_delta import PARTITION_BY, TABLE_SPECS, _to_arrow

    root = work / "lakehouse"
    for table in TABLE_SPECS:
        parts = [_to_arrow(ds, table) for ds in datasets]
        combined = pa.concat_tables(parts) if len(parts) > 1 else parts[0]
        uri = onelake.table_uri(table, workspace="ws", lakehouse="lh", schema="tcc_source")
        target = root / "Tables" / uri.split("/Tables/", 1)[1]
        write_deltalake(str(target), combined, partition_by=PARTITION_BY.get(table))
    return root


def _point_reader_at(root: Path) -> None:
    from pytest import MonkeyPatch

    from tests.local_lakehouse import use_local_lakehouse

    patch = MonkeyPatch()  # kept for the life of the process: the world is built once and never torn down
    use_local_lakehouse(patch, root)
    patch.setattr("infrastructure.persistence.source_sql.SourceSqlReader.is_configured", lambda self: False)
    for name, value in (("DATA_SOURCE", "lakehouse"), ("FABRIC_WORKSPACE", "ws"), ("FABRIC_LAKEHOUSE", "lh"), ("PAY_CODE_POLICY", "assume")):
        os.environ[name] = value
    from data.source import from_fabric

    from_fabric.clear_cache()


def _p1(work: Path) -> World:
    from bootstrap import wiring
    from tests.data_engine_fixture import SqliteWarehouse, run_engine

    warehouse = SqliteWarehouse()
    run_engine(warehouse, work, claims=wiring.get_claim_repository())
    _wire_gold(warehouse)
    import main

    return World("P1", work, warehouse, main.app, {"client": 1001, "year": 2025})


def _p2(work: Path) -> World:
    from application.commands.run_client_calculation import RunClientCalculationCommand
    from bootstrap import wiring
    from data.source.synth import SYNTHETIC_CLIENTS, build_synthetic_dataset
    from tests.data_engine_fixture import SqliteWarehouse

    datasets = [build_synthetic_dataset(spec) for spec in SYNTHETIC_CLIENTS]
    _point_reader_at(_lakehouse(work, datasets))
    warehouse = SqliteWarehouse()
    _wire_gold(warehouse)
    mediator = wiring.get_mediator()
    runs = []
    for spec in SYNTHETIC_CLIENTS:
        result = mediator.send(RunClientCalculationCommand(client_id=spec.account_id, tax_year=P2_RUN_YEAR, state=spec.states[0], actor="contract-seed"))
        runs.append({"client": spec.account_id, "state": spec.states[0], "run_id": result.get("run_id") if isinstance(result, dict) else None})
    import main

    return World("P2", work, warehouse, main.app, {"clients": [s.account_id for s in SYNTHETIC_CLIENTS], "year": P2_RUN_YEAR, "runs": runs})


def build(profile: str, work: Path) -> World:
    if profile == "G1":
        from . import gateway

        return gateway.build(work)
    return {"P1": _p1, "P2": _p2}[profile](work)
