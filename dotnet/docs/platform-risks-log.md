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

## Conductor follow-up: no_halt repair

- Improved the offline diagnostic, identifying negative case 19:
  `OPENROWSET(BULK ...)` was accepted because it uses ScriptDom's distinct
  `BulkOpenRowset` node.
- Added the missing visitor refusal. All 20 forbidden cases and 11 allowed
  cases now pass; the safety test was not bypassed.
- Guarded token-authenticated Warehouse connection and `SELECT 1` succeeded
  in 4.209 seconds, excluding token acquisition.
- Scratch metadata returned zero tables/objects. The inventory
  was repeated after cleanup and returned zero objects again.
- Removed the stale `HALT.md` only after these checks succeeded. Successful
  live commands now clear a stale halt only after cleanup proof.
- This repair does not claim completion of unperformed PS2-PS8 measurements.
- Final isolated build: zero warnings/errors. Offline guard: 20 negative and
  11 positive cases passed. Standalone cleanup: zero scratch tables, schemas
  and remaining objects; its connection/probe took 2.260 seconds.
- Reran `ps1` after stopping the measurement timer before cleanup: connection
  and probe took 3.9826646 seconds, persisted in `platform-connectivity.json`;
  cleanup again returned zero remaining scratch objects.
- Checked `no_halt`, commit presence beyond `dotnet/spike`, owned paths,
  report/expected files and remote branch absence. The clean-tree gate is
  checked again after committing the fix and status record.
