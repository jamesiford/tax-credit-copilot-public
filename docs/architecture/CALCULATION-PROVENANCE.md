# Calculation Provenance Standard

## Purpose

Every material number in Tax Credit Copilot must answer five questions without
requiring trust in an LLM or undocumented code:

1. **What source records were considered?**
2. **Which rule and parameters were applied?**
3. **What formula and intermediate values produced the result?**
4. **Which assumptions, exceptions, or manual decisions affected it?**
5. **Can the same inputs and versions reproduce it?**

This standard applies to all deterministic calculations, including payroll
normalization, eligibility, One/Zero, Average Headcount, net-new jobs, credit
benefit math, frozen-base-year tranches, forecasts, simulations, alerts, and
opportunity scoring.

## Non-negotiable contract

A calculation is not complete when it returns only a final value. It is complete
when it also emits a structured calculation walk with enough information to
reproduce and challenge the result.

Each calculation stage must record:

| Field | Requirement |
| --- | --- |
| `calculation_id` | Stable ID tying all stages in one run together |
| `step_id` | Stable method-specific step ID, not a display label |
| `stage` | Source, normalize, total, denominator, average, eligibility, matrix, summary, benefit, or another explicit stage |
| `method` | Calculation method such as `pay_period`, `min_max`, `one_zero`, `base_year`, or `credit_benefit` |
| `inputs` | Values used by the formula; direct identifiers are redacted outside authorized local drill-down |
| `input_counts` | Rows/employees/units included, excluded, collapsed, or flagged |
| `parameters` | Resolved floors, dates, cadence factors, thresholds, rounding, and overrides |
| `formula` | Human-readable equation plus stable formula/version identifier |
| `output` | Intermediate or final result produced by this step |
| `decision_basis` | `source_confirmed`, `project_assumption`, `rule_pack`, `negotiated_override`, or `manual_review` |
| `assumption_ids` | Versioned assumption IDs such as `BA-02`; empty when none apply |
| `exceptions` | Data-quality flags, manual exclusions, unresolved ambiguities, and invariant violations |
| `citation` | Source document/statute and exact section or step |
| `code_ref` | Module/function and code commit used for the run |
| `source_hash` | Source manifest or approved aggregate-input hash |
| `config_hash` | Rule/assumption/configuration hash |
| `timestamp` | UTC run timestamp |

The existing `TrailRecorder` structure (`step`, `inputs`, `formula`, `output`,
`citation`) is the baseline. Reference Dataset work must extend or wrap it to carry
the remaining provenance fields without breaking current API consumers.

## Two disclosure levels

### Aggregate trail

Safe for normal application views and exports:

- source/config hashes;
- row and employee counts;
- resolved rules and assumptions;
- formulas and aggregate intermediate values;
- exception counts;
- no employee IDs, FEINs, or raw payroll values.

### Authorized employee drill

Available only in the private benchmark runner or an authenticated, scoped
future product surface:

- employee surrogate or authorized source key;
- included/excluded source-line references;
- totals, denominator, averages, and flags under each method;
- unit/month allocation where authorized;
- exact discrepancy against benchmark output.

Employee-level values must never enter Foundry prompts, public demo data,
telemetry, screenshots, or Git.

## Stage requirements

### Source and normalization

Show:

- source manifest and assumption-set IDs;
- raw, padded, usable, included, excluded, collapsed, and flagged counts;
- date-window and pay-code decisions;
- duplicate/correction formulas;
- exceptions rather than silent repairs.

### Eligibility

For each method show:

- common total hours and wages;
- denominator inputs and formula;
- weeks worked;
- average weekly hours and wages;
- resolved hours/wage floors;
- rounded and unrounded values where rounding affects eligibility;
- hours-pass, wage-pass, and overall-pass flags.

### One/Zero

Show:

- eligible-list version feeding the matrix;
- method-specific row grain;
- month targets and Month-12 override;
- every employee-unit-month 1/0/weight decision;
- test-of-twos flags and tie-break/manual disposition;
- unit-month totals, denominator months, averages, and rounding views.

### Credit benefit

Show:

- current and comparison Average Headcount;
- net-new formula;
- minimum-jobs gate and whether it gates or subtracts;
- per-job or wage-percentage value;
- annual and lifetime formulas;
- rule-pack version, statutory citation, and any negotiated override.

## Assumption and exception policy

- Assumptions use immutable versioned sets. A run records assumption-set ID and
  SHA-256.
- If evidence disproves an assumption, create a superseding set. Never rewrite
  the configuration behind a historical result.
- A discrepancy is classified before code or configuration changes:
  `source anomaly`, `scope difference`, `configuration difference`,
  `rounding/tolerance`, `engine defect`, `benchmark defect`, or `manual judgment`.
- Subjective corrections remain flagged for review unless an approved rule makes
  them deterministic.
- Unverified values remain visible in the calculation walk and UI; they are not
  hidden by polished copy.

## UI and demo contract

Every material result surface should provide a **How calculated** or equivalent
drill that presents:

1. headline value and method;
2. formula;
3. resolved inputs and parameters;
4. intermediate stage table;
5. source/citation;
6. assumptions and exceptions;
7. reproducibility metadata.

Agents may narrate this structured record, but cannot calculate, alter, or omit
its values.

## Test contract

Each calculation requires:

- a focused formula test;
- stage-shape tests;
- at least one edge-case/exception test;
- a trail/provenance assertion;
- a reproducibility assertion for source/config hashes;
- a regression fixture for every resolved Reference Dataset discrepancy.

## Definition of done

A calculation is audit-ready when an authorized reviewer can select a result,
walk backward through every stage to the approved source/configuration, reproduce
it with the same versions, and see every assumption or exception that could have
changed the answer.
