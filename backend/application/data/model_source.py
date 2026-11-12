"""Lakehouse source datasets: the payroll as the customer's own system holds it. [CH-16a, 06.6]

Names and shapes are the source schema's (`data/source/schema.py`); the PHYSICAL table and column names come
from the source mapping (`data/source/mapping`), so a renamed column changes a mapping file and nothing here.
This is the raw material, before the engine's rules: it holds pay codes the engine filters out and pay periods
the fiscal window excludes, so a figure here can legitimately differ from the engine's. For the credit,
eligibility or the headcount the engine concluded, the fixed tools are authoritative.

Only tables that carry the client key are datasets. `Employment` names the employee but not the account, so it
cannot be scoped to a client and is excluded; the address, county and frequency lookups are shared reference
data with no client key.

The two employee identifiers are `blocked`. The source holds no record token (a token is derived per programme
and tax year by the engine), so payroll rows are anonymous: pay data per person-period with nothing to say whose.

The datasets are BUILT (`source_datasets()`), not constants, because the mapping in force decides their physical
names and the `null_pay_date` policy decides what a derived pay year means.
"""
from __future__ import annotations

from application.data.model_dsl import Cols
from application.data.semantic_model import Dataset, JoinDecl, SchemaKey, Source
from application.data import source_names as M

_PAY = "Payroll"


def _pay_expressions() -> tuple[tuple[str, str], tuple[str, str], tuple[str, ...]]:
    """`pay_year`, `pay_month` and the physical columns they read, under the `null_pay_date` policy in force."""
    paid, ended = M.column(_PAY, "pay_date"), M.column(_PAY, "pay_period_end")
    if M.null_pay_date_mode() == "exclude":
        tsql, lite = "{t}.[%s]" % paid, '{t}."%s"' % paid
    else:
        tsql, lite = "COALESCE({t}.[%s], {t}.[%s])" % (paid, ended), 'COALESCE({t}."%s", {t}."%s")' % (paid, ended)
    year = (f"YEAR({tsql})", f"CAST(strftime('%Y', {lite}) AS INTEGER)")
    month = (f"(YEAR({tsql}) * 100 + MONTH({tsql}))", f"CAST(strftime('%Y%m', {lite}) AS INTEGER)")
    return year, month, (paid, ended)


def _excluded(table: str, *items: tuple[str, str]) -> tuple[tuple[str, str], ...]:
    """Columns the model leaves out, given by logical field and reported by the physical column that carries it."""
    return tuple((M.column(table, name), reason) for name, reason in items)


def _payroll_columns(S: Cols, year, month, depends) -> tuple:
    """The payroll columns; the derived pay year and month carry the expressions for the policy in force."""
    return (
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
              physical="PayYear", expression=year, depends_on=depends),
        S.dim("pay_month", "int", "Calendar month of the pay date as YYYYMM. Not a fiscal month.",
              physical="PayMonth", expression=month, depends_on=depends),
    )


def _payroll() -> Dataset:
    S = Cols(source_table=_PAY)
    year, month, depends = _pay_expressions()
    return Dataset(
        name="payroll", source=Source.LAKEHOUSE, schema=SchemaKey.SOURCE, table=M.physical_table(_PAY),
        tenant_column=M.tenant_column(_PAY), employee_level=True, person_key="employee_id",
        period_columns=("pay_period_start", "pay_period_end", "pay_date"),
        grain="One row per employee per pay period per pay code, exactly as received.",
        description="The payroll rows before any engine rule: hours, wages, rate, pay code and location for every pay period.",
        joins=(
            JoinDecl("location", "location", (("location_id", "location_id"),)),
            JoinDecl("worksite", "location", (("worksite_location_id", "location_id"),)),
            JoinDecl("pay_code_info", "pay_code", (("pay_code_id", "pay_code_id"),)),
        ),
        columns=_payroll_columns(S, year, month, depends),
        excluded_columns=_excluded(
            _PAY,
            ("payroll_id", "Surrogate row key; it joins a row back to a person and has no analytic use."),
            ("inload_payroll_id", "Load-batch lineage, not a payroll fact."),
            ("create_date", "Load audit timestamp."),
            ("modify_date", "Load audit timestamp."),
            ("created_by", "Loader user key."),
            ("modified_by", "Loader user key."),
        ),
        engine_notes=(
            ("hours, wages", "Raw inputs. The engine applies the fiscal window, pay-code filter and BA rules before it counts, so sums here are not the engine's totals; employee_eligibility holds those."),
            ("pay_year", "A calendar year, not a tax year. For a tax-year answer use the engine tools or the Gold datasets."),
        ),
    )


def _location() -> Dataset:
    S = Cols(source_table="Location")
    return Dataset(
        name="location", source=Source.LAKEHOUSE, schema=SchemaKey.SOURCE, table=M.physical_table("Location"),
        tenant_column=M.tenant_column("Location"), period_columns=("open_date", "close_date"),
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
        excluded_columns=_excluded("Location", ("address_id", "Key into the address lookup, which has no client key; reachable only through a future declared join.")),
        engine_notes=(
            ("location_id", "Gold's worksite_id is the payroll's worksite location. Resolve a name here, then filter the Gold dataset on that id."),
        ),
    )


def _pay_code() -> Dataset:
    S = Cols(source_table="PayCode")
    return Dataset(
        name="pay_code", source=Source.LAKEHOUSE, schema=SchemaKey.SOURCE, table=M.physical_table("PayCode"),
        tenant_column=M.tenant_column("PayCode"),
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


def source_datasets() -> tuple[Dataset, ...]:
    """The lakehouse datasets under the mapping and policies in force now."""
    return (_payroll(), _location(), _pay_code())
