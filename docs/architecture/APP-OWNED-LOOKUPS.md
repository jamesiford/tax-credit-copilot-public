# App-owned lookups

Four lookups are referenced by the source tables and are **not in the schema the customer shared**: `PayCodeCategory`,
`EntityFiscalYearRules`, `PayFrequency` and `IndustryType`. The app has to work correctly with them present, overridden,
seeded, empty or absent, and a missing lookup must never silently change a statutory result.

## Decision: they live in the app, not in the customer's lakehouse

The lakehouse is the customer's system of record and we read it read-only. A table we authored there could collide with
one they supply later, and a lakehouse is a poor place to author, audit and version small edits. So each lookup is resolved
in the application, by key, after the account-scoped read, through one `LookupResolver`. Nothing is ever joined across stores
in SQL and nothing is joined onto the large payroll table: the lookups are tiny.

## Provider order

`source -> override -> seed -> default -> none`

| Provider | What it is |
| --- | --- |
| `source` | A table in the customer's estate under its mapped name, when present with rows. Read-only |
| `override` | App-owned rows in `tcc_ops.lookup_override`, per client (`client_id` = the account) or global (`client_id` = 0), effective-dated, with `authored_by`, `authored_on`, `basis`, `inferred`. Every change appends `tcc_ops.lookup_audit`. A new value supersedes the live row; nothing is deleted |
| `seed` | A versioned file `backend/rules/lookups/<name>.v<N>.json` with provenance (`authored_by`, `authored_on`, `basis`, `inferred`). The highest version wins |
| `default` | Blank or a documented default, for display-only lookups |
| `none` | Absent, with a defined consequence |

## The lookups

| Lookup | Statute-affecting | Key | Providers in use | If missing |
| --- | --- | --- | --- | --- |
| `pay_code_category` | **yes** (BA-07) | normalised pay-code text or category id; the most specific match wins: client code, client category, global code, global category | override, seed (inferred) | An unmapped code is dropped by the state's whitelist and eligibility reads zero. So: counted, flagged, and blocked under `strict` |
| `entity_fiscal_year_rules` | **yes** (BA-01) | the account (and entity), effective-dated | source, override | A calendar window is assumed and flagged `assumed`; `strict` blocks |
| `pay_frequency` | no | (dropped) | none: the label is derived from the measured period span (BA-03); the raw id is lineage | nothing |
| `industry_type` | no (display only) | industry id | seed (inferred) | the industry shows no name; the raw id is kept |

## Policy

Per lookup: `strict` (a missing lookup blocks the affected calculation with a message that names what is missing and the
remedy) or `assume` (use the next provider and flag it). Never assumed silently.

- `PAY_CODE_POLICY`: default `strict` for `DATA_CLASSIFICATION=customer`, where the seed is a convention and is **not** trusted,
  so nothing is mapped until somebody authors the mapping; `assume` otherwise. Under `assume` an unmapped code passes through
  unchanged (the rule pack's whitelist then excludes it), flagged on the row and counted.
- `FISCAL_RULES_POLICY`: default `assume` (the flagged calendar window); `strict` blocks.

## What is visible

- Every row carries `_Pay_Code_Unmapped` / `_Pay_Code_Defaulted` and `_Pay_Date_Imputed`; `projection_controls` reports
  `pay_codes` (policy, distinct and unmapped codes, rows unmapped, how many resolved by an inferred seed, providers) and
  `rows_with_no_county`.
- The fiscal window carries its provenance and `assumed` flag from the source through the resolver
  (`fiscal_window_for_state_year`) to each claim cell (`fiscal_window`).
- The startup log, the `/api/ready` verdict and `scripts/validate-source-schema.py` list every lookup with its status
  (`source`, `override`, `seed v1 (inferred)`, `default`, `missing (strict)`) and what it affects.

## Authoring

`python scripts/lookups.py list|show|import|export|diff|audit` (needs `LOOKUP_STORE=sqlite` or `warehouse`). `import` takes a CSV
(`kind,key,value`) or JSON for pay codes and a JSON file for fiscal rules, validates it before writing, supports `--dry-run`,
and records who, why and whether it is inferred. There is no UI yet.

## Known gaps

- A `source` provider for `PayCodeCategory` (a customer table mapping category ids to canonical categories) is not modelled:
  the schema carries only the id. The override layer accepts category-id mappings when the customer supplies them.
- A work county that cannot be resolved reaches the row as `""`; it is counted (`rows_with_no_county`) but the pricing paths do
  not yet refuse a client-year whose county is missing. That needs a decision in the engine, not the projection.
- The Warehouse adapter for the override store is covered by the tenant-helper architecture test and the SQLite contract
  tests, and has not been run against a live Warehouse.
