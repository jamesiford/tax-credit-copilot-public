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

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from config import SOURCE_SCHEMA, get_settings

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
from .book_keys import book_entry
from . import read_stats
from .read_cache import BoundedCache, NegativeCache, SingleFlight
from .mapping import column, engine_fields, mapping, optional_tables, table_map
from .mapping.columns import resolve_for
from .onelake import physical_table, storage_options, storage_token, table_uri
from .to_delta import TABLE_SPECS


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
        return value if isinstance(value, Decimal) else _decimal(value)
    return value


def _decimal(value: Any) -> Decimal | None:
    """A number the source stored as text (`HourlyWage` is a string in the DDL) or as a float; blank or junk is None."""
    try:
        return Decimal(str(value).strip().replace(",", "").lstrip("$"))
    except (InvalidOperation, ValueError):
        return None


def _rows_to(cls, records: list[dict[str, Any]], spec: dict[str, str]) -> list[Any]:
    """Rebuild dataclass instances from rows keyed by LOGICAL field name (`_read` renames the columns)."""
    built = []
    for rec in records:
        kwargs = {}
        for field_name, arrow_type in spec.items():
            kwargs[field_name] = _coerce(rec.get(field_name), arrow_type)
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


log = logging.getLogger(__name__)

_WARNED_MISSING: set[str] = set()

# Reading a tenant means opening ten Delta tables over the network, so a read is cached, and the cache is BOUNDED: an
# estimated byte budget and an entry count (`SOURCE_CACHE_MB`, `SOURCE_CACHE_ACCOUNTS`), least recently used out first. It is
# keyed by (workspace, lakehouse, schema, account, the Payroll Delta VERSION), so a reload of the lake is noticed (within
# `SOURCE_VERSION_CHECK_SECONDS`) and only the changed account is read again; switching tenant never serves another's rows.
# Concurrent requests for one account share one read (single-flight), and an unknown id is remembered as unknown for a short
# time. `clear_cache()` is the reload path and the tests'.
_DATASET_CACHE: BoundedCache | None = None
_NEGATIVE: NegativeCache | None = None
_FLIGHT = SingleFlight()
_VERSIONS: dict[tuple[str, str, str], tuple[float, int | None]] = {}
_ACCOUNTS_CACHE: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
_LINEAGE_CACHE: dict[tuple[str, str, str, str], dict[str, Any]] = {}
_ROW_ESTIMATE_CACHE: dict[tuple[str, str, str, str], int | None] = {}
_COLUMN_CACHE: dict[str, dict[str, str]] = {}

# The credential is shared by the whole process (`infrastructure/azure_credential.py`),
# and so is the token it mints: `DefaultAzureCredential` caches nothing for the CLI
# credentials, which on a developer machine means an `az` subprocess per call.

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
    return storage_token()


def _dataset_cache() -> BoundedCache:
    global _DATASET_CACHE
    if _DATASET_CACHE is None:
        settings = get_settings().source_model
        _DATASET_CACHE = BoundedCache(settings.cache_accounts, settings.cache_mb * 1_000_000)
    return _DATASET_CACHE


def _negative() -> NegativeCache:
    global _NEGATIVE
    if _NEGATIVE is None:
        _NEGATIVE = NegativeCache(min(60, get_settings().source_model.version_check_seconds))
    return _NEGATIVE


def clear_cache() -> None:
    """Drop cached datasets. Call after reloading the lakehouse."""
    global _DATASET_CACHE, _NEGATIVE
    _DATASET_CACHE = _NEGATIVE = None
    _VERSIONS.clear()
    _ACCOUNTS_CACHE.clear()
    _LINEAGE_CACHE.clear()
    _ROW_ESTIMATE_CACHE.clear()
    _COLUMN_CACHE.clear()


@dataclass
class FabricLakehouseReader:
    """Reads the source schema tables (`SOURCE_SCHEMA`, default `tcc_source`)
    from a Fabric Lakehouse over OneLake."""

    workspace: str | None = None
    lakehouse: str | None = None
    schema: str = SOURCE_SCHEMA

    def __post_init__(self) -> None:
        configured = get_settings().data_source
        self.workspace = self.workspace or configured.fabric_workspace
        self.lakehouse = self.lakehouse or configured.fabric_lakehouse

    def is_configured(self) -> bool:
        return bool(self.workspace) and bool(self.lakehouse)

    def require_configured(self) -> None:
        """Raise `SourceNotConfigured`, naming exactly the settings still unset."""
        if self.is_configured():
            return
        from application.errors import SourceNotConfigured

        raise SourceNotConfigured(self.missing_settings())

    def missing_settings(self) -> tuple[str, ...]:
        """The settings a person must set, so an error names them rather than saying "not configured"."""
        return tuple(
            name for name, value in (("FABRIC_WORKSPACE", self.workspace), ("FABRIC_LAKEHOUSE", self.lakehouse))
            if not value
        )

    def _storage_options(self) -> dict[str, str]:
        return storage_options(_storage_token(), _TRANSPORT_OPTIONS)

    def _read(self, table: str, options: dict[str, str], account_id: int | None) -> list[dict[str, Any]]:
        """One table's rows for one tenant (or all rows when there is no tenant or the table has no tenant column)."""
        return self._scan(table, options, tenant=account_id)

    def _read_keyed(self, table: str, options: dict[str, str], key: str, ids: set) -> list[dict[str, Any]]:
        """The rows of a table that has NO tenant column, for the keys one tenant references: never the whole table."""
        return self._scan(table, options, key=key, ids=ids) if ids else []

    def _scan(self, table: str, options: dict[str, str], *, tenant: int | None = None, key: str | None = None, ids: set | None = None) -> list[dict[str, Any]]:
        """The one place a Delta table is read: filters pushed down, only the engine's columns, counted, size-guarded.

        A tenant read prunes on the partition column. A keyed read pushes a range filter on the key (row-group statistics
        skip what cannot match) and then semi-joins in Arrow, so a 363-million-row `Address` table is read for the
        addresses of one account's locations and not in full.
        """
        import pyarrow as pa
        import pyarrow.compute as pc
        from deltalake import DeltaTable

        started = time.perf_counter()
        uri = table_uri(table, workspace=self.workspace, lakehouse=self.lakehouse, schema=self.schema)
        dt = DeltaTable(uri, storage_options=options)
        found = self._columns_of(table, uri, [f.name for f in dt.schema().fields])
        tenant_field = table_map(table).tenant_field
        wanted = engine_fields(table) | {name for name in (tenant_field, key) if name}
        columns = [actual for name, actual in found.items() if name in wanted]
        filters = None
        if tenant is not None and tenant_field in found:
            filters = [(found[tenant_field], "=", tenant)]
        elif key is not None and key in found:
            filters = [(found[key], ">=", min(ids)), (found[key], "<=", max(ids))]
        arrow = dt.to_pyarrow_table(columns=columns, filters=filters)
        if key is not None and key in found:
            arrow = arrow.filter(pc.is_in(arrow[found[key]], value_set=pa.array(sorted(ids))))
        limit = get_settings().source_model.max_account_rows
        if tenant is not None and filters is not None and arrow.num_rows > limit:
            from application.errors import AccountTooLarge

            raise AccountTooLarge(tenant, arrow.num_rows, limit)
        read_stats.record_read(table, arrow.num_rows, arrow.nbytes, arrow.num_columns, time.perf_counter() - started, filtered=filters is not None)
        inverse = {actual: name for name, actual in found.items()}
        return arrow.rename_columns([inverse[c] for c in arrow.column_names]).to_pylist()

    def _columns_of(self, table: str, uri: str, actual: list[str]) -> dict[str, str]:
        """logical field -> actual column for this table, resolved once and cached; a missing required field raises."""
        cached = _COLUMN_CACHE.get(uri)
        if cached is None:
            resolution = resolve_for(mapping(), table, actual)
            if not resolution.ok:
                from application.errors import SourceSchemaMismatch

                raise SourceSchemaMismatch(table, physical_table(table), resolution.missing_required)
            if resolution.missing_optional:
                log.warning("source table %s has no column for optional field(s) %s; they read as empty",
                            table, ", ".join(resolution.missing_optional))
            cached = _COLUMN_CACHE[uri] = resolution.found
        return cached

    def _read_table(self, table: str, options: dict[str, str], account_id: int, missing: list[str]) -> list[dict[str, Any]]:
        """`_read`, except that an optional table that is absent is "no rows", said once, and recorded.

        Only a missing table is tolerated. A table that exists but cannot be read (a timeout, a 403) is an
        outage and raises, so "could not read" and "read, found none" stay different facts.
        """
        reasons = optional_tables()
        if table not in reasons:
            return self._read(table, options, account_id)
        from deltalake.exceptions import TableNotFoundError

        try:
            return self._read(table, options, account_id)
        except TableNotFoundError:
            missing.append(table)
            if table not in _WARNED_MISSING:
                _WARNED_MISSING.add(table)
                log.warning(
                    "source table %s (%s) is absent from the lakehouse; continuing with no rows. %s",
                    table, physical_table(table), reasons[table],
                )
            return []

    def actual_schemas(self) -> dict[str, dict[str, str] | None]:
        """logical table -> {column: Delta type} for every mapped table, or None where the table is absent. No data is read."""
        from deltalake import DeltaTable
        from deltalake.exceptions import TableNotFoundError

        options, out = self._storage_options(), {}
        for table in TABLE_SPECS:
            uri = table_uri(table, workspace=self.workspace, lakehouse=self.lakehouse, schema=self.schema)
            try:
                fields = DeltaTable(uri, storage_options=options).schema().fields
                out[table] = {f.name: str(getattr(f.type, "type", f.type)) for f in fields}
            except TableNotFoundError:
                out[table] = None
        return out

    def _read_keyed_table(self, table: str, options: dict[str, str], key: str, ids: set, missing: list[str]) -> list[dict[str, Any]]:
        """`_read_keyed`, with an absent optional table read as "no rows" (said once, and recorded), as `_read_table` does."""
        reasons = optional_tables()
        if table not in reasons:
            return self._read_keyed(table, options, key, ids)
        from deltalake import DeltaTable
        from deltalake.exceptions import TableNotFoundError

        try:
            if not ids:  # nothing to look up, but an absent optional table is still worth saying
                uri = table_uri(table, workspace=self.workspace, lakehouse=self.lakehouse, schema=self.schema)
                if not DeltaTable.is_deltatable(uri, storage_options=options):
                    raise TableNotFoundError(uri)
            return self._read_keyed(table, options, key, ids)
        except TableNotFoundError:
            missing.append(table)
            if table not in _WARNED_MISSING:
                _WARNED_MISSING.add(table)
                log.warning("source table %s (%s) is absent from the lakehouse; continuing with no rows. %s", table, physical_table(table), reasons[table])
            return []

    def fiscal_year_rules(self, account_id: int) -> list[EntityFiscalYearRules]:
        """One client's fiscal rules from two small tables, never from payroll.

        `Entity` is read with the account filter pushed down and `EntityFiscalYearRules` is a lookup,
        so this is a bounded read where `for_account` would open ten tables including every payroll
        row. A rules table that is absent reads as no rules (said in the log): "read, found none".
        """
        options = self._storage_options()
        missing: list[str] = []
        entities = _rows_to(Entity, self._read_table("Entity", options, account_id, missing), TABLE_SPECS["Entity"][1])
        wanted = {e.fiscal_year_rules_id for e in entities}
        rules = _rows_to(
            EntityFiscalYearRules,
            self._read_table("EntityFiscalYearRules", options, account_id, missing),
            TABLE_SPECS["EntityFiscalYearRules"][1],
        )
        return sorted((r for r in rules if r.fiscal_year_rules_id in wanted), key=lambda r: r.fiscal_year_rules_id)

    def list_accounts(self) -> list[dict[str, Any]]:
        """Every tenant in the lakehouse. Cheap — the Account table is tiny."""
        if not self.is_configured():
            return []
        key = (self.workspace, self.lakehouse, self.schema)
        if key not in _ACCOUNTS_CACHE:
            options = self._storage_options()
            _ACCOUNTS_CACHE[key] = [book_entry(r) for r in self._read("Account", options, None)]
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
            "table": ".".join(part for part in (self.schema, physical_table(table)) if part),
            "uri": uri,
            "version": dt.version(),
            "files": len(records),
            "bytes": sum(int(a.get("size_bytes") or 0) for a in records),
        }
        _LINEAGE_CACHE[key] = lineage
        return lineage

    def table_row_estimate(self, table: str) -> int | None:
        """The table's row count from the Delta log's per-file statistics (no data is read), or None.

        None when the writer recorded no statistics, which is different from a table of zero rows.
        Cached with the lineage: the log is read once per process.
        """
        key = (self.workspace, self.lakehouse, self.schema, table)
        if key in _ROW_ESTIMATE_CACHE:
            return _ROW_ESTIMATE_CACHE[key]
        from deltalake import DeltaTable

        uri = table_uri(table, workspace=self.workspace, lakehouse=self.lakehouse, schema=self.schema)
        adds = DeltaTable(uri, storage_options=self._storage_options()).get_add_actions()
        try:
            records = adds.to_pylist()
        except AttributeError:
            import pyarrow as pa

            records = pa.table(adds).to_pylist()
        counts = [a.get("num_records") for a in records]
        _ROW_ESTIMATE_CACHE[key] = None if not counts or any(c is None for c in counts) else sum(int(c) for c in counts)
        return _ROW_ESTIMATE_CACHE[key]

    def _data_version(self) -> int | None:
        """The Payroll table's Delta version, re-checked at most every `SOURCE_VERSION_CHECK_SECONDS`.

        Opening a Delta log can take tens of seconds on a slow capacity, so the check is rationed. None when it cannot be
        read (the previous answer is kept if there is one): the cache then simply does not notice a reload until it can.
        """
        key = (self.workspace, self.lakehouse, self.schema)
        known = _VERSIONS.get(key)
        if known and time.monotonic() - known[0] < get_settings().source_model.version_check_seconds:
            return known[1]
        try:
            from deltalake import DeltaTable

            uri = table_uri("Payroll", workspace=self.workspace, lakehouse=self.lakehouse, schema=self.schema)
            version = DeltaTable(uri, storage_options=self._storage_options()).version()
        except Exception as exc:  # noqa: BLE001 - a version check that fails must not fail the read it guards
            log.warning("could not read the Payroll Delta version (%s); keeping the last known one", type(exc).__name__)
            version = known[1] if known else None
        _VERSIONS[key] = (time.monotonic(), version)
        return version

    def for_account(self, account_id: int) -> SourceDataset | None:
        """One tenant's full source dataset, read once: cached (bounded), single-flight, keyed by the data version.

        An id that does not exist is found out from the (tiny, tenant-filtered) `Account` read and remembered, instead
        of being discovered after every other table has been read.
        """
        if not self.is_configured():
            return None
        key = (self.workspace, self.lakehouse, self.schema, account_id)
        if _negative().has(key):
            read_stats.record_cache("negative_hits")
            return None
        full_key = (*key, self._data_version())
        cache = _dataset_cache()
        cached = cache.get(full_key)
        if cached is not None:
            read_stats.record_cache("hits")
            return cached
        read_stats.record_cache("misses")
        return _FLIGHT.do(full_key, lambda: self._load_account(account_id, key, full_key))

    def _rows(self, table: str, options: dict[str, str], tenant: int | None, missing: list[str]) -> list[Any]:
        return _rows_to(_CLASS_FOR[table], self._read_table(table, options, tenant, missing), TABLE_SPECS[table][1])

    def _keyed(self, table: str, options: dict[str, str], key: str, ids: set, missing: list[str]) -> list[Any]:
        return _rows_to(_CLASS_FOR[table], self._read_keyed_table(table, options, key, ids, missing), TABLE_SPECS[table][1])

    def _load_account(self, account_id: int, key: tuple, full_key: tuple) -> SourceDataset | None:
        """Read one tenant: the tenant-filtered tables first, then each tenant-less table by the keys they reference."""
        options, missing = self._storage_options(), []
        accounts = self._rows("Account", options, account_id, missing)
        if not accounts:
            _negative().add(key)
            return None
        entities, locations = self._rows("Entity", options, account_id, missing), self._rows("Location", options, account_id, missing)
        pay_codes, payroll = self._rows("PayCode", options, account_id, missing), self._rows("Payroll", options, account_id, missing)
        addresses = self._keyed("Address", options, "address_id", {loc.address_id for loc in locations if loc.address_id is not None}, missing)
        dataset = SourceDataset(
            account=accounts[0], entities=entities, locations=locations, addresses=addresses,
            state_county_zips=self._keyed("StateCountyZip", options, "state_county_zip_id",
                                          {a.state_county_zip_id for a in addresses if a.state_county_zip_id is not None}, missing),
            employments=self._keyed("Employment", options, "employee_id", {p.employee_id for p in payroll}, missing),
            pay_codes=pay_codes, pay_frequencies=self._rows("PayFrequency", options, account_id, missing),
            fiscal_year_rules=self._keyed("EntityFiscalYearRules", options, "fiscal_year_rules_id",
                                          {e.fiscal_year_rules_id for e in entities if e.fiscal_year_rules_id is not None}, missing),
            payroll=payroll, missing_tables=tuple(missing),
        )
        _dataset_cache().put(full_key, dataset, supersedes=lambda k: len(k) == 5 and k[:4] == key and k != full_key)
        return dataset

    def _silver_uri(self) -> str:
        """Where this lake's Silver table is: next to the Payroll table, under its own name."""
        from .silver import SILVER_TABLE

        payroll = table_uri("Payroll", workspace=self.workspace, lakehouse=self.lakehouse, schema=self.schema)
        return payroll.rsplit("/", 1)[0] + "/" + SILVER_TABLE

    def silver_rows(self, account_id: int) -> list[dict[str, Any]] | None:
        """One account's Silver partition as engine rows (pay code still raw), or None when there is none. Cached like a dataset."""
        from types import SimpleNamespace

        from deltalake import DeltaTable
        from deltalake.exceptions import TableNotFoundError

        from .silver import from_silver

        key = (self.workspace, self.lakehouse, self.schema, account_id, "silver", self._data_version())
        cached = _dataset_cache().get(key)
        if cached is not None:
            read_stats.record_cache("hits")
            return cached.payroll
        started = time.perf_counter()
        try:
            dt = DeltaTable(self._silver_uri(), storage_options=self._storage_options())
        except TableNotFoundError:
            return None
        tenant = next((f.name for f in dt.schema().fields if f.name.lower() == column("Payroll", "account_id").lower()), None)
        arrow = dt.to_pyarrow_table(filters=[(tenant, "=", account_id)]) if tenant else None
        if arrow is None or arrow.num_rows == 0:
            return None
        read_stats.record_read("Silver", arrow.num_rows, arrow.nbytes, arrow.num_columns, time.perf_counter() - started, filtered=True)
        rows = from_silver(arrow.to_pylist())
        _dataset_cache().put(key, SimpleNamespace(payroll=rows), supersedes=lambda k: k[:4] == key[:4] and k[4:5] == ("silver",) and k != key)
        return rows

    def bcs_rows(self, account_id: int) -> list[dict[str, Any]]:
        """One tenant, projected straight into the shape the engine reads: from Silver when it is enabled and built, else raw."""
        from .to_bcs import source_to_bcs_rows

        mode = get_settings().source_model.silver
        if mode != "off":
            silver = self.silver_rows(account_id)
            if silver is not None:
                from .silver import finalize_pay_codes

                return finalize_pay_codes([dict(r) for r in silver], account_id)
            if mode == "require":
                from application.errors import SilverNotBuilt

                raise SilverNotBuilt(account_id)
        dataset = self.for_account(account_id)
        return source_to_bcs_rows(dataset) if dataset else []
