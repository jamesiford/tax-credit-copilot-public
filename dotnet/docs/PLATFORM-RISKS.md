# .NET platform risks: guard repaired, connectivity verified

| Question | Verdict | Headline evidence | ADR recommendation |
|---|---|---|---|
| Token-authenticated Warehouse connectivity | Works | Latest `SELECT 1` in 3.983 seconds including connection open; explicit Azure CLI token | Token connectivity is viable; pooling/retry policy not yet measured |
| Warehouse writes vs Python; `SqlBulkCopy` | Not tested | No rows written; no baseline or throughput measurements | No write-path decision supported |
| Lakehouse SQL reads vs Python | Not tested | No source rows read; no parity hashes or timings | No read-path decision supported |
| Delta-version stand-in | Not tested | No SQL fingerprint, OneLake or REST probe | No version-marker decision supported |
| Direct Delta libraries, including Linux | Not tested | Docker Linux engine available; no library/container read attempted | No direct-Delta decision supported |
| EF Core scope on Warehouse | Not tested | No EF model or live operation attempted | No EF Core decision supported |

## Conductor failure and repair

The first run halted because negative self-test case 19 was accepted:
`SELECT * FROM OPENROWSET(BULK 'file', SINGLE_CLOB) AS x`.
ScriptDom parses this as `BulkOpenRowset`, not `OpenRowsetTableReference`.
The guard rejected the latter but lacked a visitor for the former.

The repair explicitly rejects `BulkOpenRowset`. Negative-test diagnostics now
identify each refused fixture and identify any unexpectedly accepted case.
**All 20 forbidden cases and all 11 allowed cases pass**, including production
schema writes, mixed-case/bracket-quoted targets, multi-object drops,
comment-obfuscated targets, multiple statements and external bulk rowsets.
The isolated .NET solution builds with zero warnings and errors.

This follow-up addresses the conductor's `no_halt` failure. The earlier halt
record is removed after successful safety checks and guarded live cleanup;
future successful `ps1` and `cleanup` commands also clear stale halt records
only after the cleanup proof succeeds. An offline test alone cannot clear them.

## Preflight and limited live evidence

Approval was `yes`; Azure CLI was signed in. .NET SDK 10.0.404, the Python
oracle and main-checkout configuration were present. Docker 29.9.3 reported
a Linux engine. Targets were loaded at runtime from the required main checkout
configuration; no server name, Fabric item ID, token or source value was
recorded. Token acquisition and guarded `SELECT 1` succeeded on the demo
Warehouse, establishing access without modifying the capacity.

The latest 3.983-second measurement uses `Microsoft.Data.SqlClient` 7.1.2 with an
`AzureCliCredential` token, encryption, certificate validation, 90-second
connection timeout, pooling enabled and maximum pool size four. It includes
connection open and the probe, not token acquisition. It is not a write or read
throughput baseline. It is persisted in `platform-connectivity.json`; the
initial probe took 4.209 seconds. The standalone non-pooled cleanup probe took
2.260 seconds in a separate process; this is not a controlled pooling comparison.
Default authentication, pooled reconnects and 30/60/120
second idle/retry measurements have not been performed.

## Cleanup proof

The guarded metadata query:

```sql
SELECT o.name, o.type
FROM sys.objects o
JOIN sys.schemas s ON o.schema_id = s.schema_id
WHERE s.name = @schema
```

bound `@schema` to `tcc_scratch_dotnet` and returned **zero objects**.
The scratch schema is dropped if present. The metadata inventory was repeated
after cleanup and again returned zero.
**Cleanup is proven.** This run created no scratch tables and wrote no rows.
The standalone `cleanup` command is available and independently rechecked.
Both the standalone cleanup and the final `ps1` check reported zero scratch
tables dropped, zero scratch schemas dropped and zero remaining objects.

## Remaining investigation

PS2-PS8 remain **not tested**, and PS1 is limited to token connectivity and
cleanup. No platform write/read/version/EF Core ADR should be settled from this
evidence. The historical Python write timing in the task description is not a
measurement from this run. Live decimal/datetime metadata and the HTTP/SQLite
contract comparison also remain unperformed.

A subsequent experiment must retain the passing guard, implement a guarded
Python baseline and retain final cleanup before measuring the remaining paths.
The Fabric owner must establish file-read permissions before direct OneLake
probes. With a separately approved controlled lake load, compare Delta commits,
SQL endpoint visibility, SQL fingerprints and Silver `Source_Version` markers
over time to measure sync lag. This work has not modified the lake or capacity.

No existing Python file, main solution or other worktree was changed. No push,
pull request or remote change was made. Conductor status and local gate evidence
are recorded in `dotnet\docs\status\platform.json`.
