# Live Fabric platform spike

This solution is isolated from `TaxCredit.slnx`. Targets are read only at runtime
from the main checkout's `backend\.env`. No endpoint or credential is stored here.

**Blocked revision:** the mandatory offline guard self-test failed. The run
stopped before any Fabric access. Do not bypass it. See
`dotnet\docs\HALT.md` and `dotnet\docs\PLATFORM-RISKS.md`.

```powershell
$env:TCC_PLATFORM_SPIKE_APPROVED = 'yes'
dotnet build dotnet\spikes\platform\Platform.slnx
dotnet run --project dotnet\spikes\platform\Runner -- selftest
dotnet run --project dotnet\spikes\platform\Runner -- ps1
dotnet run --project dotnet\spikes\platform\Runner -- cleanup
```

The runner is designed to check SQL using the ScriptDom-based `ScratchGuard`.
Comments, multiple statements, unqualified objects and non-scratch writes are
intended to be refused; the negative-test failure means this is not yet proven.
The guard self-test runs before any live connection, including `cleanup`.

`cleanup` removes scratch tables and the scratch schema, then checks metadata
for zero remaining objects. It requires the same explicit approval and target
configuration as an experiment. Stop on any hard-stop condition in the task.
It is blocked by the failed self-test in this revision; cleanup is not proven.

| Phase | Command / status |
|---|---|
| Safety self-test | `dotnet run --project dotnet\spikes\platform\Runner -- selftest` (fails; hard stop) |
| PS1 connectivity | `dotnet run --project dotnet\spikes\platform\Runner -- ps1` (blocked before connecting) |
| PS2 Python baselines | Not implemented after the mandatory hard stop |
| PS3 write methods and live type contract | Not implemented after the mandatory hard stop |
| PS4 conflicts and transactions | Not implemented after the mandatory hard stop |
| PS5 EF Core | Not implemented after the mandatory hard stop |
| PS6 SQL payroll read parity | Not implemented after the mandatory hard stop |
| PS7 version fingerprints | Not implemented after the mandatory hard stop |
| PS8 Delta libraries and Linux | Not implemented after the mandatory hard stop |
| PS9 report | `dotnet\docs\PLATFORM-RISKS.md` records untested questions and the halt |
| Standalone cleanup | `dotnet run --project dotnet\spikes\platform\Runner -- cleanup` (blocked before connecting) |
