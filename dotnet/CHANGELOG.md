# Changelog

All notable changes to the .NET port are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Solution skeleton under `dotnet/` (Domain, Application, Infrastructure, Api, ServiceDefaults, AppHost; Domain, Parity and Architecture test projects), central package management, `net10.0`, warnings as errors.
- `TaxCredit.Domain.Numerics`: Python compatibility layer (round, Decimal quantize, float repr/parse, floor division and modulo, compensated `sum`, stable sort, string and date semantics).
- `parity/export_primitives.py` and `parity/gen_unicode_tables.py` (new Python files only) and the primitives golden vector file.
