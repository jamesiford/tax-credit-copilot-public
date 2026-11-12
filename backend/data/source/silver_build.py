"""Build and refresh the Silver table (`silver.py`) from a lake, one account at a time. [08.3, 08.4]

Works against any Delta location the reader can reach (a local lake in tests and development, the Fabric lakehouse when run
there): `uri` and `storage_options` say where Silver lives. Each account's partition is replaced by a predicate write, so a refresh
touches one account's files and no other's. An account is (re)built only when its recorded source version is not the current
Payroll Delta version, so an unchanged lake is a no-op.

Change detection here is by TABLE version: any new Payroll version marks every account stale. Per-account detection needs the
Change Data Feed (or a per-account high-water mark) on the source and is the next step; the table-level rule is the safe one.
"""
from __future__ import annotations

from typing import Any

from .silver import SILVER_TABLE, refresh_plan, silver_rows_from_dataset, to_arrow


def built_versions(uri: str, account_column: str, storage_options: dict | None = None) -> dict[int, int | None]:
    """{account: source version it was built from} for what Silver already holds (empty when there is no table yet)."""
    from deltalake import DeltaTable
    from deltalake.exceptions import TableNotFoundError

    try:
        table = DeltaTable(uri, storage_options=storage_options).to_pyarrow_table(columns=[account_column, "Source_Version"])
    except TableNotFoundError:
        return {}
    return {int(a): v for a, v in zip(table[account_column].to_pylist(), table["Source_Version"].to_pylist())}


def build_silver(reader: Any, uri: str, account_column: str, *, accounts: list[int] | None = None, force: bool = False,
                 storage_options: dict | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Build (or refresh) Silver for `accounts` (default: every account the source lists). Returns what it did."""
    from deltalake import write_deltalake

    version = reader._data_version()
    wanted = accounts if accounts is not None else [int(a["AccountId"]) for a in reader.list_accounts()]
    built = built_versions(uri, account_column, storage_options)
    todo = wanted if force else refresh_plan(built, wanted, version)
    report: dict[str, Any] = {"table": SILVER_TABLE, "source_version": version, "accounts_total": len(wanted),
                              "built": [], "skipped_unchanged": len(wanted) - len(todo), "dry_run": dry_run, "rows": 0}
    exists = bool(built)
    for account_id in todo:
        dataset = reader.for_account(account_id)
        if dataset is None:
            continue
        rows = silver_rows_from_dataset(dataset)
        report["built"].append(account_id)
        report["rows"] += len(rows)
        if dry_run:
            continue
        table = to_arrow(rows, account_column, version)
        if exists:  # replace this account's partition only
            write_deltalake(uri, table, mode="overwrite", predicate=f"{account_column} = {account_id}", storage_options=storage_options)
        else:
            write_deltalake(uri, table, mode="overwrite", partition_by=[account_column], storage_options=storage_options)
            exists = True
    return report
