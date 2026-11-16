# DraftsRuns implementation and halted integration handoff

## Outcome

All 23 operation handlers and endpoint mappings are implemented in the
allocated feature folders. The stage-1 slice is commit `29181ed`; subsequent
commits contain lifecycle, catalogue, client runs, base-year work and focused
evidence. **This is a halted delivery, not a passed W2 gate.**
`HALT-routes_drafts_runs.md` records the mandatory ownership stop.

No product Python, certified Domain, shared executor, persistence adapter,
shared registration, existing framework test, infrastructure or remote was
changed. No package was added. No live service was contacted.

## Callable operation map

All routes below are under `/api/v2`. JSON bodies use the captured snake-case
contract. Commands and queries traverse the existing mediator; HTTP translation
is feature-owned. Shared authentication, client authorization, rate limiting,
request validation and exception translation remain active.

| Method and suffix | Behavior and application implementation |
| --- | --- |
| GET `/program-drafts` | `DraftReads`: status filter and count-first BigInteger paging |
| POST `/program-drafts` | `DraftCommands` / `DraftLifecycle`: normalized unique code, scaffold, creation event |
| GET `/program-drafts/{draft_id}` | `DraftReads`: saved documents, lifecycle metadata, ordered history |
| PUT `/program-drafts/{draft_id}/documents` | Optimistic `expected_version`, editable-state guard, bounded documents, review invalidation |
| POST `/program-drafts/{draft_id}/validate` | Real pack/schema, identity, citations, TODO and customer-data checks |
| POST `/program-drafts/{draft_id}/request-review` | Requires current valid saved content |
| POST `/program-drafts/{draft_id}/review` | Approve or request changes; configured second-reviewer separation |
| POST `/program-drafts/{draft_id}/preview` | `PreviewDraft`: designated committed synthetic sample only |
| POST `/program-drafts/{draft_id}/withdraw` | Versioned withdrawal with lifecycle event |
| POST `/program-drafts/{draft_id}/export` | `ExportDraft`: approved current content, real ZIP, modeled local-write refusal |
| GET `/program-drafts/{draft_id}/export/manifest` | Saved immutable export metadata, not a new export |
| GET `/programs` | `ProgramCatalogue`: existing registry and authored rule files |
| GET `/programs/{code}` | Registry detail, authored years and engagement context; unknown is 404 |
| POST `/run-batches` | `StartBatch`: normalized selection, dry-run summary or durable acceptance |
| GET `/run-batches` | `ReadBatches`: authorized batch list, counters and paging |
| GET `/run-batches/{batch_id}` | Visible-only detail, selection digest, status and liveness |
| GET `/run-batches/{batch_id}/items` | Authorized item filtering and totals before paging |
| POST `/run-batches/{batch_id}/cancel` | `ControlBatch`: queued versus active work, whole-batch entitlement |
| POST `/run-batches/{batch_id}/retry-failed` | Failed-only retry; cancelled and successful work are not requeued |
| POST `/clients/{client_id}/runs` | `ClientRuns`: synchronous shared transactional runner; body field is `year` |
| GET `/clients/{client_id}/runs/latest` | Durable successful manifest destination; never-calculated client is 404 |
| POST `/clients/{client_id}/units/{unit_id}/base-year` | `SetBaseYear`: append-only override and force-calculation queue work |
| GET `/clients/{client_id}/units/{unit_id}/rebase` | `RebaseUnit`: Gold-only series, `base_year` query, certified year-specific pricing |

Batch start accepts `kind`, `scope`, `program_code`, `tax_years`,
`skip_unchanged`, `force`, `include_code_commit`, confirmation and
`idempotency_key`. Replay is requester-scoped: a repeated key returns its
original accepted batch even when the new body differs, after rechecking
entitlement. Dry runs enqueue nothing. Normalized selected-year order is kept.
Nested batch error objects are preserved; draft errors use the
code/reason/remedy family inside `detail`.

The F-14 reader direct-run and batch-dry-run exceptions are retained.
Other writes use Writer policy. Draft reads do not invent an author check.
Acting-principal ordering is inherited, not bypassed by feature handlers.

## Completed orchestration versus inherited machinery

New here: durable HTTP acceptance, real preview selection, idempotency,
authorized reads and controls, direct/latest endpoints, override-to-queue
orchestration, draft lifecycle/export and program catalogue.

Inherited: finite Worker, polling, claim competition, per-client live leases,
attempt/backoff/reaping, source observations, certified content fingerprint,
unchanged decisions, durable work/run identity, accepted-manifest recovery,
atomic Gold/manifest/claim/item publication and contract drain/reset gate.
The Worker executable needed no changes. Handlers never call a second
calculation implementation or maintain an in-memory batch list.

The inherited singleton mediator resolves handlers from its root provider.
That retained scoped source readers across contract profile resets. The owned
API module now wraps each feature dispatch in a fresh DI scope, preserving
the existing policy/audit pipeline and shared mediator implementation.
An actual P1-to-P2 source regression test proves the source changes rather than
mistaking this for environment-variable precedence.

Batch filtering follows one coherent portfolio candidate: boolean nearness,
effective engagement outcome, one candidate satisfying all cell filters, and
whole-history declining overlay. Restricted reads recompute counts, scope
digest and program-item metadata from visible items only. Queue liveness does
not leak hidden global work.

## Evidence

### Drafts and export

- Final owned fast gate: **8 passed**, no failures, about one second of test
  execution. Includes lifecycle, invalid controls, restricted reads/filters,
  stable reviewer identity, bundle oracle and lease-expiry rollback.
- Invalid scaffold cannot request review or export. Stale versions, wrong
  identity, excessive nesting and huge nonnegative offsets are modeled.
- Approved content traverses save, validation, review request, second-person
  approval, ZIP export and manifest verification through the actual repository.
  Repeated exports retain stable member content.
- Reviewer separation uses stable effective OID and compatible tenant as well
  as actor text; changing a display address cannot self-approve.
- Reviewer setting defaults to false locally and true outside local.
  Explicit true/false spellings match Python; invalid configuration fails
  explicitly.
- Application limits are 30 year documents, 8,000 canonical codepoints per
  document, 12 container levels and strict UTF-8. Years and identity are checked.
- Preview client data is refused; omitted client ID is a modeled 422 rather
  than a missing-dictionary-key exception. Arbitrary payroll is never loaded.
- `BundleOracleTests` compares **every exported member byte** against a
  CPython 3.12.13 production-bundle fixture. It includes Unicode, control
  characters, negative zero, scientific notation, large integers, review
  history, JSON indentation/newline rules and per-file hashes.
  `export_bundle_oracle.py` regenerates the committed synthetic oracle.
  This is stronger evidence than treating ZIP member hashes as container noise.

### Worker, direct runs and base years

- Earlier full owned run: **11/11 passed**, 8m31s. Four expensive tests are
  tagged `Category=heavy`; the new lease test subsequently made 12 unique
  feature tests in total.
- `Http_accepted_work_completes_in_finite_worker_and_reopen_retains_one_publication`
  passed in 34s: ordinary HTTP acceptance, actual `--once` Worker process,
  separate reopened connection, successful queue/manifest/Gold/claim checks,
  idempotent acceptance and no second publication on drain.
- Direct-run/latest/never-run passed in 20s and proves the correct **P1 TY2025
  population 107 / Min-Max 77 / Pay Period 72**.
- Same-timestamp save/change/clear/later-save passed in 8m10s. All four
  recalculation batches succeed; persisted override write order wins; an
  unchanged final save records/enqueues nothing.
- Gold-only rebase reads no payroll and matches the recorded synthetic unit's
  base-year-2022 result: annual total 0, prior total 120820, delta -120820.
- The new injected-clock test advances time **inside calculation**, after the
  entry heartbeat and before precommit ownership verification. Expiry raises
  `RunLeaseLost`, rolls back the manifest and completion, preserves the leased
  item, and permits reaping/reclaim. It does not merely test expiry before work.
- Inherited persistence tests provide independent publishers/claim competition,
  at-most-one client lease, heartbeat/lost lease, reaping/backoff, cancellation
  rollback/refunded attempts and accepted-manifest recovery. The complete
  persistence fast project passed **129/129** in this session's full gate.
- Existing runtime queue tests cover actual drain, assessment-only work and
  classified source outage behavior. No second executor was introduced to
  manufacture these results.

### Whole-solution gates and stop

`dotnet build -warnaserror`: passed, zero warnings/errors.
Whole-solution `dotnet format --verify-no-changes`: passed, including the final
rerun after the assertion-only test correction.

`dotnet test --no-build --filter "Category!=heavy"` completed all eight test
projects: **720 total, 711 passed, 9 failed**. One new lease assertion was
corrected and all 8 owned fast tests then passed. The remaining eight shared
test failures are detailed in the HALT report: six endpoint-collision cases,
one old 501 expectation, and one standalone provider-composition failure.
No shared test was edited or disabled.

The seven non-API fast projects passed: architecture 16, Domain 18, auth 147,
AI 167, persistence 129, sources 108, parity 61. The full API run had 65 passes.
Do not treat the focused rerun as a green whole-solution fast gate.

## Semantic replay evidence and limits

Replayed complete `p1_program_drafts`, `p2_run_batches` and `p2_reads_writes`
with their setup exchanges, fresh isolated SQLite/byte roots, approved Python
3.12.13, semantic comparison and no concurrent Worker. Absolute diagnostics:

- `dotnet/artifacts/drafts-runs-replay/board-scoped.json`
- `dotnet/artifacts/drafts-runs-replay/scoped/p1_program_drafts.json`
- `dotnet/artifacts/drafts-runs-replay/scoped/p2_run_batches.json`
- `dotnet/artifacts/drafts-runs-replay/scoped/p2_reads_writes.json`

These are ignored local diagnostics, not required tracked deliverables.
The policy-free wrapper reports **243 group cases, 35 passed, 208 failed
(14.40%)**. Per-scenario raw failure records (not failing-case counts) are
353 across 175 draft exchanges, 254 across 64 batch exchanges, and 1166 across
74 reads/writes exchanges. Many latter routes are not owned by this group.
The wrapper does not implement policy tiers or the improvements cap and
misclassifies some framework method variants; it is **not** the conductor's
exact-template denominator. No adjusted 98% result is claimed.

Concrete differences:

- Deterministic identity draw offsets propagate into draft/batch/run IDs.
  No dummy ID draws were inserted to reproduce recording startup effects.
- Validation verdicts/paths are retained; English and Pydantic error-detail
  members differ. Messages are free by task policy, not calculated figures.
- Successful durable manifests replace the disconnected F-18 latest-run 404s.
  Actual manifests also alter operational skip-coverage/never-run summaries.
  Those numeric differences are **not waived** here.
- Real client footprints yield a resolved program where the historical batch
  recording held null. Correct portfolio filtering can select clients where
  the disconnected recording refused. No fake program/selection was emitted.
- Recorded `preview-client-refused` actually succeeds under Python's synthetic
  environment; this task expressly requires designated-sample-only preview.
  The feature refuses that request instead.
- Direct calculation has inherited `validation.queries_run=17` versus recorded
  20. This shared numeric difference was not changed or waived.
- `p2_reads_writes:client2001.unit-rebase` depends on the unimplemented,
  unowned ReadsCalc units route. Capture failure substitutes the literal
  `capture-failed` as unit ID. The exact recorded real unit URL succeeds and
  its numeric result is covered by the owned integration test. The handler
  does not invent an alias for failed setup.

The final all-12-scenario run and full improvement classification were
interrupted by the mandatory ownership stop. The register is deliberately
narrow; it is not a blanket waiver for changed numbers or byte hashes.

## Remaining boundaries and decisions

1. Update shared test fixture composition/placeholder expectations under an
   explicitly expanded allocation, then rerun the full fast/replay gates.
2. Decide the standalone provider-registration contract. Application scanning
   currently sees the new handlers without discovering API-owned helper
   registrations; normal API discovery is proven but standalone validation
   fails. This is unresolved.
3. Default lease is 600 seconds. Certified synchronous computation has no
   periodic heartbeat; renewal precedes publication and precommit checks
   prevent expired ownership from publishing. Long-run sizing is unmeasured.
4. Native schema additions for write sequence, work identity and source
   observations were inherited/documented, not live-provisioned or certified.
5. Saving an override and accepting recalculation are separate repository
   transactions. Queue failure after override save can leave saved intent
   without accepted work; unchanged resave currently does not repair it.
   A truly atomic outbox/publication seam is outside this allocation.
6. Source/claim dependency failures propagate rather than silently fabricate
   healthy preview/validation summaries. Python has some logged fallback
   behavior; availability equivalence remains unmeasured.
7. M-01 ingestion overrides of year-resolved statutory fields and the
   first-program credit-math behavior remain inherited, figure-sensitive
   owner decisions. Neither was changed.
8. Finish exact-template replay classification, including operational numeric
   differences and the shared validation query count. Do not waive figures
   or claim the improvements cap passed without the conductor's evidence.

## Resumed conductor verification

The latest complete conductor result is **79/323 passing (24.5%)**, not the
earlier three-scenario wrapper denominator. It rejects numeric-looking UUID
strings and the honest `never_run=0` after a successful durable run. These
seven distinct cases alone limit compliant behavior to at most 97.83% under
the current gate, even if all other cases passed. The task explicitly
forbids dummy identity draws and historical disconnected-manifest behavior.

A fresh build and format check passed; the fresh entire fast suite is
**712 passed / 8 failed / 720 total**, with exactly the previously identified
unowned failures and no failing owned tests. The query-count mismatch was
traced to the shared registration's literal 17; the HTTP handler does not
calculate that field.

The HALT report now contains the ten exact conductor rejection cases,
numeric upper-bound calculation, shared source seams and required policy
decisions. No shared fixture, production registration, gate or comparison
was modified. The hard stop remains active; this section is not a new
completion or replay-pass claim.
