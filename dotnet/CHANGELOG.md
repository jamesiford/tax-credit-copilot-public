# Changelog

All notable changes to the .NET port are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- The oracle is pinned to CPython 3.12 in code (parity/oracle.py, OracleInterpreter); PySum implements 3.12 exactly; goldens and the Unicode 15.0 tables were regenerated on 3.12; the 410 version-sensitive vectors are kept with both answers in parity/goldens/version-sensitive.jsonl.gz.

### Added
- Opt-in per-client projection cache (`SOURCE_CACHE_MODE=on`, default `off`; `SOURCE_CACHE_MB`, `SOURCE_CACHE_ACCOUNTS`, `SOURCE_VERSION_CHECK_SECONDS`): a singleton LRU of finished projections with single-flight loads, a fingerprint-plus-lookup-digest freshness check, a mandatory fresh check on every calculation run and claim assessment, and OpenTelemetry meter `TaxCredit.SourceCache`. See `docs/SCALE-S3-REPORT.md`.
- Solution skeleton under `dotnet/` (Domain, Application, Infrastructure, Api, ServiceDefaults, AppHost; Domain, Parity and Architecture test projects), central package management, `net10.0`, warnings as errors.
- `TaxCredit.Domain.Numerics`: Python compatibility layer (round, Decimal quantize, float repr/parse, floor division and modulo, compensated `sum`, stable sort, string and date semantics).
- `parity/export_primitives.py` and `parity/gen_unicode_tables.py` (new Python files only) and the primitives golden vector file.
- Calculation engine port (TaxCredit.Domain.Calculation): Pay Period and Min-Max methods, preprocessing, eligibility, headcount, fiscal windows, floors, calculation trail with evidence hash.
- Golden exporter (parity/export_goldens.py), engine CLI (parity/engine_cli.py), differential fuzzer, mutation self-test and benchmark.
- ADRs 0001-0008, findings, parity report, spike report.
