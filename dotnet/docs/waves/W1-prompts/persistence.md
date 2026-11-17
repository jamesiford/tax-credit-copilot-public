# Persistence adapters: Gold and operational stores, run queue, seed importer

Session `persistence` of wave `W1`. You run unattended: nobody will answer questions, so do not ask any.
Worktree: `C:\Projects\GitHub\tcc-dotnet-w1-persistence` (branch `dotnet/w1-persistence`, created from `dotnet/integration`).

---

## Pre-approved decisions (policy)

The owner decided these in advance. Follow them without asking. If something needs a decision that is not covered here, choose the reading closest to the documented design and the Python behaviour, record it in STATUS.json under `needs_human`, and continue.

- **parity**: Equivalent behaviour, not bug-for-bug. The target is the designed functionality and the contract a client depends on: the same routes and methods, authentication and authorisation, request and response fields and their types, the meaning of each status code, money as a decimal string with its scale, and the same calculated figures for the same valid input. Do not reproduce defects, accidents of Python, FastAPI or Pydantic, or artefacts of the recording harness (plain-text error bodies, key order, number lexemes such as 5.0 versus 5, byte-level headers and wording, HEAD and trailing-slash quirks, reflected CORS headers). Never write code whose only purpose is to reproduce a defect or a framework artefact. Where the Python behaviour is a bug or an accident, implement what the design, the ADRs, the docs or sound engineering intend, and record it in dotnet/docs/improvements/<session>.json (see improvements_register). If the same issue turns up naturally in the .NET code, that is acceptable; note it as a finding.
- **parity_tiers**: The replay runs in semantic mode (values equal; key order and number lexeme free). Tier A (certified-figure routes and every gateway tool result): the values must be equal, and a changed figure is never an improvement. Tier B (everything else with a JSON body): values equal. Tier C (error responses): keep the error shape family (a JSON body with `detail`, as the clients read it) and the right status; the message text is free. Tier D (zip and xlsx container bytes, timing, model output): out of scope. Anything else that differs from a recording for a good reason goes in the improvements register, not into reproduction code.
- **python_oddities**: Fix defects instead of reproducing them. F-2 to F-6 (plain-text 500s): return the JSON error family with the correct status, a 4xx where the cause is a client error, and never a stack trace. F-8 (duplicate claims): handle duplicates as the claims design intends (idempotent or a 409), and record which. F-14 to F-16 (inconsistent writer checks): apply the writer check consistently to every route that writes. F-1 (a GET that never returns because magnitude is unbounded): bound it and refuse out-of-range values with a 422. F-17 and every other entry in contract/FINDINGS.md: apply the same principle; read the finding first. Exception: if fixing something would change a calculated figure, a stored value or an authorisation outcome for a valid request, keep the Python result, and list it under needs_human as a fix candidate for the owner.
- **oracle**: CPython 3.12 is the only oracle interpreter. The recordings, goldens and seeds were made on it.
- **target**: net10.0 only. Do not use .NET 11 features or preview packages unless a decision below names them.
- **delta_read**: No Delta library at runtime. Payroll is read over the lakehouse SQL analytics endpoint behind an IPayrollSource port. For the data-version stand-in use the design recommended in dotnet/docs/PLATFORM-RISKS.md if that file exists; otherwise use a per-account fingerprint of row count plus the maximum modified date, record it with each run, and list the limitation.
- **warehouse_writes**: Use multi-row parameterised INSERT batches (the Python adapter's method) unless dotnet/docs/PLATFORM-RISKS.md proves a faster supported bulk path on Fabric Warehouse. Retry on SQL errors 24556, 3960 and 1205. Never use EF Core migrations against Fabric Warehouse.
- **mediator**: Use the in-house mediator (ADR 0003). No MediatR, and no libraries with commercial licences. Check a package's licence before adding it and record it in the session log.
- **scope_cuts**: Out of scope: the 10 sealed /api/workspace routes (answer exactly what the recordings show when the reference extract is absent), tools/reference_*, web retrieval inside tools/rules_ingestion beyond its HTTP surface, the mock AI gateway, and the ops scripts (migrations, grants, seeding, smoke checks), which stay in Python for now.
- **external_systems**: Never contact live Fabric, Foundry, Entra or any customer system unless the session's task names it and its approval variable is set. The hermetic seeds under contract/seed are the data source for development and replay.
- **numeric_guard**: Agents narrate and tools calculate (ADR-008). The numeric guard ports as is, with the same refusals.
- **heavy_tests**: Tag every test that runs longer than about 20 seconds or loads more than 20 MB as [Trait("Category", "heavy")]. A session's own gate is build, format, fast tests and its replay groups; heavy suites run at wave end and at the final gate.
- **route_ownership**: Each route group lives in its own folders: src/TaxCredit.Application/Features/<Group>/ and src/TaxCredit.Api/Endpoints/<Group>/ plus tests under tests/TaxCredit.Api.Tests/<Group>/. A group registers itself through an endpoint-group class discovered by the host; no shared file is edited to add or retire a route.
- **schema_messages**: Pack and draft validation (domain slice, finding on JsonSchema.Net): verdicts, keywords and paths must be correct; the English wording of messages is free. Record any case where a verdict differs from Python's jsonschema in dotnet/docs/pack-validation-deviations.md, with the reason.
- **ingestion_override**: Captured ingestion overrides a year-resolved pack's wage_basis, measuring_date and pay codes (domain finding M-01). This changes calculated figures, so keep it as ported and list it under needs_human as a fix candidate for the owner. Read the finding and the ADRs first: if the design clearly says otherwise, say so in the report, but still do not change it without the owner's decision.
- **multi_program_credit_math**: In credit_math a state with several programs prices its first program, as Python does; the typed refusals live in the run-resolution code (_client_run, program_defaults), which is ported. Do not add a refusal to credit_math. List this under needs_human as a fix candidate for the owner, since it affects figures.
- **improvements_register**: Each deliberate difference from the recorded Python behaviour is an entry in dotnet/docs/improvements/<your session>.json: {"improvements": [{"id": "IMP-<session>-1", "kind": one of defect_fix, error_text, wire_incidental, framework_default, "route": "METHOD /path/template", "case": optional text matching a recorded case id, "categories": optional list of replay categories, "path_prefix": optional JSON path, "finding": "F-n or empty", "reason": what was wrong and what the .NET host does instead (at least 20 characters)}]}. The replay gate treats failures covered by an entry as waived and shows them on the board and in the wave report for the owner to review; a changed number is never waived, and a group that relies on the register for more than the policy limit of its cases fails.
- **domain_slice**: The domain slice is certified (dotnet/docs/DOMAIN-SLICE-REPORT.md): build the application layer on top of it and do not re-port or re-verify its modules. Anything marked partial or pending in dotnet/docs/port-map.md and needed by your routes is yours to finish.

---

## Your role

Build the durable persistence boundary for the certified calculation pipeline and the route sessions that follow W1. Implement Gold reads and writes, operational repositories, the run-batch store and queue, and `SeedImporter.Load(profile)` in `dotnet/src/TaxCredit.Infrastructure.Persistence/`, with adapter tests in `dotnet/tests/TaxCredit.Infrastructure.Persistence.Tests/` and additional application contracts in `dotnet/src/TaxCredit.Application/Ports/Persistence/`.

The certified implementation is already present. `dotnet/docs/DOMAIN-SLICE-REPORT.md` proves the engine-to-payload path, not database persistence. Connect to `TaxCredit.Domain.Pipeline.IGoldWriter`, `IClaimSink` and `IBaseYearOverrides`, and the existing Domain repository interfaces; do not replace these with unrelated interfaces of the same name. Complete the richer application read/write contracts alongside them. A real adapter must be consumable by `ClientCalculation` without modifying Domain.

Own artifact metadata, access audit and channel state, not artifact bytes. Own lookup storage, not source projection/resolution. Python's source SQL modules belong to .NET Sources. Leave HTTP/host hooks, handlers, auth, AI, existing Infrastructure/Domain, shared solution files and other application folders untouched.

## Preflight

Read `dotnet/docs/DOMAIN-SLICE-REPORT.md`, `dotnet/docs/slice-domain-log.md` sections DS4, DS5, DS6, GP and CAP, `dotnet/docs/port-map.md`, `dotnet/docs/findings.md`, `dotnet/docs/PLATFORM-RISKS.md`, and `contract/CONTRACT-REPORT.md` sections 3-5 and 8. Inspect `contract/FINDINGS.md`, `contract/seed/README.md`, both seed manifests, `contract/harness/gold.py`, `contract/harness/world.py` and `contract/harness/control.py`.

Inspect prepared projects, central package markers and Domain interfaces in `Pipeline/PipelinePorts.cs`, `Claims/`, `Warehouse/` and `Programs/`. W1 preparation creates project references. Skeleton ownership overlaps Application: confine additions to `Ports/Persistence/` and document names for integration.

Establish worktree-local imports on the rendered CPython 3.12 oracle. Read `backend/tests/contracts/conftest.py`; not every repository fixture is offline by default.

Settle SQLite numeric seeds versus scaled Gold/claims and successful-manifest/current-row consistency first. `PLATFORM-RISKS.md` establishes only token `SELECT 1` and zero scratch objects; writes, bulk copy, decimal/date metadata, pooling, source parity and versions remain unmeasured. Use SQLite and fake SQL Server/Warehouse transports, not a new live experiment.

## Stage P1: prove the tenant and value boundary

Read `backend/infrastructure/persistence/tenant_sql.py`, `tenant_marker.py`, `sql_connection.py`, `sql_errors.py`, `pool_policy.py`, the SQL Server DDL and the six files under `migrations/`. Define a small dialect/connection boundary that permits real SQLite execution and parameter-inspection/fault-injection tests for SQL Server and Warehouse. Use explicit SQL projections and typed values; keep provider details outside application ports.

Implement SQL Server/Azure SQL connections with `Microsoft.Data.SqlClient` and injectable Entra token acquisition for `https://database.windows.net/.default`. Test token scope/refresh, encrypted connection settings and disposal with doubles. Warehouse shares this transport, not an assumed bulk-copy path.

Implement tenant binding before repositories. Cover markers immediately after `WHERE` and `ON`, aliases, several markers, parameters preceding markers, parameter-count mismatches, question marks inside quoted literals, missing or misplaced markers, and insert rows with a missing client column or a different client. Source tenant columns are a configured closed set; do not turn arbitrary column names into a tenant escape. Cross-client portfolio reads and worker/reaper operations need explicitly named, logged exemptions, not an unscoped public executor that ordinary repositories can use.

Port the relevant scenarios from `backend/tests/test_tenant_sql.py` and `test_tenant_sql_column.py`, especially `test_parameters_before_the_marker_keep_their_position`, `test_an_aliased_marker_in_a_join_binds_each_side`, `test_insert_refuses_another_clients_row_or_no_client_column` and `test_an_exemption_needs_a_reason_and_logs_every_use`. Prove a rejected statement never reaches the fake cursor. Exercise two synthetic clients with identical program, year and local IDs so a missing predicate is observable.

Define `GoldCell`/`PyDecimal`/date conversions preserving decimal values/exponents. Claims retain recorded `"1234.50"`, `"1234.5"` and `"1000.0"` strings. Gold DDL and SQLite harness scales differ: select a representation using small Python-adapter/recorded-body round trips, not a money-to-double shortcut. Document provider mappings and unresolved live scale.

Checkable result: tenant violations are refused before execution; valid parameters retain their order; money/date round trips match the applicable recorded fields; the dialect boundary is usable without credentials or a running server.

## Stage P2: schema and deterministic seed reset

Implement adapter/importer schema administration from `docs/data/schema/tcc-schema.sqlserver.sql`, migrations and Python SQLite schemas. Explicitly map qualified names, types and migration constructs to SQLite; a manifest-only dynamically typed table does not prove schema fidelity. Document local constraints/precision mapping. Operator scripts remain Python.

Implement `SeedImporter.Load(profile)` for P1 and P2 and make the destination/configured seed root explicit in the importer instance. It should be a library callable by the future reset hook, not an HTTP endpoint or a new operator script. Whitelist the profiles and manifest table paths, stream gzip JSON Lines, verify `content_sha256` against decompressed bytes, verify declared columns and row counts, and reject malformed rows or unexpected tables before accepting a new state. The committed gzip `sha256` describes the shipped file; it is not the cross-interpreter identity of a table.

Respect the three seed namespaces. `source/*` contains source-shaped tables, not Gold; load or stage these through an explicit seed-data boundary for the Sources adapter without implementing its projection. `ops/run_manifest` belongs to the run store. `operational/program_claim` and `program_engagement` map to their actual operational repositories, not to a second disconnected claims database. Other operational tables start empty. Reset must also clear newly created batches, leases, drafts, findings, overrides, artifact metadata and channel state. Byte-store cleanup is the separate adapter's responsibility and should be exposed as a documented integration requirement.

P1 has 11 tables and 18,111 total rows: 9,477 source pay periods, 376 eligibility, 5,281 period facts, 2,898 matrix, 4 method summaries, 40 installments, 16 month summaries, 16 unit-year rows, 1 manifest and 2 claims. P2 has 20 tables and 390,660 rows, including 197,094 Payroll rows, 4 fiscal rules, 4 manifests and 22 claims. Validate every manifest count, not just these examples.

Make replacement transactional or stage it into a new destination before activation, so truncated gzip, hash mismatch or an insert failure does not leave a half-reset store. Test P1 twice, P1-to-P2-to-P1, unknown profiles, a corrupted table and restart/readback. Repeated reset must restore the same starting data rather than append duplicate current rows. Verify manifest API checks at repository level: TY2025 min-max evaluated populations are 107 for P1 and 202/164/137/125 for P2 clients 2001-2004. These are seed populations, not the separate 81/51/49 calculation certification figures.

Checkable result: every profile table is accounted for, reset is repeatable and failure-safe, hashes/counts are checked, and both claims and Gold readers see the imported state.

## Stage P3: implement Gold reads over the imported model

Use `backend/application/gold_read_port.py` as the complete inventory, not only the routes named in the brief. Declare the application read port and typed options/results for run identity and connection scopes; unit grid, years, months, installments, credit columns and totals; employee and near-threshold unit cohorts; run series and onezero matrix; risk/proximity and cohort periods; eligibility and employee drill. Preserve all optional filters, method/program distinctions, defaults and return-presence semantics.

Port the SQL and post-query shaping from `backend/infrastructure/persistence/gold_reader/`, including the reader base, statement builders and envelope. Implement provider-specific paging and date/string functions at the dialect boundary. `contract/FINDINGS.md` E-2 records why `SELECT DISTINCT TOP n` needs special treatment in the SQLite harness; both distinct paging and ordinary paging need executable SQLite tests. Port filter whitelists and parameterized predicates using the existing Domain `GridFilter` where appropriate, with dialect-specific LIKE escaping rather than blindly sending SQL Server bracket syntax to SQLite.

An uncalculated client returns no successful run and the documented empty collections/envelope, not invented zero figures. Resolve `latest_run`, `run_in_flight` and program-scoped reads against the same durable manifest store as writes. Include pagination past the end, empty cohorts, unknown record tokens, same employee in several units, both methods, and two programs sharing a state. Scope all employee-grain reads through the selected successful run; those tables do not carry `is_current`.

Add adapter-level comparisons grounded in `contract/recordings/p1_reads.jsonl`, `p1_query_edges.jsonl` and `p2_reads_writes.jsonl`, isolating stored/read values from HTTP binding. Port `backend/tests/test_gold_read_port.py`'s completeness intent. Include `p1_query_edges:unknown.client-huge` as a range-refusal test at the binding boundary, not a reason to emulate an overflow crash. `p2_reads_writes:client2002.run-latest-after` is F-18, an in-memory-profile limitation: it does not justify hiding a durable successful manifest.

Implement governed Gold queries from `sqlite_data_query.py`/`warehouse_data_query.py` with catalogue/tenant enforcement, not arbitrary caller SQL. E-7 records missing query-service wiring; document registration.

Checkable result: the declared Gold surface is implemented, imported populations and selected read envelopes agree with recordings, and negative tenant/program/token cases cannot expose another client's rows.

## Stage P4: make the certified payload durable

Implement the existing `IGoldWriter.WriteRun(GoldRunPayload)` and `Validate()` contracts, bridging richer application errors/results where needed. Read `backend/infrastructure/persistence/warehouse_gold.py` in full. Preserve all seven `GoldColumns` lists and the manifest columns; reuse Domain projections instead of computing credits in a writer.

The manifest identifies the run before its rows become visible. Only `unit_year_master` and `unit_credit_installment` carry `is_current`; supersession is client-program scoped across the recalculated series, not just the requested year. Successful completion, prior-manifest supersession and row currency must agree. Python's documented intent is to retain the prior successful run on failure, but its versioned-pair sequence retires old rows before inserting all new ones. Test failure at that exact boundary and implement safe publication using the supported dialect transaction/staging semantics. Do not claim a process lock alone protects separate replicas or a Warehouse publication strategy is live-proven.

Test parameterized multi-row inserts under the 2,100-parameter ceiling/headroom with narrow/wide tables and hostile text. Classify native conflicts 24556/3960/1205, rollback/retry a safe whole transaction with bounded attempts/injected delay; permanent errors propagate. Distinguish transport failure before commit from ambiguous post-commit reconnects to prevent duplicate accepted rows.

Implement named section-9 checks: duplicates, orphans, invalid vocabulary, missing decline reasons and installment/current consistency. Keep established formulas. Reaping marks stranded runs failed without inventing completion timestamps.

Build a persistence-side capstone in your owned test project: construct `ClientCalculation` using the real writer, real claim sink and override reader; pass the same fixture payroll, rules and injected clock/IDs used by the certified pipeline. Compare typed pre-storage payload cells against `parity/goldens/gold_payload.jsonl.gz`, then read stored rows back at the documented DDL/provider representation. Keep payload equality distinct from database scale conversions. The existing `ClientCalculationParityTests` uses an internal capturing world and cannot be changed from this session; consume public production entry points and golden data rather than copying its private harness. Retain its passing behavior while adding actual persistence coverage.

Checkable result: a valid run survives reopening the store, a rerun supersedes only its client-program, injected failures cannot publish partial figures, validation detects corrupted invariants, and the real-writer capstone preserves certified payload values.

## Stage P5: operational stores and competing workers

Complete claims/engagements, findings/resolutions/audit, manifests, overrides/lookups, artifacts/accesses, channel audit/confirmation/download state, drafts/events and run batches/queue. Inventory corresponding `sqlite_*`/`warehouse_*`, `program_draft_store.py`, `run_batch_store.py` and `run_batch_queue.py` methods. Preserve histories, scope, versions, hashes, expiry, durability and duplicate IDs through existing Domain interfaces.

For claims use `backend/tests/contracts/test_contract_claims.py` and `test_claim_repository_contract.py`: recorded claims round trip; a new record closes one live cell; same-day history keeps all IDs with the live row last; empty program/year selectors mean empty; portfolio coverage spans only requested clients. F-8's `p1_writes:claims.create-duplicate` is an HTTP duplicate-create defect, not a reason to prohibit legitimate history append. Choose a repository-level duplicate identity/conflict contract that leaves route-level idempotency possible and describe it for W2.

For lookups port `sqlite_lookups.py`, `warehouse_lookups.py` and the storage assertions in `test_app_owned_lookups.py`: tenant/global rows, effective dates, close-not-delete replacement/removal and audit. Publish a neutral lookup-reading contract for Sources consumption; resolution priority, fiscal strictness and pay-code policy belong there. For artifacts use the repository half of `backend/tests/contracts/test_contract_artifacts.py`: supersede only the matching client/kind/year, retain other years and record access outcomes. The byte-store half belongs to the other session.

Queue tests come from `test_run_batch_store.py` and `test_run_queue_cost.py`. Exercise create/read counters, requester-scoped idempotency, queue ordering, one live item per client, owner-bound heartbeat/finish/requeue/release, backoff, lease expiry and spent attempts, cancel queued-but-not-running work, failed-only retry, and atomic item-finish plus batch refresh. Use separate connections/worker instances against one SQLite database for contention tests; one in-process mutex is not proof. Global claim/reap operations must use the explicit worker exemption; subsequent item updates must verify lease owner and client identity. Preserve the recorded queue-cost budgets where applicable rather than adding a read per item.

Checkable result: each owned store has a method-to-test inventory, histories survive reopen, two-client isolation holds, stale draft/lease writes are rejected, and competing workers cannot run two live items for one client.

## Stage P6: integration evidence

Write `dotnet/docs/PERSISTENCE-REPORT.md`: ports/registration, method/scenario coverage, schema/value mapping, reset/counts, publication/retries, concurrency and real-writer capstone. Separate fake SQL checks from SQLite execution; list live scale/pooling/publication limits and host reset/query/artifact contracts.

Identify cross-session dependencies rather than editing consumers: skeleton wiring, Sources lookup/seed consumption and W2 run/latest/claims handlers. If both parallel adapters need the same absent central package, report the selected version and marker so integration can deduplicate it; do not remove another session's section. Distinguish a runnable SQLite implementation from unverified live deployment behavior.

## Traps to expect

- `contract/CONTRACT-REPORT.md` sections 4-5: money string scale, null versus absent, mixed date formats and run provenance survive storage; framework number lexemes are not a database type specification.
- `dotnet/docs/findings.md` C-01/C-02 and GP-06: Decimal arithmetic and zero exponents are already certified. Database binding is not another rounding pass.
- GP-02/GP-03/GP-04/GP-05 and CAP-01: malformed handmade payloads can reach non-null columns; unreachable months are zero-based positions; inclusion/QC columns have existing constants; synthetic employee IDs are not transformed again; Georgia tier may arrive as an integer for a text column.
- CAP-03/CAP-06: the handler and replay populate method-summary counts differently, and an assessment can fail after rows are written. Do not silently recalculate counts or report a partial run as usable.
- F-18, E-2, E-5 and E-9 in `contract/FINDINGS.md`: in-memory latest-run divergence, distinct paging translation, claims as a run side effect and decompressed seed identity are separate problems.
- Fabric does not enforce keys. SQLite uniqueness may prevent corruption that Warehouse accepts; invariant tests still need to demonstrate the Warehouse-facing checks.

## Evidence this plan is based on

- `C:\Projects\tcc-conductor-runtime\reports\W0.md`: Domain and platform sessions passed their listed checks; the platform pass is not certification of all platform stages.
- `dotnet/docs/DOMAIN-SLICE-REPORT.md`: 19 capstone cases, 12 successful payloads, 390,945 rows/8,017,010 cells and 47 claims certified; persistence and fiscal I/O remain outside that proof.
- `dotnet/docs/slice-domain-log.md` CAP and DS4-DS6: public pipeline seams and repository declarations already live in Domain; capturing parity internals are not reusable application services.
- `dotnet/docs/port-map.md`: `application.gold_ports` and `application.gold_read_port` declarations remain pending; portfolio/discovery are application work, not this adapter's calculation logic.
- `dotnet/docs/PLATFORM-RISKS.md` and `platform-risks-log.md`: SqlClient 7.1.2 token connectivity succeeded, final scratch inventory was zero; PS2-PS8 and decimal/date metadata remain untested.
- `dotnet/docs/adr/0006-ef-core-scope-and-bulk-writes.md`: hand-written Gold SQL and bounded multi-row inserts are the established implementation basis; bulk-copy support is unverified.
- `contract/CONTRACT-REPORT.md` sections 3-5 and 8, `contract/FINDINGS.md`: seed/harness versus deployed storage differences, F-8/F-9/F-18 and E-2/E-5/E-7/E-9 determine adapter tests and limits.
- `contract/seed/README.md`, `contract/seed/P1/manifest.json`, `contract/seed/P2/manifest.json`: namespace/load order, complete row counts, decompressed hashes and evaluated populations define importer checks.
- `contract/docs/replay-spawn-312.md` and `replay-inprocess-312.md`: all 1,769 exchanges matched the Python oracle; these are reference evidence, not existing .NET HTTP certification.
- `parity/goldens/gold_payload.jsonl.gz`, `parity/goldens/gold_payload_input.jsonl.gz` and `dotnet/docs/findings.md`: typed payload evidence and documented GP/CAP traps constrain the real writer.

---

## Gates (checked by the conductor after you finish, mechanically)

- `no_halt`: no HALT.md in the worktree
- `commits_present`: at least one commit on your branch
- `clean_tree`: everything committed
- `not_pushed`: the branch is not on any remote
- `owned_paths`: every changed file is inside your owned paths
- `status_json`: the STATUS.json finish file exists and parses
- `report_present`: the report files named below exist
- `dotnet_build`: `dotnet build -warnaserror` passes on the whole solution
- `dotnet_format`: `dotnet format --verify-no-changes` passes
- `tests_fast`: all tests not tagged `heavy` pass
- report required: `dotnet/docs/PERSISTENCE-REPORT.md`

If a gate fails you will be resumed with its output and asked to fix it. Run the same checks yourself before you finish.

---

## Rules (fixed by the conductor; they cannot be changed by the task)

- **Work only in `C:\Projects\GitHub\tcc-dotnet-w1-persistence`** (branch `dotnet/w1-persistence`). Do not edit the main checkout or any other worktree.
- **Never push, never open a pull request, never change a remote.** Pushing is also blocked mechanically; do not try to work around it. Commit locally in small, sensible commits with the trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- **You may create or modify only:** `dotnet/src/TaxCredit.Infrastructure.Persistence/**`, `dotnet/tests/TaxCredit.Infrastructure.Persistence.Tests/**`, `dotnet/src/TaxCredit.Application/Ports/Persistence/**`, `dotnet/Directory.Packages.props`. Any other change fails a gate. Never edit existing product files (`backend/`, `frontend/`, `infra/`, `scripts/`, `channel_orchestrator/`, `docs/`, `.github/`) unless they are inside your owned paths.
- **The reference is the Python product on CPython 3.12** (`C:\Projects\py312-oracle\.venv\Scripts\python.exe`): it shows what the system is meant to do, but it is not a specification to copy defect for defect. Build the designed functionality and the contract clients depend on; do not reproduce defects or framework accidents. Never change the Python code. Record each deliberate difference in `dotnet/docs/improvements/persistence.json` as the policy describes, and record Python oddities in `STATUS.json` under `findings`. A changed calculated figure is never an improvement. Never loosen a comparison, delete a test or weaken a threshold to make something pass.
- **Nobody can answer questions.** Use the policy decisions above. When a decision is missing, take the reading closest to the documented design and the Python behaviour, record it under `needs_human` in `STATUS.json`, and keep going.
- **Customer-neutral:** no customer names, tenant or server names, identifiers, tokens or secrets in any file, log or report. Synthetic data only.
- **Tests:** tag long-running tests `[Trait("Category", "heavy")]`; the fast gate excludes them. Keep the fast gate quick.
- **Shared files:** put package versions only inside your marked section of `Directory.Packages.props` if your session has one; never add a package another section already declares. Register your services and endpoints from your own project (an `AddXxx` extension or endpoint-group class); do not edit another session's files.
- **Keep a running log** of decisions, findings and gate results in `dotnet/docs/persistence-log.md`.
- **Budget:** you have a limited time and credit budget. Finish each stage with its checks green before polishing, and finish the whole task rather than perfecting one part.

---

## Hard stops (fixed by the conductor)

Write `dotnet/docs/HALT-persistence.md` (what happened, what you tried, what a human must decide), commit it, and end the run if any of these happens:

1. A push, a remote change, a change outside your owned paths, or a destructive command outside your worktree would be needed.
2. A secret, token, tenant or server name, customer identifier or private data would be written to a file.
3. Equivalent behaviour for the designed functionality cannot be reached after three honest attempts on the same item (this is a valid, important result: report it, do not hide it).
4. The Python oracle environment is not CPython 3.12, or imports the wrong checkout, and configuration cannot fix it.

---

## Finish (fixed by the conductor)

When the task is done, or you are stopping at a hard stop, write `dotnet/docs/status/persistence.json` in your worktree and commit it. It is machine-read; it must be valid JSON with this shape:

```json
{
  "session": "persistence",
  "branch": "dotnet/w1-persistence",
  "head": "<short commit>",
  "summary": "<at most ten lines: what was built, what the gates say, what surprised you>",
  "stages": {"<stage id>": "done | partial | skipped"},
  "gates_claimed": {"<gate>": true},
  "deviations": [{"id": "DEV-1", "what": "...", "why": "...", "decision_needed": false}],
  "findings": ["Python behaviour that looks wrong, or traps found"],
  "open_questions": ["..."],
  "needs_human": [{"item": "...", "why": "..."}],
  "reports": ["relative path of each report you wrote"]
}
```

Then print a short summary. The conductor reads your reports and `STATUS.json` to plan the next wave, so write them for a reader who has not seen your session: numbers, evidence, exact error messages, and what the next session can now rely on.
