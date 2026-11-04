"""A small vocabulary for writing the model's data compactly and uniformly. [CH-16a]

Roughly two hundred columns are described across the `model_*.py` modules. Without a
vocabulary each would restate the same defaults (what a measure may aggregate to, what a
text dimension may be filtered by), and the defaults would drift. `Cols` is the one place
those defaults live; a module overrides one only where the data genuinely differs, which
makes the exception visible.
"""
from __future__ import annotations

from application.data.semantic_model import Agg, ColType, Column, Op, Role, Sensitivity

_ALL_AGGS = frozenset(Agg)
_COUNTS = frozenset({Agg.COUNT, Agg.COUNT_DISTINCT})
_ORDERED = frozenset({Op.EQ, Op.IN, Op.BETWEEN, Op.GTE, Op.LTE})
_NUMERIC = (ColType.INT, ColType.DECIMAL)
_ORDERED_TYPES = (*_NUMERIC, ColType.DATE, ColType.DATETIME)


def pascal(name: str) -> str:
    """`pay_period_start` -> `PayPeriodStart`: the lakehouse's physical naming."""
    return "".join(part.capitalize() for part in name.split("_"))


def default_aggs(role: Role, type_: ColType) -> frozenset[Agg]:
    """What a column of this role and type may aggregate to unless the data says otherwise."""
    if role is Role.MEASURE:
        return _ALL_AGGS if type_ in _NUMERIC else frozenset({Agg.COUNT, Agg.MIN, Agg.MAX})
    if role is Role.FLAG:
        return frozenset({Agg.COUNT, Agg.SUM})
    if type_ in _ORDERED_TYPES:
        return _COUNTS | {Agg.MIN, Agg.MAX}
    return _COUNTS


def default_ops(role: Role, type_: ColType, free_text: bool) -> frozenset[Op]:
    """Which filters make sense: ordered types take ranges, text takes equality, flags one value."""
    if type_ is ColType.BOOL:
        return frozenset({Op.EQ})
    if type_ in _ORDERED_TYPES:
        return _ORDERED
    return frozenset({Op.EQ, Op.IN, Op.CONTAINS}) if free_text else frozenset({Op.EQ, Op.IN})


class Cols:
    """Builds `Column`s with the shared defaults; `pascal_physical` is for the lakehouse."""

    def __init__(self, *, pascal_physical: bool = False) -> None:
        self._pascal = pascal_physical

    def _make(self, logical, type_, description, role, emp, physical, **extra) -> Column:
        sens = Sensitivity.EMPLOYEE_LEVEL if emp else Sensitivity.PUBLIC_AGGREGATE
        free_text = extra.pop("free_text", False)
        aggs = extra.pop("aggs", None)
        ops = extra.pop("ops", None)
        name = physical or (pascal(logical) if self._pascal else logical)
        return Column(
            logical=logical, physical=name, type=ColType(type_), description=description,
            role=role, sensitivity=sens, free_text=free_text,
            aggregations=default_aggs(role, ColType(type_)) if aggs is None else frozenset(aggs),
            operators=default_ops(role, ColType(type_), free_text) if ops is None else frozenset(ops),
            **extra,
        )

    def dim(self, logical, type_, description, *, emp=False, physical=None, **extra) -> Column:
        """A column to slice by."""
        return self._make(logical, type_, description, Role.DIMENSION, emp, physical, **extra)

    def measure(self, logical, type_, description, *, emp=False, physical=None, **extra) -> Column:
        """A number to aggregate."""
        return self._make(logical, type_, description, Role.MEASURE, emp, physical, **extra)

    def flag(self, logical, description, *, emp=False, physical=None, **extra) -> Column:
        """A yes/no column."""
        return self._make(logical, "bool", description, Role.FLAG, emp, physical, **extra)

    def ident(self, logical, type_, description, *, emp=False, physical=None, **extra) -> Column:
        """A handle for a row or a person: countable, never summable."""
        return self._make(logical, type_, description, Role.IDENTIFIER, emp, physical, **extra)

    def blocked(self, logical, type_, description, *, physical=None) -> Column:
        """A column that exists in the table and must never be queried."""
        name = physical or (pascal(logical) if self._pascal else logical)
        return Column(
            logical=logical, physical=name, type=ColType(type_), description=description,
            role=Role.IDENTIFIER, sensitivity=Sensitivity.BLOCKED,
            aggregations=frozenset(), operators=frozenset(),
        )
