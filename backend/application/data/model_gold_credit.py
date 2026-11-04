"""Gold datasets for the credit itself: the unit-year master and its installments. [CH-16a]

These are the figures that land on a filed return. They carry `is_current`, because a
re-run supersedes rather than overwrites and a superseded figure may already be on a
return; a query reads only the current rows. Every figure here is the engine's own, read
back: `annual_credit_usd` is what `client_eligibility` and `client_trend` report, and
those tools stay authoritative. This model exists so the figure can be broken down by
worksite, year, method and tier, not so it can be recomputed.
"""
from __future__ import annotations

from application.data.model_dsl import Cols
from application.data.semantic_model import Currency, Dataset, SchemaKey, Source

G = Cols()
_METHODS = ("min_max", "pay_period")
_RUN = "The calculation run that wrote the row."
_METHOD = "Which statutory reading produced the row: min_max or pay_period. Never mixed silently."
_STATUS = ("base", "above_minimum", "below_minimum", "partial", "no_data", "before_base", "in_progress")

YEAR_MASTER = Dataset(
    name="unit_year_master", source=Source.WAREHOUSE, schema=SchemaKey.GOLD,
    table="unit_year_master", tenant_column="client_id", currency=Currency.IS_CURRENT,
    year_column="tax_year", method_column="method",
    grain="One current row per worksite per programme per method per tax year.",
    description="The cross-year master per location: headcount, base year, qualification, tier and the annual credit. The portal's location grid reads this table.",
    columns=(
        G.dim("worksite_id", "text", "The worksite (unit) the row is for."),
        G.dim("entity_fein", "text", "The legal entity's federal tax id."),
        G.dim("program_code", "text", "The programme priced."),
        G.dim("method", "text", _METHOD, choices=_METHODS),
        G.dim("tax_year", "int", "The tax year."),
        G.measure("average_headcount", "decimal", "Average headcount for the worksite-year (the monthly total divided by twelve).", unit="headcount"),
        G.flag("is_base_year", "True where this year is the worksite's base year."),
        G.measure("base_average_headcount", "decimal", "The frozen baseline headcount the credit is measured against.", unit="headcount"),
        G.dim("base_year_source", "text", "inferred or override.", choices=("inferred", "override")),
        G.measure("net_new_vs_base", "decimal", "Average headcount above the frozen base.", unit="jobs"),
        G.measure("months_reachable", "int", "Months whose measuring date a pay period reaches.", unit="months"),
        G.flag("year_complete", "True when the year fills every reachable month."),
        G.flag("declined", "True when under half the targets were reachable, so the year was declined rather than priced at zero."),
        G.dim("decline_reason", "text", "Why a year was declined.", free_text=True),
        G.measure("threshold", "decimal", "The statutory minimum new jobs.", unit="jobs"),
        G.dim("threshold_source", "text", "designation or rule_pack: which applied.", choices=("designation", "rule_pack")),
        G.flag("qualified", "True when the worksite met the threshold."),
        G.dim("status", "text", "The reading decided once for the grid.", choices=_STATUS),
        G.dim("tier", "text", "Geographic tier."),
        G.dim("designation", "text", "Negotiated designation, where one exists.", free_text=True),
        G.dim("tier_source", "text", "prototype or unassigned.", choices=("prototype", "unassigned")),
        G.measure("eligible_jobs", "decimal", "Net-new jobs above the frozen base; sizes the annual credit.", unit="jobs"),
        G.measure("new_jobs_created", "decimal", "Increment above the running high-water mark; sizes a new tranche.", unit="jobs"),
        G.measure("high_water_mark", "decimal", "Running maximum average through this year, never below base.", unit="headcount"),
        G.flag("backfilled", "True for a year that re-qualified after a non-qualifying one."),
        G.measure("per_job_usd", "decimal", "Dollars per job as applied by the rule pack of that run.", unit="USD"),
        G.measure("tranche_years", "int", "Benefit window in years.", unit="years"),
        G.measure("annual_credit_usd", "decimal", "Eligible jobs times dollars per job: the credit for the worksite-year.", unit="USD"),
        G.flag("base_year_overridden", "True where a person set the base year."),
        G.flag("high_water_mark_overridden", "True where a person set the high-water mark."),
        G.ident("run_id", "text", _RUN, ops=()),
        G.dim("appended_at", "datetime", "When the row was written."),
    ),
    excluded_columns=(("is_current", "The dataset's currency; applied for you, never a user choice."),),
    engine_notes=(
        ("annual_credit_usd", "client_eligibility and client_trend report the client-year credit; they are authoritative. Summed over worksites this column equals them for the same method and year."),
        ("status, qualified", "Decided once in the engine and read back. Do not re-derive them from headcount."),
    ),
)

INSTALLMENT = Dataset(
    name="unit_credit_installment", source=Source.WAREHOUSE, schema=SchemaKey.GOLD,
    table="unit_credit_installment", tenant_column="client_id", currency=Currency.IS_CURRENT,
    year_column="tax_year", method_column="method",
    grain="One current row per worksite per method per creation year per tax year.",
    description="The credit's tranche projection at its atomic grain: each qualifying year opens a window that pays an installment in each later year.",
    columns=(
        G.dim("worksite_id", "text", "The worksite (unit)."),
        G.dim("program_code", "text", "The programme priced."),
        G.dim("method", "text", _METHOD, choices=_METHODS),
        G.dim("creation_year", "int", "The year that opened the window."),
        G.dim("tax_year", "int", "The year the installment falls in."),
        G.measure("tranche_jobs", "decimal", "Window size at creation.", unit="jobs"),
        G.measure("jobs_maintained", "decimal", "Jobs still above base this year.", unit="jobs"),
        G.measure("per_job_usd", "decimal", "Dollars per job as applied.", unit="USD"),
        G.measure("claimable_usd", "decimal", "Jobs maintained times dollars per job.", unit="USD"),
        G.flag("projected", "True where no payroll exists yet and the installment assumes the job is maintained: a forecast, not a claim."),
        G.ident("run_id", "text", _RUN, ops=()),
        G.dim("appended_at", "datetime", "When the row was written."),
    ),
    excluded_columns=(("is_current", "The dataset's currency; applied for you, never a user choice."),),
    engine_notes=(
        ("claimable_usd", "A tax year's claimable figure is the sum over creation years. Rows with projected = true are forecasts and must be labelled so."),
    ),
)

CREDIT_DATASETS = (YEAR_MASTER, INSTALLMENT)
