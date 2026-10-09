"""Canonical source-record interface (Part E · DATA-03/04/05/06).

The calc core must never care where payroll came from. This module defines the
**canonical source record** — one row per employee per pay period carrying full
dimensionality — and a thin ingestion interface behind which real data (the partner's
dummy set / a sanitized export from the partner) slots in without touching the engine.

Pipeline (all pure, deterministic):

    raw source rows
      -> map to CanonicalRecord            (adapter; DATA-03)
      -> attach worksite address / unit    (worksite join; DATA-04)
      -> classify includable pay codes      (per-client mapping; DATA-05)
      -> trim to fiscal year by PAY DATE     (cash-basis; DATA-06)
      -> collapse to one row per (employee, pay period)

The included/excluded pay-code lists come from the agent-INGESTED cited config
(tools/rules_ingestion.py) so the wage base is rules-driven, not hard-coded
(CALC-11). Runs on the mock pay-period CSV today; a new adapter is all it takes
to point at a real export.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Protocol

_PAY_PERIODS_CSV = Path(__file__).resolve().parent.parent / "data" / "payroll_pay_periods.csv"


# ---------------------------------------------------------------------------
# The canonical record (DATA-03)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CanonicalRecord:
    """One employee, one pay period — the grain every downstream calc needs.

    PII is intentionally minimal (surrogate ``employee_id`` only; DATA-10).
    ``worksite_address`` / ``unit_number`` are populated by the worksite join
    (DATA-04). ``pay_code``/``includable`` drive the wage-base filter (DATA-05).
    """
    tax_year: int
    employee_id: str
    worksite_id: str
    legal_entity_fein: str
    pay_frequency: str            # 'weekly' | 'biweekly' | ... (true-weeks basis)
    pay_period_start: date
    pay_period_end: date
    pay_date: date                # cash-basis fiscal-year anchor (DATA-06)
    hours_worked: float
    gross_wages: float
    pay_code: str = "Regular"
    job_title: str = ""
    # DATA-04 worksite/location join outputs:
    worksite_address: str | None = None
    unit_number: str | None = None
    # DATA-05 pay-code classification output:
    includable: bool = True


# ---------------------------------------------------------------------------
# Source adapter interface (swap the adapter to swap the source)
# ---------------------------------------------------------------------------


class SourceAdapter(Protocol):
    """Anything that can yield raw dict rows becomes a source. Real data slots
    in by implementing this — the engine never changes."""

    def rows(self) -> Iterable[dict[str, Any]]: ...


@dataclass
class PayPeriodCsvAdapter:
    """Adapter over the prototype BCS-shaped pay-period CSV."""
    path: Path = _PAY_PERIODS_CSV

    def rows(self) -> Iterable[dict[str, Any]]:
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        with self.path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out.append(r)
        return out


@dataclass
class RowsAdapter:
    """Rows a caller has already loaded.

    Without this a screen can read its first number from one source and the
    rest from another: `to_canonical` defaults to the local CSV, so a view
    showing a Fabric row count above a CSV-derived pipeline looks consistent
    and is not.
    """
    loaded: list[dict[str, Any]]

    def rows(self) -> Iterable[dict[str, Any]]:
        return self.loaded


# ---------------------------------------------------------------------------
# Worksite / location join (DATA-04) + pay-code frequency inference
# ---------------------------------------------------------------------------


def _worksite_join(worksite_id: str) -> dict[str, Any]:
    """Attach a worksite address + unit number. Worksites are static/reliable;
    the prototype derives a synthetic address from the sites registry when
    available, else a deterministic placeholder."""
    try:
        from data.sites import SITES  # type: ignore
        for s in SITES:
            if s.get("worksite_id") == worksite_id or s.get("id") == worksite_id:
                return {
                    "worksite_address": s.get("address") or f"{s.get('city', '')}, {s.get('state', '')}".strip(", "),
                    "unit_number": worksite_id,
                }
    except Exception:  # noqa: BLE001 — registry is optional
        pass
    return {"worksite_address": None, "unit_number": worksite_id}


def _infer_frequency(start: date, end: date) -> str:
    span = (end - start).days + 1
    if span <= 7:
        return "weekly"
    if span <= 14:
        return "biweekly"
    if span <= 16:
        return "semimonthly"
    return "monthly"


# ---------------------------------------------------------------------------
# Pay-code classification (DATA-05) — rules-driven via ingested config
# ---------------------------------------------------------------------------


def _pay_code_classifier(program: str) -> tuple[set[str] | None, set[str]]:
    """Return (included_codes | None, excluded_codes) from the ingested config.

    None included = include everything not explicitly excluded. Excluded wins.
    Falls back to a conservative default (strip common non-taxable codes) when
    no ingested config exists (CALC-11 / DATA-05).
    """
    try:
        from .rules_ingestion import load_ingested_config
        cfg = load_ingested_config(program)
        if cfg:
            wb = (cfg.get("parameters") or {}).get("wage_basis") or {}
            inc = wb.get("included_pay_codes")
            exc = wb.get("excluded_pay_codes") or []
            return (set(inc) if inc else None), set(exc)
    except Exception:  # noqa: BLE001
        pass
    return None, {"Mileage", "Expense_Reimbursement", "Relocation"}


def _is_includable(pay_code: str, included: set[str] | None, excluded: set[str]) -> bool:
    if pay_code in excluded:
        return False
    if included is None:
        return True
    return pay_code in included


# ---------------------------------------------------------------------------
# Ingestion entry point
# ---------------------------------------------------------------------------


def to_canonical(
    adapter: SourceAdapter | None = None,
    *,
    tax_year: int | None = None,
    program: str = "GA_JTC",
) -> list[CanonicalRecord]:
    """Map raw source rows to canonical records with the full DATA-03..06 pipeline.

    * ``tax_year`` — when set, cash-basis trim by PAY DATE (DATA-06): keep only
      rows whose pay date falls in that calendar year (wages count in the year
      PAID, not earned).
    * ``program`` — selects the pay-code classifier from the ingested config.
    """
    adapter = adapter or PayPeriodCsvAdapter()
    included, excluded = _pay_code_classifier(program)

    records: list[CanonicalRecord] = []
    for r in adapter.rows():
        try:
            pp_start = date.fromisoformat(str(r["Pay_Period_Start"])[:10])
            pp_end = date.fromisoformat(str(r["Pay_Period_End"])[:10])
            pay_date = date.fromisoformat(str(r["Pay_Date"])[:10])
        except (KeyError, ValueError):
            continue

        # DATA-06 cash-basis fiscal-year trim by pay date.
        if tax_year is not None and pay_date.year != tax_year:
            continue

        worksite_id = str(r.get("Worksite_ID", ""))
        join = _worksite_join(worksite_id)
        pay_code = str(r.get("Pay_Code", "Regular"))

        records.append(
            CanonicalRecord(
                tax_year=pay_date.year,  # DATA-06 cash-basis: fiscal year = year PAID, not earned
                employee_id=str(r.get("Employee_ID", "")),
                worksite_id=worksite_id,
                legal_entity_fein=str(r.get("Entity_FEIN", "")),
                pay_frequency=_infer_frequency(pp_start, pp_end),
                pay_period_start=pp_start,
                pay_period_end=pp_end,
                pay_date=pay_date,
                hours_worked=float(r.get("Hours_Worked", 0.0) or 0.0),
                gross_wages=float(r.get("Gross_Wages", 0.0) or 0.0),
                pay_code=pay_code,
                job_title=str(r.get("Job_Title", "")),
                worksite_address=join["worksite_address"],
                unit_number=join["unit_number"],
                includable=_is_includable(pay_code, included, excluded),
            )
        )
    return records


def collapse_to_employee_period(records: Iterable[CanonicalRecord]) -> list[dict[str, Any]]:
    """Collapse remaining includable lines to one record per (employee, pay period).

    Sums includable hours/wages; non-includable pay codes (e.g. mileage) are
    dropped from the wage base but their existence is not required downstream.
    Mirrors the partner's "collapse remaining lines to one record per employee per pay
    period" step (DATA-05).
    """
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for rec in records:
        if not rec.includable:
            continue
        key = (rec.employee_id, rec.worksite_id, rec.pay_period_end.isoformat())
        b = buckets.get(key)
        if b is None:
            b = {
                "tax_year": rec.tax_year,
                "employee_id": rec.employee_id,
                "worksite_id": rec.worksite_id,
                "legal_entity_fein": rec.legal_entity_fein,
                "pay_frequency": rec.pay_frequency,
                "pay_period_start": rec.pay_period_start.isoformat(),
                "pay_period_end": rec.pay_period_end.isoformat(),
                "pay_date": rec.pay_date.isoformat(),
                "hours_worked": 0.0,
                "gross_wages": 0.0,
            }
            buckets[key] = b
        b["hours_worked"] = round(b["hours_worked"] + rec.hours_worked, 2)
        b["gross_wages"] = round(b["gross_wages"] + rec.gross_wages, 2)
    return list(buckets.values())
