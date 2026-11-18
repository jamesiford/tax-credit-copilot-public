# R1 rename log

Running log for `rename/r1-env-vars` (worktree `..\tcc-rename-r1`, branched from `main` at `df06d1e`). Nothing is pushed.

## Baseline (before any change)

| Suite | Result |
| --- | --- |
| `dotnet build TaxCredit.slnx -warnaserror` | succeeded, 0 warnings, 0 errors |
| `dotnet format TaxCredit.slnx --verify-no-changes` | _see below_ |
| `dotnet test TaxCredit.slnx` | _see below_ |
| `pytest backend/tests -q` | _see below_ |
| `terraform fmt -check` / `validate` (`infra/`, `infra-dotnet/`) | _see below_ |
| frontend `npm test` | _see below_ |

## Stage R1.1: inventory and mapping

- 108 distinct `TCC_` tokens found in tracked files; 6 are not environment variables (`TCC_COLUMNS`, `TCC_DECIMAL`, two stderr diagnostic codes, the `TCC_TELEMETRY_` prose fragment, the `TCC_GOLD_SCHEMA` docstring slip).
- Mapping written to `docs/rename-r1-mapping.md`. No unmapped token; one deliberate duplicate new name (`REPOSITORY_ROOT`, merging the Python `TCC_REPO_ROOT`, as directed).
- Collisions found and resolved: four azd inputs share a name with a Terraform output of a different meaning (`EXISTING_` prefix); `PROFILE` became `DEPLOY_PROFILE`; `DOTNET_ACTIVATE` became `DEPLOY_DOTNET_ACTIVATE`.
