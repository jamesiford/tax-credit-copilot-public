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
