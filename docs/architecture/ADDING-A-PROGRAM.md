# Adding a program

A new tax incentive program is added by **data**: a registry entry plus a rule pack (and a year pack per authored tax year),
with no engine code change when it uses the supported models. Design: [ADR-013](ADR-013-program-registry.md). Statute rules:
[ADR-005](ADR-005-year-versioned-rules.md). Proof it works: `backend/tests/test_fictional_program_end_to_end.py` registers a
fictional program from a temporary rules folder and prices it with the unchanged engine.

## Where things live

| What | Where |
|---|---|
| The registry (one entry per program, federal included) | `backend/rules/registry/programs.json`, or `PROGRAM_REGISTRY_FILE` |
| The program's base pack | `backend/rules/<state>_<credit>.json` (`federal_<credit>.json` for a federal one), or under `RULES_DIR` |
| A year pack (the statute for one tax year) | `backend/rules/<state>_<credit>/<year>.json` |
| The pack schema | `backend/rules/schema/rule-pack.schema.json` (`schema_version` 1) |
| The old lookups | `STATE_TO_PACK` and `PROGRAM_CODE_TO_PACK` in `tools/credit_math.py` are read-only views over the registry; federal programs are registry entries without a state, found by jurisdiction level |
| Folder and file overrides | `RULES_DIR`, `PROGRAM_REGISTRY_FILE` ([ENV-VARS.md](ENV-VARS.md) §4b) |

The registry file sits in its own `registry/` subfolder because the packs are found with `rules/*.json`; a manifest beside them
would be read as a pack.

The stored `lifecycle` is `draft`, `described` or `retired`. **`calculable` is never typed**: a program is calculable exactly when
at least one year pack is authored, and the registry loader refuses a typed `calculable`. A program with no authored year is
*described, not calculable* and is declined by name. A `retired` program leaves the lookups and is declined as unknown.

## The rules that do not bend

- **Statute is never invented and never inherited across years.** A year pack is complete on its own; a year that is not
  authored is "not authored", never an estimate from a neighbour. The schema rejects `extends`, `inherits` and `base` keys. [ADR-005]
- **Every new value is unverified until a person verifies it.** Packs carry `_prototype_verify` flags and a
  `_prototype_verification` note; the portal and the API say "not verified". Nothing in the product asserts that a program's
  values are legally correct, and a pack that passes validation is *valid*, not *verified*.
- **Nothing activates statute at runtime.** A database row or a portal action cannot change what the engine prices; a year pack
  arrives through a reviewed commit.
- **A pack that claims `_verified: true`** must carry no outstanding `_prototype_verify` flag and must name its source.

## Steps

1. **Decide the program and the state.** Two-letter state, a credit code (`XX_JTC`), and whether it is a state, local or federal
   credit. Several programs may share a state; the first listed is the state's default for derived runs. A federal program has no state and is **not runnable**: a run prices the payroll rows of a state, so a federal entry is described, never calculable.
2. **Check it fits the supported models** (below). If it does not, stop at "needs engine work".
3. **Scaffold.** `python scripts/new-program.py program --code XX_JTC --state XX --name "..." --slug jtc` writes a flagged base pack
   and a `draft` registry entry. Every statutory value is `null`.
4. **Author the year packs with citations.** `python scripts/new-program.py year --pack xx_jtc.json --year 2025` writes
   `xx_jtc/2025.draft.json`, which the engine ignores. Fill every value from a cited source into a complete pack (no inheritance),
   keep the flags until a person verifies, then rename it to `2025.json`.
5. **Validate.** `python scripts/validate-rule-pack.py --all` (or one file; `--json` for machines). Exit 0 valid, 1 errors, 2 usage.
6. **Register.** Set the entry's `lifecycle` to `described` and make sure `pack_file`, `code`, `state` and `jurisdiction` agree with the
   pack. The program is now listed; it becomes calculable when the first year pack exists.
7. **Test with synthetic data.** Follow the shape of `test_fictional_program_end_to_end.py`: a temporary `RULES_DIR`, synthetic payroll
   for the state, an assessment and a calculation. Never use real payroll in a test.
8. **Review.** A tax professional reviews the values against the cited sources; only then is a `_prototype_verify` flag removed.
9. **Deploy.** Packs ship with the backend package. To read them from elsewhere set `RULES_DIR` (and `PROGRAM_REGISTRY_FILE`).

## What a pack can express today (supported models)

| Area | Supported | Pack fields |
|---|---|---|
| Credit | A flat amount per qualifying net-new job over a threshold, in a benefit period, with a base-year tranche | `benefit.amount_per_qualifying_job_usd`, `benefit.benefit_period_years`, `benefit.carryforward_years`, `thresholds.minimum_new_jobs` |
| Headcount | The One/Zero pay-period and min-max methods | `one_zero.*` (floors, `wage_basis`, `pt_aggregation`, `measuring_date`, `entity_combination`, `geographic_granularity`, pay-code policy, `methodology`) |
| Floors by year | A year's weekly hours and wage floor | the year pack's `one_zero`, and `thresholds_by_year` on a flat pack (must agree with its own year) |
| Tax-year label | The year a fiscal window begins or ends | `tax_year_convention.label` |
| Filing | Form, window and cycle (metadata) | `filing.*` |

The registry's `engine_profile` names the models (`credit_model: per_net_new_job`, `headcount_model: one_zero`). A value the engine
does not support is **rejected, not ignored**.

## Needs engine work

None of these can be added by data. Each names the seam where the work would go, and the validator reports them rather than pricing
them wrongly.

| Case | Why a pack cannot express it | Seam |
|---|---|---|
| A percentage-of-wages benefit (`amount_per_qualifying_job_pct_of_wages`) | The engine prices a flat amount per job. A pack that declares only this is describable and reported with a warning; as a year pack it is an error | `tools/credit_math.py` (benefit read), `domain/calculation/onezero.py` |
| Investment-based credits, caps, refundability, carryforward rules beyond the stored years | No model for them | `tools/credit_math.py`, `domain/calculation/` |
| Tiered per-job amounts that vary by location designation beyond a single negotiated designation threshold | One amount per program-year | `StatutoryFloors` in `domain/calculation/floors.py`, `data/designations.py` |
| Credits not based on net new jobs, or several simultaneous credit computations per location | The headcount-delta model is the only one | `domain/calculation/onezero.py` |
| Ingesting statute with the rules-ingestion agent for a state other than Georgia | The agent and its API are Georgia-only by design; statute arrives as an authored year pack | `tools/rules_ingestion.py` |
| Read endpoints, chat and demo surfaces that default `state` to `GA` | The run, base-year, location-level read and client-grain capability paths derive the state from data. The portfolio reads (`GetEligibilityQuery` and friends) already require a state, chat keyword scope detection and the demo simulators still assume Georgia | `api/chat/scope.py`, `api/chat/pipelines_core.py`, `tools/simulation.py`, `api/simulate.py` |
