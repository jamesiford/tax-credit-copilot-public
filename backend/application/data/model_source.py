"""Lakehouse source datasets: the payroll as the customer's own system holds it. [CH-16a]

Names and shapes are the source schema's (`data/source/schema.py`), in the PascalCase
the Delta tables carry. This is the raw material, before the engine's rules: it holds
pay codes the engine filters out and pay periods the fiscal window excludes, so a figure
here can legitimately differ from the engine's. For the credit, eligibility or the
headcount the engine concluded, the fixed tools are authoritative.

Only tables that carry the client key (`AccountId`) are datasets. `Employment` names the
employee but not the account, so it cannot be scoped to a client and is excluded; the
address, county and frequency lookups are shared reference data with no client key.

The two employee identifiers (`EmployeeId`, `ClientEmployeeId`) are `blocked`. The source
holds no record token (a token is derived per programme and tax year by the engine), so
payroll rows are anonymous: pay data per person-period with nothing to say whose.
"""
from __future__ import annotations

from application.data.model_dsl import Cols
from application.data.semantic_model import Dataset, JoinDecl, SchemaKey, Source

S = Cols(pascal_physical=True)

_DATE = "COALESCE({t}.[PayDate], {t}.[PayPeriodEnd])"
_LITE_DATE = 'COALESCE({t}."PayDate", {t}."PayPeriodEnd")'
_PAY_YEAR = (f"YEAR({_DATE})", f"CAST(strftime('%Y', {_LITE_DATE}) AS INTEGER)")
_PAY_MONTH = (f"(YEAR({_DATE}) * 100 + MONTH({_DATE}))", f"CAST(strftime('%Y%m', {_LITE_DATE}) AS INTEGER)")
_DEPENDS = ("PayDate", "PayPeriodEnd")

PAYROLL = Dataset(
    name="payroll", source=Source.LAKEHOUSE, schema=SchemaKey.SOURCE, table="Payroll",
    tenant_column="AccountId", employee_level=True, person_key="employee_id",
    period_columns=("pay_period_start", "pay_period_end", "pay_date"),
    grain="One row per employee per pay period per pay code, exactly as received.",
    description="The payroll rows before any engine rule: hours, wages, rate, pay code and location for every pay period.",
    joins=(
        JoinDecl("location", "location", (("location_id", "location_id"),)),
        JoinDecl("worksite", "location", (("worksite_location_id", "location_id"),)),
        JoinDecl("pay_code_info", "pay_code", (("pay_code_id", "pay_code_id"),)),
    ),
    columns=(
        S.blocked("employee_id", "int", "The source's employee key. Blocked: payroll rows are anonymous."),
        S.blocked("client_employee_id", "text", "The customer's own employee number. Blocked."),
        S.dim("entity_id", "int", "The legal entity the pay belongs to."),
        S.dim("location_id", "int", "The location on the payroll row; always present."),
        S.dim("worksite_location_id", "int", "The worksite, where the source supplies one. Jobs are counted at the worksite."),
        S.dim("pay_frequency_id", "int", "The source's pay-frequency key (lookup not supplied; lineage only)."),
        S.dim("pay_period_start", "date", "First day of the pay period."),
        S.dim("pay_period_end", "date", "Last day of the pay period."),
        S.dim("pay_date", "date", "Date paid. Blank in some rows."),
        S.measure("hours", "decimal", "Hours paid. Blank is not zero.", emp=True, unit="hours"),
        S.measure("wages", "decimal", "Wages paid.", emp=True, unit="USD"),
        S.measure("hourly_rate", "decimal", "Hourly rate, where supplied.", emp=True, unit="USD/hour"),
        S.flag("is_full_time", "Full-time marker from the source, where supplied."),
        S.flag("is_salaried", "Salaried marker from the source, where supplied."),
        S.dim("pay_code_id", "int", "Key into the client's pay codes; join pay_code_info for the code and its description."),
        S.dim("pay_year", "int", "Calendar year of the pay date (the period end when there is none). NOT the tax year, which follows the client's fiscal window.",
              physical="PayYear", expression=_PAY_YEAR, depends_on=_DEPENDS),
        S.dim("pay_month", "int", "Calendar month of the pay date as YYYYMM. Not a fiscal month.",
              physical="PayMonth", expression=_PAY_MONTH, depends_on=_DEPENDS),
    ),
    excluded_columns=(
        ("PayrollId", "Surrogate row key; it joins a row back to a person and has no analytic use."),
        ("InloadPayrollId", "Load-batch lineage, not a payroll fact."),
        ("CreateDate", "Load audit timestamp."),
        ("ModifyDate", "Load audit timestamp."),
        ("CreatedBy", "Loader user key."),
        ("ModifiedBy", "Loader user key."),
    ),
    engine_notes=(
        ("hours, wages", "Raw inputs. The engine applies the fiscal window, pay-code filter and BA rules before it counts, so sums here are not the engine's totals; employee_eligibility holds those."),
        ("pay_year", "A calendar year, not a tax year. For a tax-year answer use the engine tools or the Gold datasets."),
    ),
)

LOCATION = Dataset(
    name="location", source=Source.LAKEHOUSE, schema=SchemaKey.SOURCE, table="Location",
    tenant_column="AccountId", period_columns=("open_date", "close_date"),
    grain="One row per client worksite.",
    description="The client's locations: name, the client's own location code, status and open and close dates.",
    columns=(
        S.ident("location_id", "int", "The location key payroll rows carry."),
        S.dim("entity_id", "int", "The legal entity operating the location."),
        S.dim("location_name", "text", "The location's name, for example the town; use it to find the location key.", free_text=True),
        S.dim("client_location_id", "text", "The client's own code for the location."),
        S.dim("dba", "text", "Trading name.", free_text=True),
        S.dim("open_date", "date", "When the location opened; a site opened mid-year is not a site with missing months."),
        S.dim("close_date", "date", "When the location closed, if it did."),
        S.dim("location_status_id", "int", "The source's location status key."),
        S.dim("screening_status_id", "int", "The source's screening status key."),
    ),
    excluded_columns=(("AddressId", "Key into the address lookup, which has no client key; reachable only through a future declared join."),),
    engine_notes=(
        ("location_id", "Gold's worksite_id is the payroll's worksite location. Resolve a name here, then filter the Gold dataset on that id."),
    ),
)

PAY_CODE = Dataset(
    name="pay_code", source=Source.LAKEHOUSE, schema=SchemaKey.SOURCE, table="PayCode",
    tenant_column="AccountId",
    grain="One row per client pay code.",
    description="The client's pay codes, with whether each is ACA or FUTA wages and its category.",
    columns=(
        S.ident("pay_code_id", "int", "The pay-code key payroll rows carry."),
        S.dim("pay_code", "text", "The pay code as the client writes it.", free_text=True),
        S.dim("description", "text", "What the pay code means.", free_text=True),
        S.flag("is_aca", "Counts for ACA purposes."),
        S.flag("is_futa", "Counts as FUTA wages."),
        S.dim("pay_code_category_id", "int", "Category key; the lookup was not supplied, so whether a code counts toward a state credit is an open question."),
    ),
    engine_notes=(
        ("pay_code", "The engine's pay-code filter (BA-07) is authoritative for what counts; this lists what exists."),
    ),
)

SOURCE_DATASETS = (PAYROLL, LOCATION, PAY_CODE)
