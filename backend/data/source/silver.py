"""The Silver layer: engine-shaped payroll, partitioned by account, built once and read instead of raw payroll. [08.3]

What the engine reads is not the source's normalised tables: it is one row per employee per pay period with the worksite's
state and county, the unit id, the entity's FEIN, hours, wages, the pay date and the pay code, all joined. Building that
per request means reading five tables (and a whole `Address` or `Employment` if a filter is missed) and a projection
that costs seconds per hundred thousand rows. This layer does it ONCE, at load time, into a compact Delta table partitioned by
the tenant column, and the app reads one account's partition.

It is deliberately unaware of the app-owned lookups. The pay code is stored as the customer wrote it (with its category id);
the canonical category, the unmapped-code accounting and the `strict` policy are applied at READ time by `finalize_pay_codes`,
exactly as the raw path applies them, so an override authored tomorrow takes effect without a rebuild and a Silver row can never
carry a statutory decision that has since changed. Every Silver row records the source Payroll Delta version it was built from;
a refresh rebuilds only what that version no longer matches.

`tests/test_silver.py` proves the two paths give the same rows, and so the same certified figures.
"""
from __future__ import annotations

from datetime import date
from typing import Any

SILVER_TABLE = "tcc_silver_pay_period"

#: BCS key -> (Silver column, Arrow type). A leading underscore is not a safe Delta column prefix, so it is dropped and restored.
_COLUMNS: dict[str, tuple[str, str]] = {
    "Tax_Year": ("Tax_Year", "int32"), "Employee_ID": ("Employee_ID", "string"), "Job_Title": ("Job_Title", "string"),
    "Worksite_ID": ("Worksite_ID", "string"), "Work_State": ("Work_State", "string"), "Work_County": ("Work_County", "string"),
    "Entity_FEIN": ("Entity_FEIN", "string"), "Pay_Period_Start": ("Pay_Period_Start", "string"), "Pay_Period_End": ("Pay_Period_End", "string"),
    "Pay_Date": ("Pay_Date", "string"), "_Pay_Date_Imputed": ("Pay_Date_Imputed", "bool"), "Pay_Frequency": ("Pay_Frequency", "string"),
    "_Source_Pay_Frequency_Id": ("Source_Pay_Frequency_Id", "int64"), "Pay_Code": ("Pay_Code_Text", "string"),
    "_Source_Pay_Code": ("Source_Pay_Code", "string"), "_Pay_Code_Defaulted": ("Pay_Code_Defaulted", "bool"),
    "Hours_Worked": ("Hours_Worked", "double"), "Gross_Wages": ("Gross_Wages", "double"),
    "_Source_Payroll_Id": ("Source_Payroll_Id", "int64"), "_Source_Account_Id": ("Source_Account_Id", "int64"),
}
_CATEGORY = "Source_Pay_Code_Category_Id"
_VERSION = "Source_Version"


def silver_rows_from_dataset(dataset: Any) -> list[dict[str, Any]]:
    """Engine rows for one account from its source dataset, with the pay code left as the customer wrote it."""
    from .to_bcs import source_to_bcs_rows

    rows = source_to_bcs_rows(dataset, resolve_pay_codes=False)
    category = {c.pay_code_id: c.pay_code_category_id for c in dataset.pay_codes}
    by_payroll = {p.payroll_id: p.pay_code_id for p in dataset.payroll}
    for r in rows:
        r[_CATEGORY] = category.get(by_payroll.get(r["_Source_Payroll_Id"]))
    return rows


def to_arrow(rows: list[dict[str, Any]], account_column: str, version: int | None):
    """One Arrow table of Silver rows for a single account (the tenant column and the source version ride along)."""
    import pyarrow as pa

    types = {"int32": pa.int32(), "int64": pa.int64(), "string": pa.string(), "bool": pa.bool_(), "double": pa.float64()}
    columns = {name: [r[key] for r in rows] for key, (name, _) in _COLUMNS.items()}
    arrays = {name: pa.array(values, type=types[_COLUMNS[key][1]]) for (key, (name, _)), values in zip(_COLUMNS.items(), columns.values())}
    arrays[_CATEGORY] = pa.array([r[_CATEGORY] for r in rows], type=pa.int64())
    arrays[account_column] = pa.array([r["_Source_Account_Id"] for r in rows], type=pa.int64())
    arrays[_VERSION] = pa.array([version] * len(rows), type=pa.int64())
    return pa.table(arrays)


def from_silver(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Silver records back into engine rows (the pay code still raw; `finalize_pay_codes` resolves it)."""
    out = []
    for rec in records:
        row = {key: rec[name] for key, (name, _) in _COLUMNS.items()}
        row["_Pay_Code_Category_Id"] = rec.get(_CATEGORY)
        out.append(row)
    return out


def finalize_pay_codes(rows: list[dict[str, Any]], account_id: int, policy: str | None = None) -> list[dict[str, Any]]:
    """Apply the pay-code lookup to Silver rows: canonical category, flags, and the `strict` block. Same outcome as the raw path."""
    from data.lookups import PayCodeResolver

    resolver = PayCodeResolver(account_id, policy)
    memo: dict[tuple, tuple[str | None, str, bool]] = {}
    unmapped: dict[str, int] = {}
    for row in rows:
        row["_Pay_Code_Unmapped"] = False
        text, category = row["Pay_Code"], row.pop("_Pay_Code_Category_Id")
        if row["_Pay_Code_Defaulted"]:
            continue
        key = (text, category)
        if key not in memo:
            memo[key] = resolver.resolve(text, category)
        canonical = memo[key][0]
        if canonical is None:
            row["_Pay_Code_Unmapped"] = True
            unmapped[text] = unmapped.get(text, 0) + 1
        else:
            row["Pay_Code"] = canonical
    if unmapped and resolver.policy == "strict":
        from application.errors import UnmappedPayCodes

        raise UnmappedPayCodes(tuple(sorted(unmapped)), sum(unmapped.values()))
    return rows


def refresh_plan(built: dict[int, int | None], accounts: list[int], current_version: int | None) -> list[int]:
    """Which accounts need (re)building: those never built, or built from a Payroll version that is no longer the current one."""
    return [a for a in accounts if a not in built or built[a] != current_version]
