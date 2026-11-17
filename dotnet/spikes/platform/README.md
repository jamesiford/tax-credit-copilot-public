# Live Fabric platform spike

This solution is isolated from `TaxCredit.slnx`. Targets are read only at runtime
from the main checkout's `backend\.env`. No endpoint or credential is stored here.

The guard failure reported by the conductor is repaired. All 20 negative and
11 positive self-test cases pass; guarded Warehouse connectivity and cleanup
have succeeded. See `dotnet\docs\PLATFORM-RISKS.md` for the measured scope.

```powershell
$env:TCC_PLATFORM_SPIKE_APPROVED = 'yes'
dotnet build dotnet\spikes\platform\Platform.slnx
dotnet run --project dotnet\spikes\platform\Runner -- selftest
dotnet run --project dotnet\spikes\platform\Runner -- ps1
dotnet run --project dotnet\spikes\platform\Runner -- cleanup
```

Every explicit SQL command passes the ScriptDom-based `ScratchGuard`.
Comments, multiple statements, unqualified objects and non-scratch writes are
refused. The self-test includes the distinct `BulkOpenRowset` AST node used by
`OPENROWSET(BULK ...)`, not only ordinary `OpenRowsetTableReference`.
The guard self-test runs before any live connection, including `cleanup`, and
prints each refused negative fixture without logging live SQL or source values.

`cleanup` removes scratch tables and the scratch schema, then checks metadata
for zero remaining objects. It requires the same explicit approval and target
configuration as an experiment. Stop on any hard-stop condition in the task.
Successful `ps1` and `cleanup` commands remove a stale halt record only after
the guard passes and cleanup is proven. A successful offline self-test alone
does not clear a halt.

| Phase | Command / status |
|---|---|
| Safety self-test | `dotnet run --project dotnet\spikes\platform\Runner -- selftest` |
| PS1 token connectivity and cleanup | `dotnet run --project dotnet\spikes\platform\Runner -- ps1` |
| PS2 Python baselines | Not implemented; not tested |
| PS3 write methods and live type contract | Not implemented; not tested |
| PS4 conflicts and transactions | Not implemented; not tested |
| PS5 EF Core | Not implemented; not tested |
| PS6 SQL payroll read parity | Not implemented; not tested |
| PS7 version fingerprints | Not implemented; not tested |
| PS8 Delta libraries and Linux | Not implemented; not tested |
| PS9 report | `dotnet\docs\PLATFORM-RISKS.md` records measured and untested work |
| Standalone cleanup | `dotnet run --project dotnet\spikes\platform\Runner -- cleanup` |
