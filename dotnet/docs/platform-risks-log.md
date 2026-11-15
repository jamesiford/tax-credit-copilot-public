# Platform risks running log

## Preflight

- Resumed the clean, existing local `dotnet/platform-risks` worktree from `dotnet/spike`.
- Approval gate is `yes`; Azure CLI is signed in.
- .NET SDK 10.0.404, CPython oracle path and main-checkout configuration are present.
- Docker 29.9.3 is available with a Linux engine.
- Direct NuGet access fails TLS negotiation; the already-configured NuGet proxy
  supplies stable versions. No machine-wide source configuration was changed.
- Building the isolated guard and self-tests before any Fabric access.

## Mandatory safety test: hard stop

- The isolated build succeeded with zero warnings and errors.
- The mandatory offline self-test failed with exit code 2 and
  `InvalidOperationException`; the negative-case assertion was not satisfied.
- Hard stop 1 applies. No Fabric connection, token acquisition, SQL statement
  or experiment was attempted. No guard repair/retry was attempted after failure.
- No scratch objects were created by this run. Pre-existing objects are unknown;
  no metadata cleanup proof can be claimed.
- `HALT.md` and `PLATFORM-RISKS.md` record the block and mark every live
  technical question as not tested.
