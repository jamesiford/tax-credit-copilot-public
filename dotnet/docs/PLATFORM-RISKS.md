# .NET platform risks: halted before live access

| Question | Verdict | Headline evidence | ADR recommendation |
|---|---|---|---|
| Warehouse writes vs Python; `SqlBulkCopy` | Not tested | No rows written; no baseline or throughput measurements | No write-path decision supported |
| Lakehouse SQL reads vs Python | Not tested | No source rows read; no parity hashes or timings | No read-path decision supported |
| Delta-version stand-in | Not tested | No SQL fingerprint, OneLake or REST probe | No version-marker decision supported |
| Direct Delta libraries, including Linux | Not tested | Docker Linux engine available; no library/container read attempted | No direct-Delta decision supported |
| EF Core scope on Warehouse | Not tested | No EF model or live operation attempted | No EF Core decision supported |

## Evidence and stop condition

The complete task description was read, and preflight resumed the existing
local `dotnet/platform-risks` branch/worktree from `dotnet/spike`. Approval was
`yes`. The .NET 10 SDK, Python oracle and main-checkout configuration file were
present. Azure CLI was signed in; its tenant's demo Fabric access was not
verified. Docker 29.9.3 reported a Linux engine.

An isolated `dotnet\spikes\platform\Platform.slnx` was created without modifying
the main solution or any existing Python file. Its build completed with
**zero warnings and zero errors**. The mandatory offline `ScratchGuard`
self-test then exited **2**, emitting:

```text
InvalidOperationException: InvalidOperationException
```

The negative-test loop raises `InvalidOperationException` if a forbidden SQL
statement is accepted. The runner does not currently identify the failing
case. The suite contains 20 negative cases and 11 positive cases; these are
fixture counts, **not passing-test counts**. No live access was attempted.

Per hard stop 1, the run ended rather than repairing and continuing after a
failed safety self-test. `HALT.md` records the block. PS1 through PS9 live
investigations, including live decimal/datetime metadata and the HTTP/SQLite
contract comparison, remain unperformed. The historical Python write timing
in the task description is not a measurement from this run.

## Cleanup

**Not proven.** This run opened no connection and created no scratch objects.
Whether an earlier run left objects behind is unknown. There is no zero-objects
metadata result, and no list of dropped objects may honestly be reported.

The standalone `cleanup` command is included, but it executes the same mandatory
self-test and therefore blocks live access in this revision. It must not be
bypassed. No capacity changes, push, pull request or remote changes were made.

## Recommendation and next controlled tests

Make no platform ADR decision from this run. In a separately authorized run,
first diagnose the failing negative case, repair the guard and demonstrate
every forbidden case being refused in both C# and the new Python baseline
guard. Only then verify tenant access, test connectivity, inventory and remove
leftover scratch objects, and proceed through PS1-PS8 with final cleanup proof.

The Fabric owner must establish suitable file-read permissions before direct
OneLake/version probes. Viewer-vs-file-read role requirements were not verified
here. With a separately approved controlled lake load, the owner can compare
Delta commits, SQL endpoint visibility, SQL fingerprints and Silver markers
over time to measure sync lag; this spike has no authority to change the lake.
