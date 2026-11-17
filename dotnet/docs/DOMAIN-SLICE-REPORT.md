# Domain slice report

Branch `dotnet/domain` (from `dotnet/spike`), local only: nothing pushed, no pull request. Oracle: CPython 3.12.13.
Detail per family is in [`slice-domain-log.md`](slice-domain-log.md); traps and odd Python behaviour (193 numbered
findings) in [`findings.md`](findings.md); the module map in [`port-map.md`](port-map.md).

## Gates

| Gate | Result |
|---|---|
| DS1 every module in `domain/` and `tools/` classified | **Met.** 22 + 52 modules plus 19 `application` modules on the calculation path; `parity/port_map.py --check` fails on an unclassified module |
| DS2 `PyJson` exactly like Python's `json` | **Met.** About 6,200 vectors (edge cases, all 38 `backend/rules` files, seeded mutations); values, int/float types, key order, both `dumps` layouts, and every `JSONDecodeError` message and offset match |
| DS3 rest of `domain/`: bit-identical goldens, mutation self-tests | **Met.** proximity 11,623 calls; claims 31,981 and coverage 9,672; performance family 3,414; models 9,829; runs 52,895; drafts 8,805; all identical including exception type and message |
| DS4 rule packs and credit math, every pack and year | **Met.** 92,926 calls, 21,016 of them exceptions: ten programme packs, Georgia 2019-2026 (other years fail loudly), methodology files, the two fictional programs sharing state ZZ, 42 invented shapes, six broken manifests. Pack validation: 13,542 documents, accept/reject agrees on all of them, semantic issues match bit for bit (60,489 issues) |
| DS5 calculation-path tools | **Met for all but `discovery`** (deferred, see below). gold_projection 8,938 calls; baseyear family 17,162; forecast and simulation 7,870; canonical, grid filter, qc and triggers 5,008 |
| DS6 differential fuzz | **Met.** 20,000 scenarios per family (proximity, gold_projection, baseyear, simulation, credit math) under seed 20261114 and again under 987654321, each batch in a fresh Python process: 0 mismatches. Four bugs found along the way are now regression goldens |
| DS6 capstone, engine to Gold payload | **Met.** 19 runs (committed synthetic payroll plus the four synthetic clients): 390,945 rows and 8,017,010 cells across all seven `tcc_gold` tables, matching bit for bit, plus the run manifest, handler result and 47 claims. Exporter byte-identical across four runs and several `PYTHONHASHSEED` values |
| Quality | `dotnet build -warnaserror` 0 warnings; `dotnet format --verify-no-changes` clean; `dotnet test`: Domain 18, Architecture 13, Parity 152, all pass. Domain is still BCL only |

Only existing Python files edited: `parity/engine_cli.py` and `parity/engine_io.py` (the spike's own). No product Python changed.

## Coverage of in-scope Python

From `port-map.md` (physical lines): **9,993** in-scope lines. Fully ported **6,919 (69.2%)**, partially ported (pure
parts only) **2,502 (25.0%)**, pending **572 (5.7%)**. 36 modules ported, 11 partial, 5 pending. "Partial" means the
computation is ported and the framework-facing part (pydantic request models, CSV/lakehouse readers, mediator wiring) is
deliberately not.

## Biggest traps

1. **Python's `Decimal` is not `System.Decimal`**: 28-digit contexts, kept exponents, `max(Decimal("0"), 0.00)` returning the int-typed operand, `Decimal("_1")` valid in 3.12. Ported as `PyDecimalOps`.
2. **Types ride on lexemes**: `35` versus `35.0` in a rule pack changes the path through `Decimal(str(x))`. The reader decides the type; in C# a `cond ? long : BigInteger` silently converts to `BigInteger` (found by the JSON tests).
3. **Ordering and aliasing**: stable `sorted` with mixed-type `TypeError` operand order (needed CPython's comparison order replayed), dict first-position/last-value on duplicate keys, set iteration order (proved irrelevant by running exporters under several `PYTHONHASHSEED` values).
4. **`jsonschema` versus the .NET library**: five behavioural differences (anchoring, `\s`, `oneOf`, `false` schemas, error order) that changed accept/reject decisions until adapted; remaining difference is wording only.

## Deviations and tolerances

- No numeric tolerance anywhere. The single bit-equality relaxation is the spike's NaN rule (T-12, `NEEDS-HUMAN-REVIEW`, low risk).
- **Schema message wording** differs from Python's `jsonschema` in 17 distinct patterns, and 764 documents report a different *number* of violations (all `required`, V-07). Decisions, keywords and paths match. Listed in [`pack-validation-deviations.md`](pack-validation-deviations.md) (generated). **Whether the exact text matters is a decision for the platform owner.** JsonSchema.Net is pinned at 8.0.5 (MIT); 9.x carries a maintenance-fee EULA.
- Documented seams: `random.random` jitter in `backoff_seconds` is a parameter (Mersenne Twister not ported); clock, ids and `uuid4` are injected.

## Python behaviours that look wrong (ported as is)

- `canonical._worksite_join` never works against the real registry (`Site` has no `.get`; the swallowed `AttributeError` gives every worksite the placeholder) (CQ-01).
- Captured ingestion overrides `wage_basis`, `measuring_date` and pay codes even on a year-resolved pack, contrary to "may fill, never override" (M-01).
- The registry cache serves a stale registry when the manifest's modification stamp is unchanged (M-04); `0042.json` is listed as authored year 42 but cannot be resolved.
- `unit_year_master.tier` is an `int` in production though annotated `str` (CAP-01); `unreachable_months` holds zero-based positions though the DDL says month numbers (GP-03); the DDL describes `included`/`selection_decision`/`qc_flag` as filter outcomes but they are constants (GP-04); the DDL says `employee_id` is tokenised but the raw id is stored (GP-05).
- `derive_run_state` falls back to GA for any non-fixture client (CAP-04); declined-year reasons are collected and never read (CAP-02).
- `weight` of 0 reads as 1.0 in `fragility`; a negative `limit` slices from the end; `batch_status` treats negative counts as open (R-03); the grid filter binds NaN instead of dropping the term (CQ-07).
- In `credit_math`/`program_credit` a state with several programs prices its **first** program rather than erroring; the typed refusals live in `_client_run.py` and `program_defaults.py` (ported in the pipeline).

## What the Application slice can call

| C# | Python |
|---|---|
| `ClientCalculation.Run` | `handle_run_client_calculation` |
| `ClientRunResolver.ResolveClientRun`, `ClientAssessment.Assess` | `resolve_client_run`, `assess_client` |
| `ProgramDefaults.ResolveProgram`, `RunFingerprint.Identity` | `resolve_program`, `run_identity` |
| `RuleLibrary.LoadYearPack`, `ResolveStatutoryFloors`, `ResolveTaxYearConvention`, `LoadPackOneZero`, `ApplyOneZeroProgramCredit` / `ApplyOneZeroStateCredit`, `CombineProgramEntityCredits` / `CombineEntityCredits`, `ProgramPerJobUsd` / `StatePerJobUsd`, `CreditFromPack`, `LoadRegistry` | the same-named functions in `tools/credit_math.py`, `program_credit.py`, `program_registry.py` |
| `PackValidator.ValidateDocument` / `ValidatePack` / `ValidateAll` | `tools/pack_validation.py` |
| `Proximity.AssessEmployee` / `Fragility` / `NearMissCohort` / `FragileCohort` / `BandCurve` / `RestOfYear` | `domain/calculation/proximity.py` |
| `ProgramClaim`, `ClaimReadings.DecliningReading`, `Coverage.*`, `CoverageSituation.Situation` | `domain/claims.py`, `domain/coverage.py` |
| `PerformanceDashboard.Run`, `Reconciliation.Reconcile`, `Rollups.*` | `domain/calculation/{performance,reconciliation,rollups}.py` |
| `RunStateMachine`, `UnchangedRule.Decide`, `RetryPolicy.BackoffSeconds`, `ProgramDraftRules`, `IProgramDraftRepository` | `domain/runs.py`, `domain/program_drafts.py` |
| `GoldProjection*`, `RecordTokens` | `tools/gold_projection.py`, `tools/tokens.py` |
| `BaseYearEngine.ComputeBaseYearTranches`, `UnitTrendTools`, `DesignationRegistry`, `NegotiatedOverrides`, `BenchmarkReconciliation` | `tools/baseyear.py`, `unit_trend.py`, `designation.py`, `negotiated.py`, `reconcile.py` |
| `ForecastProjection.*`, `WhatIfSimulator`, `OneZeroSimulation`, `OneZeroLever`, `StateCreditCalculator` | `tools/forecast.py`, `tools/simulation.py` |
| `CanonicalMapper`, `GridFilter.Compile`, `TriggerDetector.Detect`, `QcDetector`, `PayLineKeys` | `tools/canonical.py`, `grid_filter.py`, `triggers.py`, `qc.py` |

Ports: `IRulePackSource` (Domain; `JsonRulePackSource` in Infrastructure reads `backend/rules` through `RulePackOptions`, no copies),
`IJsonSchemaValidator`, `ISourceAdapter`, `IFiscalRuleSource`, `IProgramWageSource`, the capturing `IGoldWriter`.

## Risks

- **The mutation harness is slow**: about 8 minutes per mutation (a build plus the parity suite), 208 mutations now. The self-tests were run per family in a fast loop (filter env vars), but the *whole* table was not run end to end in one pass.
- The capstone covers synthetic data only; the private reference extract (10,236/539/656) is out of scope and is **not** proven by this slice.
- Fiscal rules from SQL or the lakehouse sit behind `IFiscalRuleSource` and were not exercised: under the CSV source every window is an assumed calendar year.
- `PySort` replays CPython's comparison order for up to 63 keys only; longer mixed-type lists are unsupported (FZ-02).
- Inputs the generators deliberately avoid (FZ-03 to FZ-07): duck-typed stair attributes, `Decimal` NaN from text, big-int `_rate`, OS-specific folder-read errors.
- One full Parity run once failed 1 of 70 and then passed on every rerun; it was not captured. Later full runs (two or more per family, and a final one) have not reproduced it.

## Open questions for the platform owner

1. Does the exact text of schema findings matter to users (pack validation)? See the deviations document.
2. Should captured ingestion be allowed to override a year-resolved pack's `wage_basis`, `measuring_date` and pay codes (M-01)? The Python does today.
3. Is "a state with several programs prices the first program" acceptable in `credit_math`, given the typed refusal exists upstream?
4. Accept the NaN sign relaxation (T-12)?
5. `discovery` depends on `tools.portfolio`; should the Application slice own both?

## Next

Application slice (mediator commands over `ClientCalculation`, Gold writer/reader adapters over the Warehouse), then
`portfolio` + `discovery`, then re-run the whole mutation table in CI nightly.
