# R1 rename log

Running log for `rename/r1-env-vars` (worktree `..\tcc-rename-r1`, branched from `main` at `df06d1e`). Nothing is pushed; no remote was touched.

## Baseline (before any change, from a clean worktree of `main` with the private fixtures copied in)

| Suite | Result |
| --- | --- |
| `dotnet build TaxCredit.slnx -warnaserror` | succeeded, 0 warnings, 0 errors |
| `dotnet format TaxCredit.slnx --verify-no-changes` | clean |
| `dotnet test TaxCredit.slnx` | all green: Domain 18, Architecture 16, Orchestrator 431, Infrastructure.Ai 167, Shadow 8, Infrastructure.Auth 147, Gateway 103, Infrastructure.Sources 189 (+4 skipped), Infrastructure.Persistence 163, Api 441, Parity 152 |
| `pytest backend/tests -q` with `TCC_REQUIRE_PARITY=1` | 6967 passed, 118 skipped, 1 xfailed, **1 failed**: `test_doc_links` (`dotnet/docs/ROUTES-READS-REPORT.md:5` links `HALT-routes_reads.md`; pre-existing, unrelated) |
| `pytest dotnet/deploy dotnet/src/TaxCredit.Api/Contract` | 33 passed, 323 subtests |
| `terraform fmt -check` / `validate` / `test` (`infra/`) | clean / valid / 81 passed |
| `terraform fmt -check` / `validate` / `test` (`infra-dotnet/`) | clean / valid / 14 passed |
| frontend `npm test` | 38 files, 600 tests passed |
| `verify_reference_independent.py` | 17/17 |

## Stage R1.1: inventory and mapping

- 108 distinct `TCC_` tokens in tracked files; 6 are not environment variables (`TCC_COLUMNS`, `TCC_DECIMAL`, two stderr diagnostic codes, the `TCC_TELEMETRY_` prose fragment, the `TCC_GOLD_SCHEMA` docstring slip).
- `docs/rename-r1-mapping.md`: no unmapped token; one deliberate duplicate new name (`REPOSITORY_ROOT`, as directed).
- Collisions resolved: four azd inputs share a name with a Terraform output of a different meaning (`EXISTING_` prefix); `PROFILE` became `DEPLOY_PROFILE`; `DOTNET_ACTIVATE` became `DEPLOY_DOTNET_ACTIVATE`.

## Stage R1.2 to R1.4: renames and aliases

- A script (kept outside the repo) applied the mapping to every tracked text file except the historical reports, with word-boundary matching, longest name first.
- Fallbacks, one table per host: Python `backend/config_aliases.py`; .NET `LegacySettingAliases.cs`; tests `LegacyTestEnvironment.cs`; scripts and azd `scripts/legacy-env.ps1` (plus the azd `preprovision` hook); standalone fallbacks in the Cowork plugin, `crosscheck.py`, `verify_reference_independent.py`, the telemetry hook and the two csproj launch targets.
- Things the mechanical rename could not do and that were fixed by hand: the `.NET` configuration inventory listed seven runtime names twice after the merge (azd duplicate removed, plus `REPOSITORY_ROOT` in the "irrelevant" group); `test_data_access_docs.py` asserted the `${TCC_...}` shape of the azd mapping; `terraform fmt` re-aligned two infra-dotnet files; `contract/inventory` was regenerated; `scripts/README.md` got a row for the new script; the `probe_support.py` env filter now covers `TELEMETRY_`.
- `configure-local.ps1` against a throwaway `backend\.env`, before and after: the only difference in the generated launch settings is `TCC_PERSISTENCE_PROVIDER` to `PERSISTENCE_PROVIDER` in both profiles (`warehouse` live, `sqlite` offline). Nothing else changed.

## Final gates

| Suite | Result |
| --- | --- |
| `dotnet build -warnaserror` | 0 warnings, 0 errors |
| `dotnet format --verify-no-changes` | clean (after formatting the new test file) |
| `dotnet test` (oracle Python set through `ORACLE_PYTHON`) | all green; Api 455 (441 + 14 alias tests), Gateway 104 (103 + 1). `Infrastructure.Ai` had one timing failure (`ResilienceTests.RetryAfterIsHonoredAndHealthyStreamsUseGapNotDuration`) while the Python suite and the frontend tests ran alongside; it passes alone (167/167) |
| `pytest backend/tests -q` with `TEST_REQUIRE_PARITY=1` | 7006 passed, 118 skipped, 1 xfailed; the two other failures were fixed and re-run green (`test_data_access_docs`, `test_architecture_scripts`); the one remaining failure is the same pre-existing `test_doc_links` |
| `pytest dotnet/deploy dotnet/src/TaxCredit.Api/Contract` | 33 passed, 308 subtests (15 fewer because the merged names are inventoried once) |
| `terraform fmt -check` / `validate` / `test` (both stacks) | clean / valid / 81 and 14 passed |
| frontend `npm test` | 38 files, 600 tests passed |
| `verify_reference_independent.py` | 17/17; certified figures 10,236 / 539 / 656 untouched (`TEST_REQUIRE_PARITY=1`, no pinned constant edited) |
| `contract.inventory.generate --check` | matches |
| `pwsh` parse of every changed `.ps1` | ok |
| `python scripts/...` `--help` for the changed scripts | ok |
| `actionlint` | not installed here; workflows checked by reading the diff |
