# W1 persistence report

## Scope and evidence

P1-P6 are implemented: tenant-safe SQL, schema/reset, all 25 Gold-read members,
governed queries, atomic Gold publication and durable operational histories/queue.
The real-writer capstone passed all 12 successful public certified payloads:
390,945 rows and 8,017,010 typed cells, followed by reopened database comparisons.
The final whole-solution gate outcomes are recorded below.

Implementation uses the existing Domain `IGoldWriter`, `IClaimSink`,
`IBaseYearOverrides` and repository contracts. No Domain, existing Infrastructure,
Python, HTTP, host, remote or cloud configuration was changed. The conductor's
repair request authorized the required report/status paths and removal of the
obsolete ownership halt.

## Tenant and transport boundary

`PersistenceDatabase` owns the connection factory/dialect and provides one
connection/transaction per unit of work. Ordinary `SqlSession.Query`, `Execute`
and `Insert` require an explicit tenant. `TenantBinding` accepts leading
WHERE/ON markers, aliases and configured source tenant columns; markers and
question marks inside quoted literals/comments are not interpreted. Positional
parameters preceding/between markers retain their order.

Missing/misplaced markers, count mismatches, invalid identifiers and foreign or
missing insert tenants are refused before the recording connection creates a
command. Source column names are configuration, not request input. Cross-client,
worker, schema, seed, validation and global identity operations use closed
internal, named exemptions; every use logs a fixed meaningful reason without
logging identifiers, values or tokens.

`ClientIdentity.Parse` refuses nonpositive, malformed or out-of-Int64 client
identifiers before binding. W2 must map this application refusal to HTTP 422;
the huge-client recording is not reproduced as an overflow crash.

`EntraSqlConnections` uses SqlClient 7.1.2, an injectable token provider and
`https://database.windows.net/.default`. Connections require encryption,
certificate validation and a bounded four-connection pool. Fake callback tests
verify the scope, refresh invocation, shared callback identity and disposal;
they do not measure live token refresh or pooling.

Multirow INSERTs use at most 500 rows and 2,090 parameters (ten slots below the
2,100 ceiling), including 34-column rows and hostile text values. Confirmed
aborted conflicts 24556/3960/1205 retry the rolled-back whole transaction with
bounded attempts and injected exponential delay. SQLite busy/locked conflicts
are also classified. Permanent failures propagate. An uncertain commit throws
`AmbiguousCommitException` and is never blindly replayed.

## Schema and values

The SQLite schema is derived from the checked-in SQL Server bootstrap and all
five forward SQL migrations, not from manifest-only dynamic tables. Qualified
names map explicitly to quoted `tcc_gold_*`, `tcc_ops_*` and `tcc_source_*`
names. Bootstrap plus five migrations produce six content-hashed local migration
identities, retained across business resets. Operator migration scripts remain
Python-owned; no EF migrations or live scratch objects were introduced.

| Deployed type | SQLite representation | Contract |
|---|---|---|
| BIGINT / INT / BIT | STRICT INTEGER | Checked integers; INT range and BIT vocabulary constrained |
| VARCHAR / CHAR | STRICT TEXT | Declared maximum length; integer tiers stringify only at storage |
| DECIMAL(p,s) | STRICT TEXT, exact-decimal collation | Exact value and precision/scale checks; never REAL money |
| FLOAT claim headcounts | STRICT REAL | Existing nonmonetary claim fields, not dollar arithmetic |
| DATE | STRICT TEXT | ISO date; SQLite claim history retains its recorded full instant |
| DATETIME2 | STRICT TEXT | Recorded/injected ISO instant; naive versus aware shape retained locally |

Domain `GoldCell`, `PyDecimal`, `DateOnly` and `PyDateTime` are reused. Production
Gold values are represented at each declared column scale, rejecting values
that would require rounding. Money is DECIMAL(19,4) in the actual DDL; it is not
the DECIMAL(18,2) shorthand in the contract report. Hours, wages, weights and
headcounts use their own declared scales.

SQLite imported Gold retains the applicable recorded numeric seed rendering;
claims retain strings such as `1234.50`, `1234.5` and `1000.0`. SQL Server binds
exact decimals as typed `SqlDecimal` parameters and dates as typed Date/DateTime2,
not floats. Live Warehouse result metadata/scale and datetime2 UTC rendering
remain unmeasured. Payload equality and provider storage scale are separate
checks; a storage conversion cannot waive a changed calculated value.

## Deterministic reset

`SeedImporter(database, seedRoot, repositoryRoot).Load("P1"|"P2")` is a library
hook, not an endpoint or operator script. Profile paths, table namespaces and
column lists are closed whitelists. Gzip JSONL is streamed, shipped file hashes
and decompressed `content_sha256` are checked, and every row count/column sequence
is verified before a transaction commits. Unknown profiles, corruption,
truncation and insert failures cannot leave half-reset data.

Gold, manifests, claims and engagements use their real shared tables.
Source-shaped rows are staged through `ISeedData`; `SourceSeedData.ReadTable`
streams raw JSON from a sequential reader and deliberately does not project or
resolve payroll. Sources owns tenant-aware projection, fiscal resolution and
data-version semantics.

| Namespace/table | P1 rows | P2 rows |
|---|---:|---:|
| gold/employee_eligibility | 376 | 7,898 |
| gold/employee_period_fact | 5,281 | 104,262 |
| gold/onezero_matrix | 2,898 | 78,150 |
| gold/run_method_summary | 4 | 54 |
| gold/unit_credit_installment | 40 | 350 |
| gold/unit_month_summary | 16 | 246 |
| gold/unit_year_master | 16 | 246 |
| operational/program_claim | 2 | 22 |
| operational/program_engagement | 0 | 0 |
| ops/run_manifest | 1 | 4 |
| source/pay_periods | 9,477 | -- |
| source/Account | -- | 4 |
| source/Address | -- | 39 |
| source/Employment | -- | 2,187 |
| source/Entity | -- | 5 |
| source/EntityFiscalYearRules | -- | 4 |
| source/Location | -- | 39 |
| source/PayCode | -- | 16 |
| source/PayFrequency | -- | 16 |
| source/Payroll | -- | 197,094 |
| source/StateCountyZip | -- | 24 |
| **Total** | **18,111 (11 tables)** | **390,660 (20 tables)** |

P1 twice and reopening passed. The heavy P1 -> P2 -> P1 reset passed in 82
seconds. TY2025 min-max evaluated populations are 107 for P1 and
202/164/137/125 for the four P2 clients. These are seed population figures,
not the separate engine certification figures.

Reset clears business Gold/operational/source state, including subsequently
created queue, leases, drafts, findings, overrides, artifact metadata and channel
tables. Artifact bytes are outside this adapter: the host reset coordinator must
invoke byte-store cleanup separately and must not report a complete reset if
that operation fails.

## Publication and calculation integration

`GoldWriter.WriteRun` validates all seven Domain Gold column lists and run,
client and program identity. A running manifest precedes row publication.
Publication retires old current rows, appends every table, checks invariants,
supersedes the prior successful client-program manifests and stamps success in
one transaction. Supersession covers the whole series, not just the requested
year; only the unit-year and installment tables carry `is_current`.

Real SQLite failure tests cover the exact boundary immediately after old rows
are retired, intermediate period insertion and final installment insertion.
The prior successful rows stay current, partial new rows disappear and the new
failed manifest retains a null completion stamp. A reopened store sees the
accepted run; unrelated clients and programs remain current.

Named section-9 checks preserve established formulas/tolerances and cover live
duplicates, all seven tables' run orphans, vocabulary, decline reasons,
installment/annual arithmetic and current-manifest consistency. Warehouse keys
are not assumed: corruption tests duplicate unit rows in SQLite and demonstrate
the checks themselves. Reaping does not invent completion timestamps.

`IPersistenceUnitOfWork` joins collaborators using the same configured database.
`IClientCalculationRunner` / `PersistedClientCalculation` wrap the complete
Domain calculation, including its post-Gold claim assessment and validation.
W2 must consume this runner, not invoke `ClientCalculation.Run` outside that
transaction. An assessment failure rolls back its Gold and claim changes,
including any otherwise-successful partial manifest; mediator failure auditing
remains a host responsibility.

The capstone uses public `ClientCalculation`, payroll/rule sources and injected
fixture clocks/IDs, not a copied private capturing world. A certifying decorator
compares each typed payload before delegating to the real writer; separate
readback asserts declared storage representation for every cell. All 12
successful scenarios passed in 4 minutes 11 seconds. The separate real
post-Gold/post-claim assessment-failure test passed and left no usable manifest,
Gold rows or claim. Existing certified validation-count inputs are preserved;
additional database checks do not rewrite golden-derived figures or counts.

## Gold reads and governed queries

`IGoldReadPort` declares the Python port's 25 members. Gold reads execute SQL
over stored results, never payroll or the calculation engine.

| Members | Scenarios |
|---|---|
| Connection, Scope | Keepalive, two-link prewarm, nested scopes |
| LatestRun, RunInFlight | Successful program scope, supersession, requested-year independence, stranded-run deadline |
| UnitPage, UnitYears, Unit, UnitMonths, MonthSummaries | P1/P2 recordings, paging past the end, unknown units/years, row-owned measuring dates |
| Installments, CreditColumns, UnitTotals | Stored tranche streams, SQL totals, exact money, all-null totals remain null |
| UnitEmployees, UnitNearThreshold, UnitDrill | Month contributors, DISTINCT near misses, independent filters/counts, sorting before paging |
| HeadcountSeries, ClientYearSeries, OnezeroMatrix | Recorded calendar/annual conclusions, allocation and unit/FEIN rollups |
| AtRisk, ProximityCandidates | Recorded verdicts and necessary-condition bounds without bounding population counts |
| CohortPeriods, EligibilityPopulation, EmployeeDrill, Employee, EmployeeUnits | Consumed rows, stored token resolution, unknown tokens, deduplication, two-method pivot, client/year isolation and drift |

These include composed-path tests, not a separate recording comparison for
every member. Thirty non-heavy reader/query cases passed; the heavy P2 recorded
read comparison passed in about 70 seconds. DISTINCT and ordinary SQLite
paging execute directly rather than emulating the harness's DISTINCT TOP bug.

`IGoldDataQueryPort` / `GoldDataQuery` build SQL from a governed specification,
not caller SQL, joins or source datasets. The catalogue contains the seven
Gold tables plus tenant-scoped run-manifest history. Unit-year/installment
selection requires `is_current`; other Gold tables use the latest unsuperseded
completed successful client run. The governed live-run selector is client-wide,
as in the Python query adapter, not an invented program selector.

Limits are 500 returned rows, 12 projections, 6 measures, 8 predicates, 8 groups,
4 orders and 12 tax years (2000-2100); IN lists are limited to 50 and text to
100 characters. Catalogue-permitted aggregates are count/count-distinct,
sum/avg/min/max. Method remains selected/grouped. A limit-plus-one probe reports
`Truncated`; distinct public dimensions/flags allow 1-100 values.

The default timeout is 20 seconds. `SqlSession.QueryBounded` applies native
command timeout, linked cancellation/deadline, SQLite interruption and a VM
progress handler. Real tests interrupt a billion-row aggregate after one second,
cancel it at 100ms without waiting for a 30-second budget, enforce the row cap
and prove the connection remains usable. Failures never become partial success.

Raw employee-query authorization defaults denied. An injected trusted
`Func<long,bool>` may authorize first-party delivery; client entitlement must
also be established by the host. Employee IDs and actor IDs are forbidden query
projections regardless, and employee-level results must not enter model context.
SQLite monetary SUM is exact. Monetary AVG retains the Python SQLite adapter's
native floating arithmetic; changing that derived figure requires an owner
decision, not a parity waiver. Live Warehouse AVG/decimal metadata equivalence
is not claimed.

## Operational stores

No live Fabric, Foundry, Entra or customer system was contacted.

The operational adapter's analyzer-enabled suite passed 41 cases.
Its method-to-scenario inventory is:

| Store | Implemented methods | Scenario files |
|---|---|---|
| Claims/engagements | Current, History, Coverage, PortfolioCoverage, Record, Engagements, SetEngagement | ClaimRepositoryTests |
| Manifests/overrides | Record, Get, Latest, Count; Record, BaseYears, History | ManifestOverrideTests |
| Run batches/queue | Create, Get, FindByKey, FindOpenIdentical, ListBatches, ListItems, GetItem, StatusCounts, Refresh, Cancel, RetryFailed, Claim, Heartbeat, MarkRunning, Finish, Requeue, Release, ReapExpired, QueueHealth | RunBatchRepositoryTests, RunQueueCostTests |
| Drafts/events | Create, Get, Save, ListDrafts, Events, LiveForCode | ProgramDraftRepositoryTests |
| Lookups | Entries, Put, Remove, Audit | MetadataLookupFindingTests |
| Findings/resolutions | Live, History, Record, Reopen, Audit | MetadataLookupFindingTests |
| Artifacts/access | Record, Find, Live, RecordAccess, Accesses | MetadataLookupFindingTests |
| Channel writer/state | Grant, Revoke, IsWriter, Live, Create, FindByTokenHash, FindByIdempotencyKey, Consume, RecordResult | ChannelRepositoryTests |
| Channel audit | Append overloads, ForUser, ByCorrelation, Recent | ChannelRepositoryTests |
| Native provider values | Typed UTC/date/decimal binding | ProviderBindingTests |

The scenarios cover reopen/durability, two-client isolation, identity conflicts,
history preservation, optimistic versions, immutable channel results, expiry,
backoff, spent attempts, cancellation and failed-only retry. Competing queue
workers use separate database connections; one process mutex is not the proof.
Item finish plus batch refresh uses four statements in one transaction.

The reset scenario populates all 19 operational tables, resets/reopens P1,
checks empty supplemental state and rejects pre-reset worker leases. The only
supplemental table outside the parsed SQL bootstrap is `tcc_ops.finding_audit`;
SQLite initialization creates it. Deployed provisioning of that durable audit
table remains an operator/integration requirement, not a claimed live migration.

Its exact supplemental contract is:

```sql
CREATE TABLE tcc_ops.finding_audit (
    audit_id VARCHAR(64) NOT NULL,
    client_id BIGINT NOT NULL,
    finding_id VARCHAR(128) NOT NULL,
    action VARCHAR(16) NOT NULL,
    actor VARCHAR(256) NOT NULL,
    at VARCHAR(40) NOT NULL
);
```

Actions are resolve/reopen; `at` retains ISO timestamp text. `audit_id` is the
logical action identity; finding identity is not unique. Current initialization
does not declare a primary key, foreign key or index.

## Registration and cross-session contract

Call `services.AddPersistence(database, repositoryRoot, seedRoot,
authorizeEmployeeQuery: optionalTrustedPredicate)` from the host composition root.
It rejects a second database registration, initializes SQLite schema only,
and registers Gold read/write/query ports, seed access, unit of work and
`IClientCalculationRunner`, plus every operational port. Deployed migration
administration remains with the existing Python operator scripts.

`IClaimRepository` and `IClaimSink` resolve the same `ClaimRepository`;
`IManualOverrideRepository` and `IBaseYearOverrides` the same override repository;
`ILookupStore` and `ILookupReader` the same lookup store. The host must register
Domain `ClientCalculation` with its existing source/rule/clock collaborators,
then invoke the transactional runner. No HTTP or host hook was edited.

Sources consumes `ISeedData` for raw staged source tables and `ILookupReader`
for effective-dated tenant/global lookup facts. It owns source projection,
lookup priority, fiscal strictness and version fingerprints. The future reset
coordinator invokes `SeedImporter.Load` and independently cleans artifact bytes.
Artifact downloads/resolutions must record their access result through the
metadata port; this adapter stores no bytes or browser SAS.

W2 run/latest handlers must use the shared durable destination and runner.
Duplicate storage identities are repository conflicts; a new identity may
legitimately append same-cell history. W2 implements duplicate-create request
idempotency or HTTP 409 rather than banning history. Client binding failures
map to JSON-detail 422. Authorization and failed-command auditing belong to
the mediator/host, not a fabricated persistence authorization stage.

Duplicate storage identities currently throw `InvalidOperationException`,
without invented application error codes; W2 handles the duplicate-create
boundary specifically rather than mapping every invalid operation to 409.
Draft version/live-code conflicts use Domain `DraftConflict` (`draft_conflict`).
Owner/tenant/expiry-invalid lease mutations return false, as the queue contract
requires. `TenantScopeViolation` identifies adapter binding violations;
`AmbiguousCommitException` requires identity reconciliation before retry.
Native storage errors propagate rather than masquerading as successful reads.

The required report/status ownership conflict was resolved by the conductor's
repair instruction. No application consumer, shared solution file or other
session's central package marker was changed. Package versions selected in the
persistence marker are SqlClient 7.1.2 (MIT), Sqlite 10.0.0 (MIT) and patched
SQLitePCLRaw bundle 2.1.13 (Apache-2.0). The existing DI abstractions are reused;
the test project references the installed ASP.NET framework for real container
integration tests without adding a package.

## Final gates and live limits

`dotnet build -warnaserror` passed on the final solution in 34.46 seconds with
zero warnings/errors. `dotnet format --verify-no-changes` passed. The complete
non-heavy solution gate passed: 18 Domain, 152 parity, 13 architecture and
123 persistence cases at its build snapshot; the final persistence snapshot,
including two added real-container integration cases, then passed 125/125.
The parity project took 12 minutes 23 seconds; final persistence took about
two minutes under concurrent validation load. No comparison was weakened.

All commands run from `dotnet` with the pinned .NET 10 SDK. The conductor's
repeated missing-environment failure is now addressed persistently:
`Directory.Packages.props` selects the owned `Oracle.runsettings` only for
`TaxCredit.Parity.Tests`, when both `TCC_PYTHON` and an explicit
`RunSettingsFilePath` are absent. The settings inject the task-approved
CPython 3.12 path into the test host and disable exploratory interpreter
override. Explicit caller environment/settings remain authoritative.
The interpreter resolver still checks the version and still fails for an
absent executable or an unsupported interpreter; no resolver/test was weakened
and no machine/user environment was changed.

This is a narrow cross-project test configuration in the already owned central
file, required by the conductor's second repair request. It is not a package
change or an application runtime default. A plain `dotnet test --filter
'Category!=heavy'` no longer relies on a prior shell's environment.
The post-repair plain command chain passed with both oracle environment
variables removed: build 16.92s with zero warnings/errors, format verification,
18 Domain, 152 parity (10m17s), 125 persistence (1m07s) and 13 architecture
tests. Its exit code was zero.
The previously reported missing-oracle failures are configuration failures,
not justification to weaken the oracle resolver or certify .NET 11.

SQLite publication/reset/concurrency and fake native parameter/retry/token
checks are runnable hermetic evidence. Live Warehouse writes, concurrent
publication, key enforcement, token refresh/pooling, decimal/date/AVG metadata
and source parity remain unmeasured. No supported bulk-copy path is assumed.
The unchanged M-01 ingestion override and multi-program credit-math behavior
remain owner fix candidates because changing them changes certified figures.
