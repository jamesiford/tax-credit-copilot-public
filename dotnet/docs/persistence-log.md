# Persistence session log

## Resume and preflight

The conductor's explicit repair request authorizes the required session report
and status paths. The obsolete ownership halt is removed. Implementation
ownership remains confined to Persistence, its tests, Persistence application
ports, and the marked central package section.

CPython 3.12.13 was verified at the designated oracle path. An explicit
worktree-local `sys.path` resolves `tools` under this worktree's `backend`.
Every .NET gate invocation sets `TCC_PYTHON` explicitly; live test approval
variables remain unset. The installed default SDK outside `dotnet` is 11;
gates run inside `dotnet` so its `global.json` selects the pinned SDK.

Read domain certification, platform risks, port inventory, findings, DS/CAP
seams, contract report and harness/seed evidence. The engine is not re-ported.
The platform evidence proves only token connectivity, not writes, bulk copy,
pooling or live decimal/date metadata.

## Implementation decisions

- One configured database is shared by Gold, claims and manifests.
- SQLite uses explicit schema-derived types. Decimal storage is exact text,
  not REAL; provider-specific typed binding retains Domain decimals.
- Claims retain their own decimal exponent. Seed Gold retains the recorded
  numeric value's float representation; production Gold uses declared scales.
- Gold publication is transactional, including currency and manifest changes.
  Native write conflicts retry the whole rolled-back transaction. Ambiguous
  commits are not blindly retried.
- Tenant exemptions are a closed, named internal capability and log every use.
- SqlClient and SQLite packages are checked for license before adoption.

Package review (cached NuGet nuspecs): Microsoft.Data.SqlClient 7.1.2 and
Microsoft.Data.Sqlite 10.0.0 are MIT. The first restore refused vulnerable
SQLitePCLRaw.lib.e_sqlite3 2.1.11 (NU1903, GHSA-2m69-gcr7-jv3q); explicitly
select SQLitePCLRaw.bundle_e_sqlite3 2.1.13 (Apache-2.0) to pull its patched
native dependency. No audit suppression is used. Versions belong only to the
persistence marker section.

## P1/P2/P4 foundation evidence

The complete persistence test project builds with `-warnaserror`. The parent
transport, schema, importer and publication checks passed: 41 fast cases in
34 seconds. During concurrent adapter editing, development tests temporarily
disabled analyzers; these were not claimed as conductor gates. The subsequent
analyzer-enabled project build passed.

The heavy P1 -> P2 -> P1 reset passed in 82 seconds. All 11/20 manifest
tables and 18,111/390,660 rows were verified, including the stated TY2025
populations. Decompressed hashes, shipped hashes, column order and counts are
checked before a transaction can commit. Corruption and insert failures
preserve the prior store. Source rows now stream from a live reader rather
than materializing the full Payroll table.

The DDL reader recognizes FLOAT for the three claim headcount fields, mapped
to SQLite REAL; this is not a money conversion. DECIMAL fields remain exact
text with numeric collation and precision/scale checks. All seven Gold column
lists match the parsed schema. Six local migration identities (bootstrap plus
five forward files) retain their actual content hashes across business resets.

Publication tests execute real SQLite transactions, including an exception
immediately after old current rows are retired. All partial rows roll back,
the prior successful rows remain current, and the new manifest is marked
failed without a completion stamp. Shared unit-of-work transactions also
roll back a post-Gold assessment failure. Native conflicts and ambiguous
acknowledgements are fault-injected transport evidence, not live Warehouse
publication certification.

## P3/P5 and capstone evidence

All 25 Gold-read members and the governed query catalogue are implemented.
The reader/query suite passed 30 non-heavy cases and one heavy P2 recording
comparison (about 70 seconds). Every employee read pins stored successful-run
identity; filtering/paging does not silently replace population counts.
DISTINCT and ordinary SQLite paging execute without the harness translation
defect. Raw employee queries default-deny and cannot expose employee/actor IDs
or be treated as model-safe context.

The operational suite passed 41 analyzer-enabled cases, including reset of all
19 owned tables and invalidation of old worker leases. Histories, optimistic
versions, client scope, artifact access outcomes, channel expiry and competing
workers use real independent SQLite connections. Queue finish/refresh retains
the four-statement/one-transaction budget.

The complete persistence capstone passed all 12 successful public pipeline
payloads (390,945 rows / 8,017,010 typed cells) in 4 minutes 11 seconds.
Pre-storage equality and reopened stored representation are separate checks.
The real post-Gold/post-claim failure capstone passed in five seconds and rolled
back every side effect. No golden or Domain implementation was changed.

Additional focused tests passed for six content-hashed migration identities,
nullable forward columns, conflicting schema/hash refusal, 38-digit native
decimal/exponent binding, and rejection of nested source values even when
their forged content/file hashes match.

`QueryBounded` has an actual execution budget: native timeout/cancellation,
SQLite interruption and progress callback, plus an explicit row cap. Three
focused real SQLite tests passed for a one-second billion-row aggregate,
100ms cancellation, refusal rather than partial success, and reuse afterward.
The first analyzer pass requested CancellationToken-last ordering on internal
helpers; this was corrected without disabling analyzers.

## Final gate invocation

Run from `dotnet` so the pinned net10 SDK is selected, and set the interpreter
in each fresh process:

```powershell
$env:TCC_PYTHON='C:\Projects\py312-oracle\.venv\Scripts\python.exe'
dotnet build -warnaserror
dotnet format --verify-no-changes
dotnet test --filter 'Category!=heavy'
```

The final formatter found one GoldDataQuery import-order issue; the formatter
fixed that file. An isolated test attempt under system TEMP could not locate
the repository fixtures from AppContext.BaseDirectory and failed before
repository operations. Validation was moved to an isolated output under the
repository's ignored artifacts directory, rather than weakening fixture checks
or replacing concurrently running binaries. No global/user environment was
modified. Final gate outcomes are appended after completion.

Final results: whole-solution fast gate passed (Domain 18, parity 152,
architecture 13, persistence 123 at that build snapshot); the final persistence
snapshot including the two DI integration tests passed 125/125 in about two
minutes. The parity project took 12m23s. All seven previously reported parity
failures are gone with the mandated oracle selected.

Whole-solution formatting verification passed. A concurrent build/format
attempt hit MSB3883 on a temporarily locked Domain reference assembly; after
those processes exited, the exact warning-as-error build passed in 34.46s with
zero warnings/errors. This was a validation-process collision, not a source
change or a reason to disable checks.
