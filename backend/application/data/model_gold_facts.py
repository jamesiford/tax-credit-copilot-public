"""Gold datasets at employee grain: the pay-period fact, the verdicts and the One/Zero matrix. [CH-16a]

Every dataset here is `employee_level`: one row is one person (or one person's pay
period), so a query that returns raw rows is delivered to the person asking and never
shown to a model. An aggregate over them (a count by location, an average by month) is
fine to narrate. The person is only ever a `record_token`; the tokenised employee id sits
beside it as a `blocked` column so nobody can add it to a query by accident.

These rows hold what the engine consumed and decided, run by run. A run writes every year
the payroll covers and a re-run supersedes the last, so each dataset pins the client's
live run (`Currency.LIVE_RUN`), exactly as the portal's reads do.
"""
from __future__ import annotations

from application.data.model_dsl import Cols
from application.data.semantic_model import Currency, Dataset, SchemaKey, Source

G = Cols()
_METHODS = ("min_max", "pay_period")
_RUN = "The calculation run that wrote the row. The live run is selected for you."
_TOKEN = "The opaque handle for one employee in one client, programme and tax year. The only way a person appears."
_EMPLOYEE_ID = "Tokenised employee id. Blocked: the record token is the only handle a person is given."
_METHOD = "Which statutory reading produced the row: min_max or pay_period. Never mixed silently."

_MONTHS = tuple(f"month_{n:02d}" for n in range(1, 13))

PERIOD_FACT = Dataset(
    name="employee_period_fact", source=Source.WAREHOUSE, schema=SchemaKey.GOLD,
    table="employee_period_fact", tenant_column="client_id", currency=Currency.LIVE_RUN,
    employee_level=True, person_key="employee_id", year_column="tax_year", period_columns=("pay_period_start", "pay_period_end", "pay_date"),
    grain="One row per employee per pay period, after the payroll was normalised. The only table that scales with payroll.",
    description="The denominator grain: every pay period the run consumed, with its hours, wages and why it counted or not.",
    columns=(
        G.dim("tax_year", "int", "The tax year the run assigned the row to."),
        G.ident("run_id", "text", _RUN, ops=()),
        G.blocked("employee_id", "text", _EMPLOYEE_ID),
        G.ident("record_token", "text", _TOKEN, emp=True),
        G.dim("worksite_id", "text", "The worksite the job is counted at (the payroll's worksite location)."),
        G.dim("entity_fein", "text", "The legal entity's federal tax id."),
        G.dim("job_title", "text", "Job title on the payroll row.", free_text=True),
        G.dim("pay_period_start", "date", "First day of the pay period."),
        G.dim("pay_period_end", "date", "Last day of the pay period."),
        G.dim("pay_date", "date", "Date paid. Blank where the source carried none."),
        G.measure("period_days", "int", "Inclusive length of the pay period. It drives the BA-12 week count.", unit="days"),
        G.dim("pay_frequency_code", "text", "The source's pay-frequency key, kept as lineage only and never used as a week multiplier."),
        G.measure("hours", "decimal", "Hours on the payroll row. Blank is not zero.", emp=True, unit="hours"),
        G.measure("wages", "decimal", "Wages on the payroll row.", emp=True, unit="USD"),
        G.dim("pay_code", "text", "Payroll pay code of the row.", free_text=True),
        G.flag("included", "True when the row survived the pay-code filter and counted (BA-07)."),
        G.dim("selection_decision", "text", "Why the row did or did not count: inside the fiscal window, too short, filtered by pay code."),
        G.dim("qc_flag", "text", "Quality-control mark: test_of_twos, short_period or none."),
    ),
    engine_notes=(
        ("hours, wages, included", "Inputs to the engine, not results. The engine's own totals are on employee_eligibility; use client_eligibility for the verdict."),
        ("row counts", "Counts pay periods, not people. Use count_distinct on record_token for people."),
    ),
)

ELIGIBILITY = Dataset(
    name="employee_eligibility", source=Source.WAREHOUSE, schema=SchemaKey.GOLD,
    table="employee_eligibility", tenant_column="client_id", currency=Currency.LIVE_RUN,
    employee_level=True, person_key="employee_id", year_column="tax_year", method_column="method",
    grain="One row per employee per method per tax year, eligible or not.",
    description="The engine's verdict on every employee, with the hours and wages behind it. Near misses are rows too.",
    columns=(
        G.dim("tax_year", "int", "The tax year of the verdict."),
        G.dim("method", "text", _METHOD, choices=_METHODS),
        G.ident("run_id", "text", _RUN, ops=()),
        G.blocked("employee_id", "text", _EMPLOYEE_ID),
        G.ident("record_token", "text", _TOKEN, emp=True),
        G.measure("total_hours", "decimal", "Hours across the employee's counted pay periods.", emp=True, unit="hours"),
        G.measure("total_wages", "decimal", "Wages across the employee's counted pay periods.", emp=True, unit="USD"),
        G.dim("first_start", "date", "Start of the employee's first counted pay period."),
        G.dim("last_end", "date", "End of the employee's last counted pay period."),
        G.measure("days", "int", "Days from first start to last end.", unit="days"),
        G.measure("weeks_worked", "decimal", "Weeks in the span, as the engine measured them.", unit="weeks"),
        G.measure("avg_weekly_hours", "decimal", "Average weekly hours, rounded half-up to two places; the rounded value is what the floor tests.", emp=True, unit="hours/week"),
        G.measure("avg_weekly_wages", "decimal", "Average weekly wages, rounded half-up to two places.", emp=True, unit="USD/week"),
        G.flag("eligible", "The engine's verdict. Equals 'cleared both floors' only where no part-time band applies."),
        G.measure("weight", "decimal", "1.00 for full-time, the part-time weight otherwise; the job count is the sum of weights.", unit="jobs"),
    ),
    engine_notes=(
        ("eligible", "client_eligibility reports the eligible count and annual average from the same run; it is authoritative. This dataset lets you break it down."),
        ("avg_weekly_hours, avg_weekly_wages", "client_at_risk ranks the employees close to a floor; use it for 'who could fall out'."),
    ),
)

ONEZERO = Dataset(
    name="onezero_matrix", source=Source.WAREHOUSE, schema=SchemaKey.GOLD,
    table="onezero_matrix", tenant_column="client_id", currency=Currency.LIVE_RUN,
    employee_level=True, person_key="employee_id", year_column="tax_year", method_column="method", month_columns=_MONTHS,
    period_columns=("first_pps", "last_ppe"),
    grain="One row per eligible employee per worksite per method per tax year; twelve monthly One/Zero cells.",
    description="The One/Zero decision for each employee who qualified: counted (1 or the part-time weight) or not (0) in each month.",
    columns=(
        G.dim("tax_year", "int", "The tax year of the matrix."),
        G.dim("method", "text", _METHOD, choices=_METHODS),
        G.ident("run_id", "text", _RUN, ops=()),
        G.blocked("employee_id", "text", _EMPLOYEE_ID),
        G.ident("record_token", "text", _TOKEN, emp=True),
        G.dim("worksite_id", "text", "The worksite the employee is counted at."),
        G.dim("entity_fein", "text", "The legal entity's federal tax id."),
        G.dim("first_pps", "date", "First pay-period start in the employee's span."),
        G.dim("last_ppe", "date", "Last pay-period end in the employee's span."),
        G.measure("weight", "decimal", "The employee's weight: 1.00 full-time, the part-time weight otherwise.", unit="jobs"),
        *(G.measure(m, "decimal", f"The One/Zero cell for fiscal month {int(m[-2:])}: counted or not.", emp=True, unit="jobs") for m in _MONTHS),
    ),
    engine_notes=(
        ("month_NN", "Summed by worksite these are the monthly headcount on unit_month_summary. The matrix holds only people who already qualified, so it cannot show a near miss."),
    ),
)

FACT_DATASETS = (PERIOD_FACT, ELIGIBILITY, ONEZERO)
