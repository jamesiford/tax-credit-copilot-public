"""The source schema -> Silver Record Layout. The Silver projection.

This is the transformation the customer's real feed will go through: their
source tables in, the shape the certified engine reads out. Writing it against
a source-shaped copy of the reference dataset means it is tested before the
real feed arrives rather than after.

What this deliberately does NOT do
----------------------------------
No fiscal-window trim, no short-period filter, no collapse. Those are BA-01,
BA-02, BA-12 and BA-04 — statutory rules that belong to the certified engine.
A projection that quietly pre-filtered would move the numbers and hide why.

Silver holds every in-scope row. The engine decides what counts.
"""
from __future__ import annotations

import logging
from typing import Any

from . import mapping
from .mapping import transforms
from .schema import SourceDataset

log = logging.getLogger(__name__)

# BA-03. The source PayFrequencyId is a surrogate key whose lookup the partner has
# not supplied. It is carried through as lineage and never used as a multiplier
# — the engine measures each period's actual span instead.
_UNKNOWN_FREQUENCY = ""

# BA-07 / Q5. Pay-code inclusion is an app-owned lookup (`data/lookups`): the customer's `PayCode.PayCode` is a
# client-specific string ("REG" in one account, "RG01" in another) and the rule packs name canonical categories
# (`Regular`, `Overtime`, ... and the suppressed `Mileage`, `Expense_Reimbursement`, `Relocation`). An unmapped code
# is dropped by `apply_pay_code_policy` BEFORE the calculation runs, so the engine silently sees no payroll, which is
# how the first source-backed call returned 9,832 rows loaded and zero eligible. So every code is resolved through
# `resolve_pay_codes`, what could not be mapped is counted, and under `strict` it blocks the calculation.


def canonical_pay_code(source_code: str | None) -> str:
    """Seed-only mapping of one client pay code, kept for callers that have no account: the code itself when unmapped.

    The projection does not use this: it resolves per account (override, then seed) with the policy applied.
    """
    from data.lookups.seeds import load_seed

    if not source_code:
        return "Regular"
    code = source_code.strip()
    seed = load_seed("pay_code_category")
    return seed.entries.get(code.upper(), code) if seed else code


def frequency_label(start, end) -> str:
    """The pay frequency, read from the period's measured span (BA-03), never from the source's surrogate id."""
    days = (end - start).days + 1
    for limit, label in ((1, "daily"), (8, "weekly"), (14, "biweekly"), (16, "semimonthly"), (31, "monthly")):
        if days <= limit and days >= {1: 1, 8: 5, 14: 13, 16: 15, 31: 27}[limit]:
            return label
    return f"{days}d"


class _Context:
    """The lookups one account's projection needs, built once."""

    def __init__(self, dataset: SourceDataset, resolve: bool = True) -> None:
        from data.lookups import PayCodeReport, resolve_pay_codes

        self.fein = {e.entity_id: (e.federal_tax_id or "") for e in dataset.entities}
        self.title = {e.employee_id: (e.job_title or "") for e in dataset.employments}
        self.code_text = {c.pay_code_id: c.pay_code for c in dataset.pay_codes}
        self.resolve = resolve
        self.canonical, self.pay_code_report = resolve_pay_codes(dataset) if resolve else ({}, PayCodeReport("deferred"))
        self.unit, self.state, self.county = _location_dimensions(dataset)
        self.worksite_mode, self.pay_date_mode = mapping.worksite_mode(), mapping.null_pay_date_mode()

    def pay_code(self, pay_code_id: Any) -> tuple[str, bool, bool]:
        """(canonical code, unmapped, defaulted): an absent or dangling id is `Regular` and says so; an unmapped code passes through."""
        if not self.resolve:  # Silver: the pay code stays as the customer wrote it; the lookup is applied on read
            known = pay_code_id is not None and pay_code_id in self.code_text
            return ((self.code_text[pay_code_id] or "").strip(), False, False) if known else ("Regular", False, True)
        if pay_code_id is None or pay_code_id not in self.canonical:
            return "Regular", False, True
        found = self.canonical[pay_code_id]
        return (found, False, False) if found is not None else ((self.code_text.get(pay_code_id) or "").strip(), True, False)


def _location_dimensions(dataset: SourceDataset) -> tuple[dict[int, str], dict[int, str], dict[int, str]]:
    """Unit id, state and county per location, through Location -> Address -> StateCountyZip.

    The same join reaches `county_name`, which Georgia's tier (and so credit value) depends on. The unit id carries
    its state as a prefix because the pipeline filters per state by worksite prefix; without it every state filter
    returns empty and the calculation silently produces nothing.
    """
    address_by_id = {a.address_id: a for a in dataset.addresses}
    scz_by_id = {s.state_county_zip_id: s for s in dataset.state_county_zips}
    unit_of: dict[int, str] = {}
    state_of: dict[int, str] = {}
    county_of: dict[int, str] = {}
    for loc in dataset.locations:
        address = address_by_id.get(loc.address_id)
        scz = scz_by_id.get(address.state_county_zip_id) if address else None
        state = ((scz.state_abbr if scz else None) or (address.state_original if address else "") or "").upper()
        # Prefer the client's own identifier: it is what appears on their reports.
        raw_unit = loc.client_location_id or str(loc.location_id)
        unit_of[loc.location_id] = raw_unit if not state or raw_unit.startswith(f"{state}_") else f"{state}_{raw_unit}"
        state_of[loc.location_id] = state
        county_of[loc.location_id] = scz.county_name if scz else ""
    return unit_of, state_of, county_of


def _bcs_row(p: Any, paid: Any, ctx: _Context) -> dict[str, Any]:
    """One payroll row in the Silver Record Layout."""
    # Q3: which location the jobs are counted at is the `worksite_location` transform.
    location_id = transforms.worksite_id(ctx.worksite_mode, p.worksite_location_id, p.location_id)
    pay_code, unmapped, defaulted = ctx.pay_code(p.pay_code_id)
    return {
        # BA-02 trims on paycheck date; tax year is derived downstream from the fiscal window.
        "Tax_Year": paid.year,
        "Employee_ID": str(p.employee_id),
        "Job_Title": ctx.title.get(p.employee_id, ""),
        "Worksite_ID": ctx.unit.get(location_id, str(location_id)),
        "Work_State": ctx.state.get(location_id, ""),
        "Work_County": ctx.county.get(location_id, ""),
        "Entity_FEIN": ctx.fein.get(p.entity_id, ""),
        "Pay_Period_Start": p.pay_period_start.isoformat(),
        "Pay_Period_End": p.pay_period_end.isoformat(),
        # Q1: nullable in source. The `null_pay_date` transform decides (period end stands in, or the row is
        # excluded before this); an imputed date is flagged on the row and counted in the controls.
        "Pay_Date": paid.isoformat(),
        "_Pay_Date_Imputed": p.pay_date is None,
        # BA-03: the label is derived from the measured span; the raw id is lineage only.
        "Pay_Frequency": frequency_label(p.pay_period_start, p.pay_period_end),
        "_Source_Pay_Frequency_Id": p.pay_frequency_id,
        # BA-07: the canonical category the rule pack names. The source code is kept as lineage, and a code no
        # provider maps (or a row with no pay code) is flagged on the row, never absorbed.
        "Pay_Code": pay_code,
        "_Source_Pay_Code": ctx.code_text.get(p.pay_code_id, ""),
        "_Pay_Code_Unmapped": unmapped,
        "_Pay_Code_Defaulted": defaulted,
        # Q2: NULL and 0 differ. NULL coerces to 0.0 so BA-05 keeps the row, and the count is reported separately.
        "Hours_Worked": float(p.hours) if p.hours is not None else 0.0,
        "Gross_Wages": float(p.wages) if p.wages is not None else 0.0,
        "_Source_Payroll_Id": p.payroll_id,
        "_Source_Account_Id": p.account_id,
    }


def source_to_bcs_rows(dataset: SourceDataset, *, resolve_pay_codes: bool = True) -> list[dict[str, Any]]:
    """Project one client's source tables into Silver Record Layout rows.

    Returns plain dicts. The engine is pure functions over lists of dicts (ADR-003), so nothing about the
    Warehouse, Fabric or Delta reaches it. Under the `strict` pay-code policy, payroll carrying pay codes no
    provider maps raises `UnmappedPayCodes` rather than projecting rows the state's whitelist would silently drop.
    """
    ctx = _Context(dataset, resolve_pay_codes)
    report = ctx.pay_code_report
    if report.policy == "strict" and report.unmapped_rows:
        from application.errors import UnmappedPayCodes

        raise UnmappedPayCodes(report.unmapped_codes, report.unmapped_rows)
    rows: list[dict[str, Any]] = []
    for p in dataset.payroll:
        if p.pay_period_start is None or p.pay_period_end is None:
            continue  # no span means no denominator; counted by `projection_controls`, never silent
        paid = transforms.effective_pay_date(ctx.pay_date_mode, p.pay_date, p.pay_period_end)
        if paid is None:
            continue  # `null_pay_date=exclude`: counted in `projection_controls`
        rows.append(_bcs_row(p, paid, ctx))
    _log_findings(dataset, rows, ctx)
    return rows


def _log_findings(dataset: SourceDataset, rows: list[dict[str, Any]], ctx: _Context) -> None:
    """Say, once per account load, what the projection had to assume."""
    account = dataset.account.account_id
    imputed = sum(1 for r in rows if r["_Pay_Date_Imputed"])
    if imputed or len(rows) < len(dataset.payroll):
        log.warning(
            "account %s: %d payroll row(s) have no paycheck date; null_pay_date=%s (%s). Counted in the projection controls.",
            account, sum(1 for p in dataset.payroll if p.pay_date is None), ctx.pay_date_mode,
            f"{imputed} used the period end" if ctx.pay_date_mode == "period_end" else "left out",
        )
    report = ctx.pay_code_report
    if report.unmapped_codes or report.inferred_codes:
        log.warning(
            "account %s: pay codes - %d unmapped (%d row(s): %s), %d resolved by an inferred seed; policy=%s. "
            "An unmapped code is dropped by the state's whitelist.",
            account, len(report.unmapped_codes), report.unmapped_rows, ", ".join(report.unmapped_codes[:10]) or "-",
            report.inferred_codes, report.policy,
        )


def projection_controls(dataset: SourceDataset, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Row-level controls for the projection.

    Every drop, coercion and assumption is counted. A Silver layer that loses rows without saying so is how a wrong
    number reaches a filed return.
    """
    payroll = dataset.payroll
    null_pay_date = sum(1 for p in payroll if p.pay_date is None)
    no_span = sum(1 for p in payroll if p.pay_period_start is None or p.pay_period_end is None)
    no_span_null = sum(1 for p in payroll if p.pay_date is None and (p.pay_period_start is None or p.pay_period_end is None))
    imputed = sum(1 for r in rows if r["_Pay_Date_Imputed"])
    from data.lookups import resolve_pay_codes

    return {
        "account_id": dataset.account.account_id,
        "account_name": dataset.account.name,
        "payroll_rows_in": len(payroll),
        "bcs_rows_out": len(rows),
        "dropped_no_period_span": no_span,
        "null_pay_date": null_pay_date,              # Q1
        "null_pay_date_policy": mapping.null_pay_date_mode(),
        "null_pay_date_imputed": imputed,
        "null_pay_date_excluded": null_pay_date - imputed - no_span_null,
        "null_hours_coerced_to_zero": sum(1 for p in payroll if p.hours is None),    # Q2
        "null_wages_coerced_to_zero": sum(1 for p in payroll if p.wages is None),    # Q2
        "worksite_fell_back_to_location": sum(1 for p in payroll if p.worksite_location_id is None),  # Q3
        "pay_codes": resolve_pay_codes(dataset)[1].as_dict(),
        "rows_with_no_county": sum(1 for r in rows if not r["Work_County"]),
        "distinct_employees": len({r["Employee_ID"] for r in rows}),
        "distinct_worksites": len({r["Worksite_ID"] for r in rows}),
        "distinct_feins": len({r["Entity_FEIN"] for r in rows}),
    }
