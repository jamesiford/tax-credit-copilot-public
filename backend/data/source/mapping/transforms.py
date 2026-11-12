"""Named transforms: the few places where a mapping needs a MEANING, not just a name. [06.5]

A mapping can say "the pay date lives in `PaycheckDate`". It cannot say what to do when that value is
missing, or which of two location columns is the worksite: those are decisions about statute-affecting
meaning, so each is a named, tested choice that a mapping (or a setting) selects by name and that has a
Python form and, where the SQL fast path needs it, an identical SQL form. Both forms are tested against
each other. An unknown name is refused at load.

`worksite_location`  which location a payroll row's jobs are counted at (open question Q3 for the partner):
  `worksite_then_location` the worksite where the source supplies one, else the row's location (default)
  `location_only`          always the row's location
  `worksite_only`          the worksite only; a row with none has no worksite and is counted as unplaced

`null_pay_date`      what a payroll row with no paycheck date does (nullable in the customer DDL):
  `period_end`  its pay-period end stands in, the row is counted and flagged as imputed (default)
  `exclude`     the row is left out of the projection and is counted as excluded
Neither is silent: the projection controls report how many rows each policy touched.
"""
from __future__ import annotations

from datetime import date
from typing import Any

WORKSITE_MODES = ("worksite_then_location", "location_only", "worksite_only")
NULL_PAY_DATE_MODES = ("period_end", "exclude")


def check(kind: str, name: str) -> str:
    allowed = WORKSITE_MODES if kind == "worksite_location" else NULL_PAY_DATE_MODES
    if name not in allowed:
        raise ValueError(f"unknown {kind} transform {name!r}; one of {', '.join(allowed)}")
    return name


def worksite_id(mode: str, worksite: Any, location: Any) -> Any:
    """The location a row is counted at under `mode`; None means the row has no placeable worksite."""
    if mode == "location_only":
        return location
    if mode == "worksite_only":
        return worksite
    return worksite or location


def worksite_sql(mode: str, worksite_ref: str, location_ref: str) -> str:
    """The SQL twin of `worksite_id`, over already-quoted column references."""
    if mode == "location_only":
        return location_ref
    if mode == "worksite_only":
        return worksite_ref
    return f"COALESCE({worksite_ref}, {location_ref})"


def effective_pay_date(mode: str, pay_date: date | None, period_end: date | None) -> date | None:
    """The date a row is paid under `mode`; None means the row is excluded."""
    if pay_date is not None:
        return pay_date
    return period_end if mode == "period_end" else None


def pay_date_sql(mode: str, pay_date_ref: str, period_end_ref: str) -> str:
    """The SQL twin of `effective_pay_date` (NULL where the row is excluded)."""
    return f"COALESCE({pay_date_ref}, {period_end_ref})" if mode == "period_end" else pay_date_ref
