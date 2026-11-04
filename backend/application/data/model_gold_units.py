"""Gold datasets at location grain, plus the run manifest. [CH-16a]

None of these holds a person: a row is a worksite-month, a client-year-method or a run.
They are `public_aggregate`, so what a query returns can be narrated. Small cells are
the one caution: a worksite with a single employee is that employee's pay in aggregate
clothing, which is why the privacy design lives in the lanes and not in this file.
"""
from __future__ import annotations

from application.data.model_dsl import Cols
from application.data.semantic_model import Currency, Dataset, SchemaKey, Source

G = Cols()
_METHODS = ("min_max", "pay_period")
_RUN = "The calculation run that wrote the row. The live run is selected for you."
_METHOD = "Which statutory reading produced the row: min_max or pay_period. Never mixed silently."
_MONTHS = tuple(f"month_{n:02d}" for n in range(1, 13))

MONTH_SUMMARY = Dataset(
    name="unit_month_summary", source=Source.WAREHOUSE, schema=SchemaKey.GOLD,
    table="unit_month_summary", tenant_column="client_id", currency=Currency.LIVE_RUN,
    year_column="tax_year", method_column="method", month_columns=_MONTHS,
    grain="One row per worksite per method per tax year; twelve monthly headcounts.",
    description="The monthly headcount at each worksite, as the One/Zero method counted it. The shape the partner reads the credit in.",
    columns=(
        G.dim("tax_year", "int", "The tax year of the summary."),
        G.dim("method", "text", _METHOD, choices=_METHODS),
        G.ident("run_id", "text", _RUN, ops=()),
        G.dim("worksite_id", "text", "The worksite (unit) the headcount is for."),
        *(G.measure(m, "decimal", f"Headcount at the fiscal month {int(m[-2:])} measuring date. Zero can mean no pay period reaches that date.", unit="headcount") for m in _MONTHS),
        G.measure("total", "decimal", "Sum of the twelve monthly headcounts.", unit="headcount"),
        G.measure("average_headcount", "decimal", "Total divided by twelve, always, including zero months, to match the partner's own summary.", unit="headcount"),
        G.measure("months_with_headcount", "int", "How many of the twelve months held any headcount.", unit="months"),
        G.dim("unreachable_months", "text", "Comma-separated month numbers no pay period reaches (a calendar fact, not a decline).", ops=()),
    ),
    engine_notes=(
        ("average_headcount", "client_eligibility and client_trend report the credit-driving average from the same run. Those are authoritative; this dataset shows which months and worksites drove it."),
        ("total", "Never divide by months-with-data: the divisor is twelve by agreement with the partner."),
    ),
)

METHOD_SUMMARY = Dataset(
    name="run_method_summary", source=Source.WAREHOUSE, schema=SchemaKey.GOLD,
    table="run_method_summary", tenant_column="client_id", currency=Currency.LIVE_RUN,
    year_column="tax_year", method_column="method",
    grain="One row per client per tax year per method.",
    description="What only the run knew: the annual average, how many employees each method found eligible, matrix size and contested months.",
    columns=(
        G.dim("tax_year", "int", "The tax year."),
        G.dim("method", "text", _METHOD, choices=_METHODS),
        G.ident("run_id", "text", _RUN, ops=()),
        G.dim("program_code", "text", "The programme the run priced, for example a state job-creation credit."),
        G.measure("annual_average", "decimal", "The method's annual average headcount for the client-year.", unit="headcount"),
        G.measure("eligible_employees", "int", "Employees the method found eligible.", unit="employees"),
        G.measure("employees_evaluated", "int", "Employees with payroll in the window.", unit="employees"),
        G.measure("matrix_rows", "int", "Rows in the One/Zero matrix.", unit="rows"),
        G.measure("unit_fein_rows", "int", "Worksite-by-entity rows.", unit="rows"),
        G.measure("contested_months", "int", "Employee-months where one person appeared at two worksites and the tie-breaker decided.", unit="employee-months"),
        G.dim("month_ends", "text", "The twelve measuring dates the run used, as a JSON list.", ops=()),
        G.dim("appended_at", "datetime", "When the row was written."),
    ),
    engine_notes=(
        ("annual_average, eligible_employees", "client_eligibility is authoritative for these. Quote the tool; use this dataset for the comparison across years or methods."),
    ),
)

RUN_MANIFEST = Dataset(
    name="run_manifest", source=Source.WAREHOUSE, schema=SchemaKey.OPS,
    table="run_manifest", tenant_column="client_id",
    year_column="tax_year", period_columns=("fiscal_year_begin", "fiscal_year_end"),
    grain="One row per calculation run, superseded runs included.",
    description="Which runs exist for the client, under which assumptions and rule pack, and whether they succeeded.",
    columns=(
        G.ident("run_id", "text", "The run's identifier."),
        G.dim("tax_year", "int", "The year the run was commanded for; a run covers every year the payroll holds."),
        G.dim("program_code", "text", "The programme priced."),
        G.dim("fiscal_year_begin", "date", "First day of the client's fiscal window."),
        G.dim("fiscal_year_end", "date", "Last day of the client's fiscal window."),
        G.dim("step1_assumption_set_id", "text", "The Min-Max methodology set the run used."),
        G.dim("onezero_assumption_set_id", "text", "The One/Zero methodology set the run used."),
        G.dim("rule_pack_version", "text", "The statute pack the run applied."),
        G.dim("code_commit", "text", "The engine's git commit."),
        G.dim("calculation_id", "text", "Deterministic hash of inputs and configuration; identical inputs give an identical hash."),
        G.dim("run_started_at", "datetime", "When the run began."),
        G.dim("run_completed_at", "datetime", "When the run finished."),
        G.dim("run_status", "text", "running, success, failed or superseded.", choices=("running", "success", "failed", "superseded")),
        G.dim("superseded_by_run_id", "text", "The run that replaced this one, if any."),
        G.blocked("triggered_by", "text", "Who started the run: a staff user principal name. Blocked."),
    ),
    excluded_columns=(
        ("entity_id", "Null means the whole client; no question needs it."),
        ("source_snapshot_id", "Lineage key into source_snapshot, which is not modelled."),
        ("step1_assumption_sha256", "A content hash for audit; the set id is the readable label."),
        ("onezero_assumption_sha256", "A content hash for audit; the set id is the readable label."),
    ),
    engine_notes=(
        ("run_status", "calc_walkthrough explains one run's derivation; this dataset lists the runs."),
    ),
)

UNIT_DATASETS = (MONTH_SUMMARY, METHOD_SUMMARY, RUN_MANIFEST)
