"""Resolve the caller's column names against the model, refusing what must not be touched. [CH-16b]

The caller writes `tax_year` or `location.location_name`. Resolution decides whether that
names a real, queryable column, and which table alias it lives on. It is the single choke
point for "unknown" and "blocked": nothing downstream accepts a column name that did not
pass through here. An unknown name is never echoed back, because it is the caller's text.
"""
from __future__ import annotations

import re

from application.data.errors import BlockedColumn, UnknownColumn
from application.data.plan import BASE_ALIAS, ColumnRef, JoinPlan
from application.data.semantic_model import Column, Dataset, SemanticModel

_REF = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}(\.[A-Za-z_][A-Za-z0-9_]{0,63})?\Z")  # \Z: `$` admits a trailing newline


class ColumnResolver:
    """Resolves references for one dataset, remembering which declared joins they used."""

    def __init__(self, dataset: Dataset, model: SemanticModel) -> None:
        self._dataset = dataset
        self._model = model
        self._used: dict[str, JoinPlan] = {}

    def resolve(self, ref: str, *, field: str) -> ColumnRef:
        """The queryable column `ref` names, or UnknownColumn / BlockedColumn."""
        if not isinstance(ref, str) or not _REF.match(ref):
            raise UnknownColumn("not a column name of this dataset", field=field)
        if "." in ref:
            return self._joined(ref, field)
        column = self._dataset.column(ref)
        return self._checked(ref, column, BASE_ALIAS, ref, field)

    def _joined(self, ref: str, field: str) -> ColumnRef:
        join_name, name = ref.split(".", 1)
        join = self._dataset.join(join_name)
        target = self._model.dataset(join.target) if join else None
        if join is None or target is None:
            raise UnknownColumn("no such join on this dataset", field=field)
        ref_obj = self._checked(ref, target.column(name), join_name, f"{join_name}__{name}", field)
        self._used[join_name] = JoinPlan(join, target)
        return ref_obj

    @staticmethod
    def _checked(ref: str, column: Column | None, alias: str, label: str, field: str) -> ColumnRef:
        if column is None:
            raise UnknownColumn("no such column in this dataset", field=field)
        if not column.queryable:
            raise BlockedColumn(f"{column.logical} is blocked: it is never selected, filtered or grouped", field=field)
        return ColumnRef(ref=ref, column=column, alias=alias, label=label)

    def joins_used(self) -> tuple[JoinPlan, ...]:
        """The declared joins the resolved columns need, in the dataset's declaration order."""
        return tuple(self._used[j.name] for j in self._dataset.joins if j.name in self._used)
