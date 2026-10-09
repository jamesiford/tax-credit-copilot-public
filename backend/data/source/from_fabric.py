"""Read the source schema tables back out of the Fabric Lakehouse.

The mirror of `to_delta.py`: OneLake Delta tables in the customer's source
shape, reconstructed into a `SourceDataset` so `to_bcs.source_to_bcs_rows` can
project them for the engine. That is the same projection tested by
`tests/test_source_roundtrip.py`, so what the app reads in production has already
been proven lossless against the reference dataset.

Tenant scoping
--------------
`for_account(...)` filters at the Delta layer, and `Payroll` is partitioned by
`AccountId`, so a single-tenant read touches only that tenant's files. Isolation
is physical rather than a predicate applied after loading everything.

Degradation
-----------
When Fabric is not configured, every call returns empty rather than raising, so
an offline demo stays deterministic — the same posture as
`tools/fabric_source.FabricEmployeesAdapter`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from config import SOURCE_SCHEMA

from .schema import (
    Account,
    Address,
    Employment,
    Entity,
    EntityFiscalYearRules,
    SourceDataset,
    Location,
    PayCode,
    PayFrequency,
    Payroll,
    StateCountyZip,
)
from .to_delta import TABLE_SPECS, table_uri


def _snake(name: str) -> str:
    """`PayPeriodStart` -> `pay_period_start`. Inverse of `to_delta._pascal`."""
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _coerce(value: Any, target: str) -> Any:
    """Delta gives back native types; nudge the few that need it.

    Dates arrive as `date` and decimals as `Decimal` — the whole point of
    storing real types — so this is mostly a passthrough with guards for the
    cases where pyarrow hands back a datetime or a float.
    """
    if value is None:
        return None
    if target == "date32":
        return value.date() if isinstance(value, datetime) else value
    if target.startswith("decimal"):
        return value if isinstance(value, Decimal) else Decimal(str(value))
    return value


def _rows_to(cls, records: list[dict[str, Any]], spec: dict[str, str]) -> list[Any]:
    """Rebuild dataclass instances from Delta rows."""
    built = []
    for rec in records:
        kwargs = {}
        for field_name, arrow_type in spec.items():
            pascal = "".join(p.capitalize() for p in field_name.split("_"))
            kwargs[field_name] = _coerce(rec.get(pascal), arrow_type)
        built.append(cls(**kwargs))
    return built


_CLASS_FOR: dict[str, Any] = {
    "Account": Account,
    "StateCountyZip": StateCountyZip,
    "Address": Address,
    "EntityFiscalYearRules": EntityFiscalYearRules,
    "Entity": Entity,
    "Location": Location,
    "PayFrequency": PayFrequency,
    "PayCode": PayCode,
    "Employment": Employment,
    "Payroll": Payroll,
}


# Reading a tenant means opening ten Delta tables over the network — roughly a
# minute for the reference client. `load_pay_periods()` is called per request, so
# without a cache the app is unusable.
#
# The lakehouse is a batch source that changes when someone reloads it, not
# per request, so a process-lifetime cache is the right shape. It is keyed by
# (workspace, lakehouse, schema, account) so switching tenant does not serve
# another tenant's rows. `clear_cache()` exists for the reload path and tests.
_DATASET_CACHE: dict[tuple[str, str, str, int], SourceDataset] = {}
_ACCOUNTS_CACHE: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
_LINEAGE_CACHE: dict[tuple[str, str, str, str], dict[str, Any]] = {}

# One credential for the process. `DefaultAzureCredential` caches tokens per
# instance, so building a new one per call re-probes IMDS every time — which on
# a developer machine is a guaranteed timeout before it falls through to the az
# CLI, on every single read.
_CREDENTIAL: Any = None

# OneLake on this capacity accepts connections slowly and erratically. Opening
# the tiny `Account` Delta log was measured at 13s, 22s, 13s, 38s and 29s on five
# consecutive attempts, and the front door answers an unauthenticated GET for the
# same URL in 0.7s — so the latency is in the storage path, not the network.
#
# `object_store` defaults to a 5s connect timeout, which on that path abandons
# connections that are alive but slow and retries them, adding load to the thing
# already struggling. It gives up after `retry_timeout`, surfacing as a 500 on
# every read: "client error (Connect) -> operation timed out ... after 10 retries".
#
# Waiting out a slow connect is strictly better than retrying it. The overall
# budget stays bounded so a genuine outage still fails in about a minute rather
# than hanging a request for several. These keys are honoured, not ignored:
# setting `connect_timeout` to 1ms fails in 0.0s.
_TRANSPORT_OPTIONS = {
    "connect_timeout": "60s",
    "timeout": "120s",
    "retry_timeout": "90s",
    "max_retries": "3",
}


def _storage_token() -> str:
    global _CREDENTIAL
    if _CREDENTIAL is None:
        from azure.identity import DefaultAzureCredential

        _CREDENTIAL = DefaultAzureCredential()
    return _CREDENTIAL.get_token("https://storage.azure.com/.default").token


def clear_cache() -> None:
    """Drop cached datasets. Call after reloading the lakehouse."""
    _DATASET_CACHE.clear()
    _ACCOUNTS_CACHE.clear()
    _LINEAGE_CACHE.clear()


@dataclass
class FabricLakehouseReader:
    """Reads the source schema tables (`SOURCE_SCHEMA`, default `tcc_source`)
    from a Fabric Lakehouse over OneLake."""

    workspace: str | None = None
    lakehouse: str | None = None
    schema: str = SOURCE_SCHEMA

    def __post_init__(self) -> None:
        self.workspace = self.workspace or os.getenv("FABRIC_WORKSPACE")
        self.lakehouse = self.lakehouse or os.getenv("FABRIC_LAKEHOUSE")

    def is_configured(self) -> bool:
        return bool(self.workspace) and bool(self.lakehouse)

    def _storage_options(self) -> dict[str, str]:
        return {
            "bearer_token": _storage_token(),
            "use_fabric_endpoint": "true",
            **_TRANSPORT_OPTIONS,
        }

    def _read(self, table: str, options: dict[str, str], account_id: int | None) -> list[dict[str, Any]]:
        from deltalake import DeltaTable

        uri = table_uri(
            table, workspace=self.workspace, lakehouse=self.lakehouse, schema=self.schema
        )
        dt = DeltaTable(uri, storage_options=options)

        # Push the tenant filter down. On Payroll this prunes partitions; on the
        # dimensions it is a cheap column filter.
        spec = TABLE_SPECS[table][1]
        if account_id is not None and "account_id" in spec:
            return dt.to_pyarrow_table(
                filters=[("AccountId", "=", account_id)]
            ).to_pylist()
        return dt.to_pyarrow_table().to_pylist()

    def list_accounts(self) -> list[dict[str, Any]]:
        """Every tenant in the lakehouse. Cheap — the Account table is tiny."""
        if not self.is_configured():
            return []
        key = (self.workspace, self.lakehouse, self.schema)
        if key not in _ACCOUNTS_CACHE:
            options = self._storage_options()
            _ACCOUNTS_CACHE[key] = self._read("Account", options, None)
        return _ACCOUNTS_CACHE[key]

    def table_lineage(self, table: str) -> dict[str, Any] | None:
        """Delta identity of one table: which version, how many files, how big.

        A Delta version is what makes a lakehouse read reproducible — it is the
        equivalent of the file hash the CSV adapter records, and without it a
        manifest naming this source is a pointer rather than a claim.

        Cached per process alongside the datasets. It is read on every workspace
        fingerprint check, and opening the Delta log plus acquiring a token each
        time cost ~9s a request. `clear_cache()` is the reload path.
        """
        if not self.is_configured():
            return None

        key = (self.workspace, self.lakehouse, self.schema, table)
        cached = _LINEAGE_CACHE.get(key)
        if cached is not None:
            return cached

        from deltalake import DeltaTable

        uri = table_uri(
            table, workspace=self.workspace, lakehouse=self.lakehouse, schema=self.schema
        )
        dt = DeltaTable(uri, storage_options=self._storage_options())
        adds = dt.get_add_actions()
        try:
            records = adds.to_pylist()
        except AttributeError:
            # Newer deltalake returns an arro3 table; both expose the Arrow C
            # stream, so pyarrow can adopt it without a copy of the data.
            import pyarrow as pa

            records = pa.table(adds).to_pylist()
        lineage = {
            "kind": "delta",
            "table": f"{self.schema}.{table}",
            "uri": uri,
            "version": dt.version(),
            "files": len(records),
            "bytes": sum(int(a.get("size_bytes") or 0) for a in records),
        }
        _LINEAGE_CACHE[key] = lineage
        return lineage

    def for_account(self, account_id: int) -> SourceDataset | None:
        """One tenant's full source dataset. Cached per process — see above."""
        if not self.is_configured():
            return None

        key = (self.workspace, self.lakehouse, self.schema, account_id)
        cached = _DATASET_CACHE.get(key)
        if cached is not None:
            return cached

        options = self._storage_options()

        raw = {t: self._read(t, options, account_id) for t in TABLE_SPECS}
        accounts = _rows_to(Account, raw["Account"], TABLE_SPECS["Account"][1])
        if not accounts:
            return None

        def build(table: str):
            cls = _CLASS_FOR[table]
            return _rows_to(cls, raw[table], TABLE_SPECS[table][1])

        # Dimensions without an account column are shared; scope them by the
        # keys this tenant actually references, so one tenant's read does not
        # drag in another's worksites.
        entities = build("Entity")
        locations = build("Location")
        address_ids = {loc.address_id for loc in locations}
        addresses = [a for a in build("Address") if a.address_id in address_ids]
        scz_ids = {a.state_county_zip_id for a in addresses}
        state_county_zips = [s for s in build("StateCountyZip") if s.state_county_zip_id in scz_ids]
        rule_ids = {e.fiscal_year_rules_id for e in entities}
        fiscal_rules = [r for r in build("EntityFiscalYearRules")
                        if r.fiscal_year_rules_id in rule_ids]

        payroll = build("Payroll")
        employee_ids = {p.employee_id for p in payroll}
        employments = [e for e in build("Employment") if e.employee_id in employee_ids]

        dataset = SourceDataset(
            account=accounts[0],
            entities=entities,
            locations=locations,
            addresses=addresses,
            state_county_zips=state_county_zips,
            employments=employments,
            pay_codes=build("PayCode"),
            pay_frequencies=build("PayFrequency"),
            fiscal_year_rules=fiscal_rules,
            payroll=payroll,
        )
        _DATASET_CACHE[key] = dataset
        return dataset

    def bcs_rows(self, account_id: int) -> list[dict[str, Any]]:
        """One tenant, projected straight into the shape the engine reads."""
        from .to_bcs import source_to_bcs_rows

        dataset = self.for_account(account_id)
        return source_to_bcs_rows(dataset) if dataset else []
