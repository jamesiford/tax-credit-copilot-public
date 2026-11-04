"""Reading which run a live-run result came from. [CH-16c]

A Gold row set is only meaningful with the run behind it: the statute pack and the assumption
sets it applied. The builder already pins live-run datasets to the client's latest successful,
unsuperseded run through a subquery, so the run's identity is read the same way, through the
same validated builder over the `run_manifest` dataset: no second hand-written statement.

It is read AFTER the data and never cached. A cache could name a run that a rerun replaced
between the two reads, and provenance that names the wrong run is worse than none; the cost is
one tiny indexed read per data query. If a rerun lands in the milliseconds between the two
reads the provenance can name the previous run, and the result then still carries its own rows.
"""
from __future__ import annotations

from collections.abc import Callable

from application.data.build import BuiltQuery, build_query
from application.data.dialect import Dialect, SchemaNames
from application.data.executor import Rows
from application.data.provenance import LiveRun
from application.data.semantic_model import SemanticModel
from application.data.spec import FilterSpec, OrderSpec, QuerySpec

_COLUMNS = (
    "run_id", "rule_pack_version", "step1_assumption_set_id", "onezero_assumption_set_id",
    "run_completed_at", "run_started_at", "superseded_by_run_id",
)
#: Enough recent runs that a few superseded ones cannot hide the live one.
_RECENT = 20


def live_run_query(client_id: int, model: SemanticModel, dialect: Dialect, schemas: SchemaNames) -> BuiltQuery:
    """The recent successful runs for a client, newest first, as a validated built statement."""
    spec = QuerySpec(
        dataset="run_manifest", client_id=client_id, select=_COLUMNS,
        filters=(FilterSpec("run_status", "eq", "success"),),
        order_by=(OrderSpec("run_started_at", "desc"),), limit=_RECENT,
    )
    return build_query(spec, model, dialect, schemas)


def pick_live_run(rows: Rows) -> LiveRun | None:
    """The newest run that completed and was not superseded: the builder's own definition of live."""
    index = {name: i for i, name in enumerate(rows.columns)}
    for row in rows.rows:
        if row[index["superseded_by_run_id"]] is None and row[index["run_completed_at"]] is not None:
            return LiveRun(
                run_id=str(row[index["run_id"]]),
                rule_pack_version=_text(row, index["rule_pack_version"]),
                step1_assumption_set_id=_text(row, index["step1_assumption_set_id"]),
                onezero_assumption_set_id=_text(row, index["onezero_assumption_set_id"]),
                completed_at=_text(row, index["run_completed_at"]),
            )
    return None


def read_live_run(
    client_id: int, model: SemanticModel, dialect: Dialect, schemas: SchemaNames,
    run: Callable[[BuiltQuery, int], Rows],
) -> LiveRun | None:
    """The client's live run, using `run(built, max_rows)` to execute the lookup."""
    built = live_run_query(client_id, model, dialect, schemas)
    return pick_live_run(run(built, _RECENT))


def _text(row: tuple, position: int) -> str | None:
    return None if row[position] is None else str(row[position])
