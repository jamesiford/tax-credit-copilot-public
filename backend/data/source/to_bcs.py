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

from typing import Any

from .schema import SourceDataset

# BA-03. The source PayFrequencyId is a surrogate key whose lookup the partner has
# not supplied. It is carried through as lineage and never used as a multiplier
# — the engine measures each period's actual span instead.
_UNKNOWN_FREQUENCY = ""

# BA-07 / Q5 — **INFERRED. Pending the partner's `PayCodeCategory` lookup.**
#
# `PayCode.PayCode` is a client-specific string: one account's "REG" is another's
# "RG01". Rule packs, by contrast, name canonical categories — Georgia includes
# `Regular`, `Overtime`, `Bonus`, `Commission` and suppresses `Mileage`,
# `Expense_Reimbursement`, `Relocation`. Something has to map one to the other.
#
# In the source that something is almost certainly `PayCode.PayCodeCategoryId`,
# which is the lookup already owed to us (Q5 in SOURCE-SCHEMA-MAPPING.md). Until
# it arrives, this maps by convention.
#
# The consequence of getting this wrong is not subtle: an unmapped code is
# dropped by `apply_pay_code_policy` BEFORE the calculation runs, so the engine
# silently sees no payroll at all. That is how the first source-backed API call
# returned 9,832 rows loaded and zero eligible employees.
_CANONICAL_PAY_CODE: dict[str, str] = {
    "REG": "Regular",
    "OT": "Overtime",
    "BON": "Bonus",
    "COM": "Commission",
    "PTO": "Regular",          # paid leave is remuneration for the wage test
    "MIL": "Mileage",
    "EXP": "Expense_Reimbursement",
    "RELO": "Relocation",
}


def canonical_pay_code(source_code: str | None) -> str:
    """Client pay code -> the canonical category rule packs name.

    Falls through to the code itself when unmapped, so an unexpected code is
    visible in the output rather than silently becoming `Regular` and inflating
    the wage base.
    """
    if not source_code:
        return "Regular"
    code = source_code.strip()
    return _CANONICAL_PAY_CODE.get(code.upper(), code)


def source_to_bcs_rows(dataset: SourceDataset) -> list[dict[str, Any]]:
    """Project one client's source tables into Silver Record Layout rows.

    Returns plain dicts. The engine is pure functions over lists of dicts
    (ADR-003), so nothing about the Warehouse, Fabric or Delta reaches it.
    """
    fein_by_entity = {e.entity_id: (e.federal_tax_id or "") for e in dataset.entities}
    title_by_employee = {e.employee_id: (e.job_title or "") for e in dataset.employments}
    code_by_id = {p.pay_code_id: p.pay_code for p in dataset.pay_codes}

    # Resolve each worksite's state through Location -> Address -> StateCountyZip.
    # This is the same join that reaches `county_name`, which Georgia's tier — and
    # therefore credit value — depends on.
    address_by_id = {a.address_id: a for a in dataset.addresses}
    scz_by_id = {s.state_county_zip_id: s for s in dataset.state_county_zips}

    # Q3: GA JTC counts jobs at a worksite. `WorksiteLocationId` is nullable in
    # the source, so fall back to `LocationId` — which is NOT NULL — rather than
    # dropping the row. Flagged for the partner; the fallback is explicit here so
    # the choice is visible if the answer changes it.
    unit_of: dict[int, str] = {}
    state_of: dict[int, str] = {}
    county_of: dict[int, str] = {}

    for loc in dataset.locations:
        address = address_by_id.get(loc.address_id)
        scz = scz_by_id.get(address.state_county_zip_id) if address else None
        state = (scz.state_abbr if scz else None) or (address.state_original if address else "") or ""
        state = state.upper()

        # Prefer the client's own identifier where present: it is what appears on
        # their reports, and what a reconciliation against them has to match.
        raw_unit = loc.client_location_id or str(loc.location_id)

        # The pipeline filters per state by worksite prefix
        # (`_payperiods.iter_state_packs` matches `f"{state}_"`), so the unit id
        # carries its state the same way `fabric_source.map_fabric_employees_row`
        # does for the demo table. Without this every state filter returns empty
        # and the calculation silently produces nothing.
        unit_of[loc.location_id] = (
            raw_unit if not state or raw_unit.startswith(f"{state}_") else f"{state}_{raw_unit}"
        )
        state_of[loc.location_id] = state
        county_of[loc.location_id] = scz.county_name if scz else ""

    rows: list[dict[str, Any]] = []
    for p in dataset.payroll:
        if p.pay_period_start is None or p.pay_period_end is None:
            # A period with no span cannot contribute a denominator. Surfacing
            # it as an exception is Silver's job; dropping it silently is not,
            # so this is counted by `projection_controls`.
            continue

        location_id = p.worksite_location_id or p.location_id
        pay_date = p.pay_date

        rows.append({
            # BA-02 trims on paycheck date; tax year is derived downstream from
            # the fiscal window, never assumed to be the calendar year.
            "Tax_Year": pay_date.year if pay_date else p.pay_period_end.year,
            "Employee_ID": str(p.employee_id),
            "Job_Title": title_by_employee.get(p.employee_id, ""),
            "Worksite_ID": unit_of.get(location_id, str(location_id)),
            "Work_State": state_of.get(location_id, ""),
            # County reaches the row so credit-value work does not need to
            # re-walk the dimension join.
            "Work_County": county_of.get(location_id, ""),
            "Entity_FEIN": fein_by_entity.get(p.entity_id, ""),
            "Pay_Period_Start": p.pay_period_start.isoformat(),
            "Pay_Period_End": p.pay_period_end.isoformat(),
            # Q1: nullable in source. Left as None so the engine's trim can
            # treat it as an exception rather than silently bucketing it.
            "Pay_Date": pay_date.isoformat() if pay_date else None,
            "Pay_Frequency": str(p.pay_frequency_id) if p.pay_frequency_id else _UNKNOWN_FREQUENCY,
            # BA-07: the canonical category the rule pack names, not the raw
            # client code — see `canonical_pay_code`. The source code is kept as
            # lineage so a reconciliation against the client's own report can
            # still be done.
            "Pay_Code": canonical_pay_code(code_by_id.get(p.pay_code_id)),
            "_Source_Pay_Code": code_by_id.get(p.pay_code_id, ""),
            # Q2: NULL and 0 are not the same thing. Until the partner confirms,
            # NULL coerces to 0.0 so BA-05 keeps the row — a zero-hour wage row
            # is a real payroll fact — but the count is reported separately.
            "Hours_Worked": float(p.hours) if p.hours is not None else 0.0,
            "Gross_Wages": float(p.wages) if p.wages is not None else 0.0,
            # Lineage back to the source row, for the audit trail.
            "_Source_Payroll_Id": p.payroll_id,
            "_Source_Account_Id": p.account_id,
        })

    return rows


def projection_controls(dataset: SourceDataset, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Row-level controls for the projection.

    Every drop and every coercion is counted. A Silver layer that loses rows
    without saying so is how a wrong number reaches a filed return.
    """
    null_pay_date = sum(1 for p in dataset.payroll if p.pay_date is None)
    null_hours = sum(1 for p in dataset.payroll if p.hours is None)
    null_wages = sum(1 for p in dataset.payroll if p.wages is None)
    no_span = sum(
        1 for p in dataset.payroll
        if p.pay_period_start is None or p.pay_period_end is None
    )
    missing_worksite = sum(1 for p in dataset.payroll if p.worksite_location_id is None)

    return {
        "account_id": dataset.account.account_id,
        "account_name": dataset.account.name,
        "payroll_rows_in": len(dataset.payroll),
        "bcs_rows_out": len(rows),
        "dropped_no_period_span": no_span,
        "null_pay_date": null_pay_date,              # Q1
        "null_hours_coerced_to_zero": null_hours,    # Q2
        "null_wages_coerced_to_zero": null_wages,    # Q2
        "worksite_fell_back_to_location": missing_worksite,  # Q3
        "distinct_employees": len({r["Employee_ID"] for r in rows}),
        "distinct_worksites": len({r["Worksite_ID"] for r in rows}),
        "distinct_feins": len({r["Entity_FEIN"] for r in rows}),
    }
