"""Engine results projected onto the Gold schema. Data in, rows out.

Pure functions: no connection, no clock, no environment. Everything that varies
between runs arrives as an argument, so a projection replays identically years
later and can be unit-tested without a warehouse.

Two rules run through the whole file.

**Money and headcount are `Decimal`, never `float`.** Every target column is
`DECIMAL(...)`, and a float that reaches the driver comes back as a binary
approximation of a figure that was exact when it went in. `_dec` is the only way
a number becomes a value here.

**`record_token` is imported, never re-derived.** `tools/tokens.py` owns the one
definition; a second implementation is a second chance to disagree, and the
symptom is a drill URL that 404s on every row a screen renders.

Column order in each `*_COLUMNS` tuple is the DDL's. The row builders emit
tuples in that order, so the insert statement and the projection cannot drift
into disagreeing about position.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from tools.tokens import record_token

_QUANTIZERS = {2: Decimal("0.01"), 4: Decimal("0.0001")}


def _dec(value: Any, places: int = 2) -> Decimal | None:
    """A number as the warehouse stores it, or None.

    Takes `str` in preference to `float` wherever the source offers one — the
    payroll reader hands back `'1972.36'`, and going via the string keeps the
    figure exact instead of rounding a float that was never 1972.36.
    """
    if value is None or value == "":
        return None
    return Decimal(str(value)).quantize(_QUANTIZERS[places])


def _day(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _flag(value: Any) -> int:
    """BIT. pyodbc wants 0/1, not True/False, for a bit column."""
    return 1 if value else 0


# --------------------------------------------------------------- run identity


def calculation_id(
    *,
    client_id: int,
    program_code: str,
    tax_year: int,
    window_begin: date,
    window_end: date,
    floors: Mapping[str, Any],
    assumption_ids: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> str:
    """A deterministic fingerprint of everything that decides the answer.

    Two runs over the same payroll, statute and assumptions produce the same id;
    a run over corrected payroll does not. That is what makes "which calculation
    produced this figure" answerable when the underlying rows have since moved.

    The payroll contributes a digest of its identifying and monetary fields
    rather than the whole row, so a column added for display does not invalidate
    every prior calculation id.
    """
    payroll = hashlib.sha256()
    for row in rows:
        payroll.update(
            "\0".join(
                str(row.get(field) or "")
                for field in (
                    "Employee_ID", "Worksite_ID", "Entity_FEIN",
                    "Pay_Period_Start", "Pay_Period_End", "Pay_Date",
                    "Hours_Worked", "Gross_Wages", "Pay_Code",
                )
            ).encode()
        )
        payroll.update(b"\n")

    seed = "\0".join([
        str(client_id), program_code, str(tax_year),
        window_begin.isoformat(), window_end.isoformat(),
        str(floors.get("minimum_average_weekly_hours")),
        str(floors.get("minimum_average_weekly_wages_usd")),
        str(floors.get("source")),
        *assumption_ids,
        payroll.hexdigest(),
    ])
    return hashlib.sha256(seed.encode()).hexdigest()


# ------------------------------------------------- tcc_gold.employee_period_fact

EMPLOYEE_PERIOD_FACT_COLUMNS = (
    "client_id", "tax_year", "run_id", "employee_id", "record_token",
    "worksite_id", "entity_fein", "job_title", "pay_period_start",
    "pay_period_end", "pay_date", "period_days", "pay_frequency_code",
    "hours", "wages", "pay_code", "included", "selection_decision", "qc_flag",
)


def employee_period_fact_rows(
    payroll: Iterable[Mapping[str, Any]],
    *,
    client_id: int,
    program_code: str,
    tax_year: int,
    run_id: str,
) -> list[tuple]:
    """One row per pay period, as the run consumed it.

    `included` is 1 for everything here because these are the rows the resolver
    already selected: `selection_decision` records that the fiscal window is why.
    Rows dropped upstream by the QC filter never reach this function, which is a
    real gap — they are the ones an exception report wants — and is why the
    column exists rather than being assumed.
    """
    out: list[tuple] = []
    for row in payroll:
        employee_id = str(row["Employee_ID"])
        start = _day(row.get("Pay_Period_Start"))
        end = _day(row.get("Pay_Period_End"))
        out.append((
            client_id,
            tax_year,
            run_id,
            employee_id,
            record_token(client_id, program_code, tax_year, employee_id),
            str(row.get("Worksite_ID") or "") or None,
            str(row.get("Entity_FEIN") or "") or None,
            str(row.get("Job_Title") or "") or None,
            start,
            end,
            _day(row.get("Pay_Date")),
            (end - start).days + 1 if start and end else 0,
            str(row.get("Pay_Frequency") or "") or None,
            _dec(row.get("Hours_Worked")),
            _dec(row.get("Gross_Wages")),
            str(row.get("Pay_Code") or "") or None,
            1,
            "fiscal_window",
            None,
        ))
    return out


# ------------------------------------------------- tcc_gold.employee_eligibility

EMPLOYEE_ELIGIBILITY_COLUMNS = (
    "client_id", "tax_year", "method", "run_id", "employee_id", "record_token",
    "total_hours", "total_wages", "first_start", "last_end", "days",
    "weeks_worked", "avg_weekly_hours", "avg_weekly_wages", "eligible", "weight",
)


def employee_eligibility_rows(
    *,
    totals: Sequence[Mapping[str, Any]],
    averages: Sequence[Mapping[str, Any]],
    client_id: int,
    program_code: str,
    tax_year: int,
    method: str,
    run_id: str,
) -> list[tuple]:
    """One row per employee per method — EVERY employee with payroll, not just
    those the method could average.

    The denominator is `totals`, not `averages`. 156 of the reference client's
    10,236 employees have hours and wages but no qualifying pay period, so they
    are absent from `all_averages`; taking the denominator from there reports
    10,080 and looks entirely plausible. Those employees get a row with NULL
    averages and `eligible = 0`, because "we evaluated them and they did not
    qualify" and "we never looked at them" are different statements.
    """
    by_employee = {str(row["Employee_ID"]): row for row in averages}

    out: list[tuple] = []
    for total in totals:
        employee_id = str(total["Employee_ID"])
        average = by_employee.get(employee_id)
        out.append((
            client_id,
            tax_year,
            method,
            run_id,
            employee_id,
            record_token(client_id, program_code, tax_year, employee_id),
            _dec(total.get("total_hours") or 0),
            _dec(total.get("total_wages") or 0),
            _day(average.get("first_start")) if average else None,
            _day(average.get("last_end")) if average else None,
            int(average["days"]) if average and average.get("days") is not None else None,
            _dec(average.get("weeks_worked")) if average else None,
            _dec(average.get("avg_weekly_hours")) if average else None,
            _dec(average.get("avg_weekly_wages")) if average else None,
            _flag(average.get("eligible")) if average else 0,
            _dec(average.get("weight") if average else 1.0),
        ))
    return out


# ----------------------------------------------------- tcc_gold.onezero_matrix

ONEZERO_MATRIX_COLUMNS = (
    "client_id", "tax_year", "method", "run_id", "employee_id", "record_token",
    "worksite_id", "entity_fein", "first_pps", "last_ppe", "weight",
    *(f"month_{i:02d}" for i in range(1, 13)),
)


def onezero_matrix_rows(
    matrix: Iterable[Mapping[str, Any]],
    *,
    client_id: int,
    program_code: str,
    tax_year: int,
    method: str,
    run_id: str,
) -> list[tuple]:
    """The monthly one/zero allocation, one row per employee per unit segment.

    The two methods publish the segment span under DIFFERENT KEYS: Min-Max emits
    `first_pps`/`last_ppe` for the whole span it measured, Pay Period emits
    `Pay_Period_Start`/`Pay_Period_End` because its rows are per pay period.
    Both mean "the span this row covers", and the column is NOT NULL, so reading
    only one shape writes NULL for every row of the other method.

    Takes the result's PUBLISHED matrix. `run_min_max_method` resolves
    employee-months claimed by two units and the deduped matrix is the one that
    agrees with `annual_average`; rolling up anything else double-counts.
    """
    out: list[tuple] = []
    for row in matrix:
        employee_id = str(row["Employee_ID"])
        months = list(row.get("months") or [])
        months += [0.0] * (12 - len(months))

        first_pps = _day(row.get("first_pps") or row.get("Pay_Period_Start"))
        last_ppe = _day(row.get("last_ppe") or row.get("Pay_Period_End"))
        if first_pps is None or last_ppe is None:
            raise ValueError(
                f"matrix row for employee {employee_id!r} carries no period span "
                f"under either key shape; writing NULL would lose the segment "
                f"the months were measured over"
            )

        out.append((
            client_id,
            tax_year,
            method,
            run_id,
            employee_id,
            record_token(client_id, program_code, tax_year, employee_id),
            str(row.get("Worksite_ID") or ""),
            str(row.get("Entity_FEIN") or "") or None,
            first_pps,
            last_ppe,
            _dec(row.get("weight") or 0),
            *(_dec(months[i]) for i in range(12)),
        ))
    return out


# ------------------------------------------------- tcc_gold.unit_month_summary

# ------------------------------------------------- tcc_gold.run_method_summary

RUN_METHOD_SUMMARY_COLUMNS = (
    "client_id", "tax_year", "method", "run_id", "program_code",
    "annual_average", "eligible_employees", "employees_evaluated",
    "matrix_rows", "unit_fein_rows", "contested_months", "month_ends",
    "appended_at",
)


def run_method_summary_row(
    result: Any,
    *,
    client_id: int,
    program_code: str,
    tax_year: int,
    method: str,
    run_id: str,
    unit_fein_rows: int,
    appended_at: datetime,
) -> tuple:
    """What one method concluded about one client-year, as a whole.

    These are properties of the RUN, not of a unit or an employee, so nothing
    else in Gold could carry them. `contested_months` is the one that cannot be
    recovered at all: the matrix is deduped before it is written, so a contest
    leaves no trace in the rows it produced.
    """
    contested = sum(
        1 for flag in (result.flags or [])
        if flag.get("type") == "multi_unit_double_count"
    )
    return (
        client_id,
        tax_year,
        method,
        run_id,
        program_code,
        _dec(result.annual_average),
        len(result.eligible_employees),
        len(result.total_hours_and_wages),
        len(result.employee_unit_matrix),
        unit_fein_rows,
        contested,
        json.dumps([month.isoformat() for month in result.months]),
        appended_at,
    )


UNIT_MONTH_SUMMARY_COLUMNS = (
    "client_id", "tax_year", "method", "run_id", "worksite_id",
    *(f"month_{i:02d}" for i in range(1, 13)),
    "total", "average_headcount", "months_with_headcount", "unreachable_months",
)


def unit_month_summary_rows(
    summary: Iterable[Mapping[str, Any]],
    *,
    client_id: int,
    tax_year: int,
    method: str,
    run_id: str,
    unreachable: Sequence[int],
) -> list[tuple]:
    """Per unit, per month. `average_headcount` divides by 12 ALWAYS.

    Including months that scored zero, and including months no pay period could
    reach. That matches the partner's own Access output and is asserted by
    validation query 9.8 — a divisor "fixed" to months-with-data inflates every
    figure on the grid.
    """
    unreachable_csv = ",".join(str(i) for i in unreachable) or None

    out: list[tuple] = []
    for row in summary:
        totals = list(row.get("month_totals") or [])
        totals += [0.0] * (12 - len(totals))
        out.append((
            client_id,
            tax_year,
            method,
            run_id,
            str(row["Worksite_ID"]),
            *(_dec(totals[i]) for i in range(12)),
            _dec(row.get("total") or 0),
            _dec(row.get("average_headcount") or 0),
            sum(1 for value in totals[:12] if value),
            unreachable_csv,
        ))
    return out


# --------------------------------------------------- tcc_gold.unit_year_master

UNIT_YEAR_MASTER_COLUMNS = (
    "client_id", "worksite_id", "entity_fein", "program_code", "method",
    "tax_year", "average_headcount", "is_base_year", "base_average_headcount",
    "base_year_source", "net_new_vs_base", "months_reachable", "year_complete",
    "declined", "decline_reason", "threshold", "threshold_source", "qualified",
    "status", "tier", "designation", "tier_source", "eligible_jobs",
    "new_jobs_created", "high_water_mark", "backfilled", "per_job_usd",
    "tranche_years", "annual_credit_usd", "base_year_overridden",
    "high_water_mark_overridden", "run_id", "is_current", "appended_at",
)


def unit_year_master_row(
    *,
    client_id: int,
    worksite_id: str,
    entity_fein: str | None,
    program_code: str,
    method: str,
    tax_year: int,
    stair: Any,
    trend: Any,
    unit_year: Mapping[str, Any],
    base_year: int,
    base_year_source: str,
    months_reachable: int,
    declined: bool,
    decline_reason: str | None,
    threshold_source: str,
    status: str,
    tier: str | None,
    designation: str | None,
    tier_source: str,
    run_id: str,
    appended_at: datetime,
) -> tuple:
    """One unit-year, with the credit layer attached.

    `stair` is a `TrancheYear`; `trend` the `BaseYearResult` it came from. The
    credit columns are not optional — they are what the grid displays, and a
    dollar computed at display time cannot be reconciled to the row that
    produced it.
    """
    return (
        client_id,
        worksite_id,
        entity_fein,
        program_code,
        method,
        tax_year,
        _dec(unit_year.get("average_headcount") or 0),
        _flag(tax_year == base_year),
        _dec(trend.base_average_headcount),
        base_year_source,
        _dec(stair.net_new) if stair else None,
        months_reachable,
        _flag(unit_year.get("months_with_headcount", 0) >= months_reachable),
        _flag(declined),
        decline_reason,
        _dec(stair.threshold) if stair else None,
        threshold_source,
        _flag(stair.qualified if stair else False),
        status,
        tier,
        designation,
        tier_source,
        _dec(stair.eligible_jobs) if stair else None,
        _dec(stair.new_jobs_created) if stair else None,
        _dec(stair.high_water_mark) if stair else None,
        _flag(stair.backfilled if stair else False),
        _dec(getattr(stair, "per_job_usd", None) or trend.per_job_usd, 4),
        trend.tranche_years,
        _dec(stair.annual_credit_usd if stair else 0, 4),
        # A base year a human chose (WI-21) is as much an override as a
        # negotiated base average, and the screen marks both the same way.
        _flag(trend.base_year_overridden or base_year_source == "override"),
        _flag(trend.high_water_mark_overridden),
        run_id,
        1,
        appended_at,
    )


# --------------------------------------------- tcc_gold.unit_credit_installment

UNIT_CREDIT_INSTALLMENT_COLUMNS = (
    "client_id", "worksite_id", "program_code", "method", "creation_year",
    "tax_year", "tranche_jobs", "jobs_maintained", "per_job_usd",
    "claimable_usd", "projected", "run_id", "is_current", "appended_at",
)


def unit_credit_installment_rows(
    trend: Any,
    *,
    client_id: int,
    worksite_id: str,
    program_code: str,
    method: str,
    years_with_data: Sequence[int],
    run_id: str,
    appended_at: datetime,
) -> list[tuple]:
    """Creation-year x claimable-year. A job created once pays out for years.

    `projected` marks an installment whose year has no payroll yet: the engine
    assumes the job is maintained so the forecast ceiling is visible, and the
    flag is what stops that assumption reading as an observation.
    """
    known = set(years_with_data)

    out: list[tuple] = []
    for event in trend.tranche_events:
        for installment in event.installments:
            out.append((
                client_id,
                worksite_id,
                program_code,
                method,
                event.creation_year,
                installment["year"],
                _dec(event.jobs),
                _dec(installment["jobs_maintained"]),
                _dec(event.per_job_usd, 4),
                _dec(installment["credit_usd"], 4),
                _flag(installment["year"] not in known),
                run_id,
                1,
                appended_at,
            ))
    return out


def utc_now() -> datetime:
    """One clock reading per run, so every row of it shares an `appended_at`."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
