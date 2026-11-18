# Changelog

All notable changes to the .NET port are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- Every `TCC_*` environment variable the .NET hosts, benches and test switches read was renamed without the product prefix (for example `TCC_PERSISTENCE_PROVIDER` is `PERSISTENCE_PROVIDER`, `TCC_PYTHON` is `ORACLE_PYTHON`, `TCC_RUN_BENCH` is `BENCH_RUN`). The old names are honoured for one release: `LegacySettingAliases` (hosts) and `LegacyTestEnvironment` (tests) copy an old value to its new name when the new one is unset, report the deprecated name only, and the new name wins. Full table in the root `CHANGELOG.md`.
- Local runs always use the live Lakehouse and the Warehouse named in `backend\.env` (`WAREHOUSE_SERVER` and `WAREHOUSE_DATABASE` are required with `LAKEHOUSE_SQL_SERVER` and `LAKEHOUSE_SQL_DATABASE`). `run-local.ps1`, `run-worker.ps1` and `configure-local.ps1` no longer default to a local SQLite file and the `-Persistence` switch is removed; `-Offline` (synthetic data, SQLite) is the only alternative.
- Gold persistence on SQL Server-family stores (Fabric Warehouse, Azure SQL, SQL Server) uses `SqlBulkCopy` inside the publish transaction instead of multi-row `INSERT` batches (kill switch `TCC_BULK_LOAD=off`); SQLite is unchanged. 400,000 `employee_period_fact` rows: 836 s to 16 s on a local SQL Server, 58 s on the live Warehouse. See `docs/SCALE-S5-REPORT.md`.
- A running queue item now renews its lease on its own task (`RUN_LEASE_RENEW_SECONDS`, default a third of `RUN_LEASE_SECONDS`, default 600); a write that outlives the lease no longer loses its work and re-runs. The local SQLite store uses WAL.
- The oracle is pinned to CPython 3.12 in code (parity/oracle.py, OracleInterpreter); PySum implements 3.12 exactly; goldens and the Unicode 15.0 tables were regenerated on 3.12; the 410 version-sensitive vectors are kept with both answers in parity/goldens/version-sensitive.jsonl.gz.

### Added
- `dotnet/deploy/sql/0100_dotnet_operational_objects.sql`: the four tables and one column only the .NET host uses (`tcc_ops.write_sequence`, `run_work_identity`, `run_source_observation`, `finding_audit`, `manual_override.write_order`); run it with writers stopped (see `COMPOSITION-SCHEMA-PROVISIONING.md`).
- Employee-grain retention: after the outermost commit, superseded runs beyond the newest N (`TCC_RETAIN_SUPERSEDED_RUNS`, default 2, `all` turns it off) lose their rows in `employee_period_fact`, `onezero_matrix` and `employee_eligibility`; manifests and unit-level tables are never touched.
- Opt-in per-client projection cache (`SOURCE_CACHE_MODE=on`, default `off`; `SOURCE_CACHE_MB`, `SOURCE_CACHE_ACCOUNTS`, `SOURCE_VERSION_CHECK_SECONDS`): a singleton LRU of finished projections with single-flight loads, a fingerprint-plus-lookup-digest freshness check, a mandatory fresh check on every calculation run and claim assessment, and OpenTelemetry meter `TaxCredit.SourceCache`. See `docs/SCALE-S3-REPORT.md`.
- Solution skeleton under `dotnet/` (Domain, Application, Infrastructure, Api, ServiceDefaults, AppHost; Domain, Parity and Architecture test projects), central package management, `net10.0`, warnings as errors.
- `TaxCredit.Domain.Numerics`: Python compatibility layer (round, Decimal quantize, float repr/parse, floor division and modulo, compensated `sum`, stable sort, string and date semantics).
- `parity/export_primitives.py` and `parity/gen_unicode_tables.py` (new Python files only) and the primitives golden vector file.
- Calculation engine port (TaxCredit.Domain.Calculation): Pay Period and Min-Max methods, preprocessing, eligibility, headcount, fiscal windows, floors, calculation trail with evidence hash.
- Golden exporter (parity/export_goldens.py), engine CLI (parity/engine_cli.py), differential fuzzer, mutation self-test and benchmark.
- ADRs 0001-0008, findings, parity report, spike report.
