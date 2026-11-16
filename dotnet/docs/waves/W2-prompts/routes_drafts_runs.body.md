## Your role

Implement the 23 `drafts_runs` operations: the complete program-draft lifecycle and export, program catalogue/detail, run-batch lifecycle, client calculation/latest-run and unit base-year/rebase. Application features live in `dotnet\src\TaxCredit.Application\Features\DraftsRuns`, endpoints in `dotnet\src\TaxCredit.Api\Endpoints\DraftsRuns`, tests in `dotnet\tests\TaxCredit.Api.Tests\DraftsRuns`; `dotnet\src\TaxCredit.Worker` is also allocated here.

The brief predates W1b. A real Worker, shared executor, durable publication/recovery, fingerprint checks and real drain already exist. Build HTTP orchestration on that implementation and complete measured gaps; do not create a second worker/executor or replace the shared calculation transaction. `dotnet\src\TaxCredit.Application\Hosting`, shared ports, ServiceDefaults, persistence and certified Domain are dependencies, not writable implementation areas for this session. ReadsCalc owns unit reads; Claims owns claim routes and packages; AI and gateway remain separate groups.

## Preflight

Read `dotnet\docs\COMPOSITION-REPORT.md`, `dotnet\docs\HOST-ARCHITECTURE.md`, `dotnet\docs\COMPOSITION-SCHEMA-PROVISIONING.md`, `dotnet\docs\PERSISTENCE-REPORT.md`, `dotnet\docs\SOURCES-AUTH-AI-REPORT.md`, `dotnet\docs\DOMAIN-SLICE-REPORT.md` and `dotnet\docs\port-map.md`. Read the runs/drafts, base-year and CAP families in `dotnet\docs\findings.md`, then `contract\CONTRACT-REPORT.md` sections 4-5, `contract\FINDINGS.md`, `contract\COVERAGE.md`, auth/normalisation documentation and draft/batch recordings.

Inventory the 23 method/templates from `dotnet\docs\route-groups.json` and captured schemas. Trace ordinary `IFeatureModule`/`IEndpointGroup` discovery, mediator dispatch, request principal, rate limiter, error helpers and `DraftPaging.ListPage`. Inspect `TaxCredit.Worker\Program.cs` and `QueueWorker.cs`; `TaxCredit.Application\Hosting\RunWorkExecutor.cs`, `RunItemExecution.cs`, `RunIdentityScope.cs`; and `Ports\Persistence\RunPublication.cs` and `OperationalPorts.cs`.

The W1b Worker polls through the shared executor, supports finite `--once`, and uses the same durable queue/publication as contract drain. `RunItemExecution` already invokes `RunFingerprint.Current`/`OfManifest` and `UnchangedRule.Decide`. The snapshot's "partial fingerprint" label is not evidence that hashing must be ported again. Resolve any remaining Python `application\runs` behavior against current code before adding orchestration.

## Stage 1: establish the durable request-to-worker path

Implement the smallest real batch-start and batch-read vertical slice first. Separate dry-run selection/summary from accepted work: a dry run must not enqueue items. Build and persist normalized scope/program/year selection, actor and idempotency metadata through `IRunBatchRepository`. Selected-year order now survives reopen. Replay keys are scoped to the requester; compare the recorded same-key/same-body and same-key/different-body outcomes rather than inventing a blanket conflict.

Use `contract\recordings\p2_run_batches.jsonl` cases `dry-run`, `dry-run-all`, `dry-run-list`, `dry-run-filter`, `create`, `create-replay`, `create-same-key-different-body`, `get-queued`, `items-queued`, `drain`, `get-done` and `items-done`. Exercise actual drain and a finite Worker process using the persisted accepted batch. Reopen storage to prove that terminal queue state, manifest, Gold and assessed claims agree; the API must not hold its own in-memory list.

The shared path allocates a durable work/run identity, reconciles accepted manifests before recalculation and commits Gold, manifest, assessment claims and item finish/counters together. Consume `IClientCalculationRunner` and `IRunPublication`; direct `ClientCalculation.Run` from a handler would bypass the completed CAP-06 repair. Leave accepted unknown-commit reconciliation to that protocol rather than executing again on every exception.

Checkable result: one batch accepted through the ordinary API can complete through the existing Worker or drain and remains terminal after restart, with no second publication on replay.

## Stage 2: complete batch controls and client/base-year routes

Implement list/detail/items, authorization-aware totals/paging, cancel and failed-only retry. Unknown batch lookup precedes client visibility and stays not-found; do not expose counts before authorization. Cancellation must distinguish queued and leased/running items. Retry affects failed items, not already successful, cancelled or skipped work. Keep nested run-batch error objects intact with the existing error helper.

Cover `p2_run_batches:skip-unchanged`, `drain-2`, `items-skip-unchanged`, `create-calculate-all`, `cancel-queued`, `items-cancelled`, `retry-after-cancel`, `retry-nothing-failed`, `empty-list`, `items-status-bogus` and unknown-batch cases. Use `test_run_orchestration.py`, `test_run_item_errors.py`, `test_run_queue_cost.py`, `test_run_batches_end_to_end.py` and `test_run_batch_visibility.py` to fill behavior absent from successful HTTP recordings.

Complete `POST /api/v2/clients/{client_id}/runs`, `GET .../runs/latest`, `POST .../units/{unit_id}/base-year` and `GET .../units/{unit_id}/rebase`. Use the shared durable manifest destination and transactional runner. `p2_reads_writes:client2002.run-latest-after` records the old disconnected-manifest 404 (F-18); W1/W1b now prove that an accepted run is durable and visible, so demonstrate the repaired latest-run response as well as a genuinely never-calculated client. Do not manufacture the historical 404 after success.

Base-year overrides use existing persisted write order, including save/change/clear/later-save at one timestamp. Use `test_base_year_override.py`, `test_rebase_unit.py`, `test_run_client_calculation.py` and the recorded base-year flow. Keep the existing request/drain ordering for deferred recalculation observable to the next read. Historical equal-timestamp intent cannot be reconstructed by sorting old GUIDs.

Complete any missing orchestration around source observations and `skip_unchanged` without conflating the count/max-modified freshness observation with the certified content fingerprint. Unknown fingerprint inputs mean "cannot tell", not an unchanged run. Cover force, include-code-commit, changed program/year/assumptions, no payroll, classified source outage and cancellation using small focused cases.

Checkable result: every batch control and all four run/base-year operations have durable, authorized behavior; latest-run reflects accepted state, and unchanged decisions match the established evidence.

## Stage 3: implement the full draft lifecycle and program catalogue

Read `backend\application\program_drafts\lifecycle.py`, `validation.py`, `checklist.py`, `customer_data.py`, `preview.py`, `bundle.py`, `export.py`, `naming.py` and `views.py`. Implement their application behavior using certified `ProgramDraftRules`, canonical hashing, registry and pack validation with the real `IProgramDraftRepository`. Draft validation, invalidation of prior review, stale-version conflicts, actor separation, event history, withdrawal and immutable export metadata belong here.

Cover `contract\recordings\p1_program_drafts.jsonl` cases `create-duplicate-code`, `documents-stale-version`, `documents-wrong-code`, `validate-empty-scaffold`, `request-review-while-invalid`, `preview-synthetic`, `preview-client-refused`, `preview-bad-dataset`, `export-before-approval`, `review-self-approve`, `review-request-changes`, `documents-after-changes`, `withdraw-again`, `second-approve`, `second-export`, `second-export-write-local` and `second-manifest`.

Preview accepts the designated synthetic dataset, not arbitrary client payroll. Enforce application document-size/depth/year-count controls; the Domain constants alone do not enforce them. Catalogue/detail reads come from the same existing registry/rule files used for validation and computation. Test unknown program/draft, invalid status, stale version and genuinely huge draft-list offsets: W1b's count-first BigInteger paging intentionally returns an empty page with honest totals for an enormous nonnegative offset.

Prove exported bundle members and manifest per-file hashes from real approved content. Container encoding portability does not exempt member bytes or canonical content hashes. Use `test_program_drafts.py`, `test_program_draft_store.py`, `test_program_draft_customer_data.py`, `test_program_draft_preview.py`, `test_program_draft_export.py` and `test_program_catalog.py`. The recorded local-write refusal is a modeled lifecycle/export outcome, not permission to change authored rule files.

Checkable result: the recorded invalid-first-draft and approved-second-draft workflows complete through real repositories, with optimistic versions/events and an export whose members and manifest describe the saved content.

## Stage 4: verify Worker boundaries and full HTTP integration

Reuse the W1b executor for actual Worker, finite mode and drain evidence. Demonstrate independent-connection claim competition, at most one live lease per client, heartbeat/lost lease, expired reaping, backoff, cancellation/refunded attempts, assessment-only work and accepted-manifest recovery. Existing persistence tests already establish much of this; add focused tests only for behavior introduced or completed in this feature and its Worker changes.

There is a documented production limit: certified synchronous compute has no periodic heartbeat; default lease is 600 seconds with renewal before publication and a precommit ownership check. An expired lease rolls back. Verify this boundary with an injected clock/lease test and report long-run sizing as unmeasured, not as solved periodic renewal. A required shared executor change cannot be hidden in a second Worker-only implementation; identify its exact unowned seam and evidence.

Exercise ordinary feature discovery, then replay complete draft/batch scenarios and their setup dependencies with fresh absolute diagnostics. Reset/drain share a process-local gate; a separate Worker must not race the hermetic replay. The recorded P1 TY2025 drain population is 107/77/72, not the unrelated TY2023 public certification.

Write `dotnet\docs\ROUTES-DRAFTS-RUNS-REPORT.md` with the 23-operation map, draft/export case results, durable worker/recovery evidence, orchestration completed versus inherited, any missing shared seam and unmeasured native/long-run behavior. A later integrator needs exact callable contracts and remaining gaps, not another claim that all Worker behavior was first implemented here.

Checkable result: both executables use the one established queue/publication path, lifecycle routes reach real handlers, and failures are attributed to recorded cases and concrete components.

## Traps to expect

- `CONTRACT-REPORT` section 4's run-batch shape nests `detail` inside `detail`; draft errors instead use code/reason/remedy. Rate-limited draft save/preview/export and batch start return structured refusal plus `Retry-After`.
- F-14's `reader.run` and `reader.batch-dry-run` are retained valid-request exceptions in W1b. F-15 draft-list reads require no invented author. F-16 checks the acting header before agent-forbidden refusal.
- E-3/E-4 concern worker/thread ordering, not a requirement for an inline background poller. The real queue and drain already provide the controlled path.
- `findings.md` R-04 distinguishes unknown/empty fingerprint fields, requested-year order and optional code commit. D-02/D-04 require canonical UTF-8/hash semantics; an HTTP serializer is not a draft canonicalizer.
- D-05's document controls live in application lifecycle, not Domain. BY-03 preserves year-specific tranche opening rates; M-01 and first-program credit math remain inherited figure-sensitive boundaries.
- W1b selected years, override order and huge draft offsets are already repaired. Native write-sequence/work-identity/source-observation schema additions are documented but not live-provisioned or certified.
- The new framework readiness raw mismatch is outside this group's folders. Do not equate the wrapper's framework denominator with the conductor's exact-template denominator.

## Evidence this plan is based on

- `dotnet\docs\COMPOSITION-REPORT.md` and `dotnet\docs\HOST-ARCHITECTURE.md`: real shared Worker/executor, accepted-run recovery, finite process proof, lease limit and real drain/reset.
- `dotnet\docs\PERSISTENCE-REPORT.md` and `dotnet\docs\COMPOSITION-SCHEMA-PROVISIONING.md`: tenant/owner leases, atomic publication, selected-year and override-order durability, native provisioning limits.
- `dotnet\docs\DOMAIN-SLICE-REPORT.md`, `dotnet\docs\port-map.md` and `dotnet\docs\findings.md`: certified runs/draft/base-year helpers, fingerprint implementation and application lifecycle remainder.
- `dotnet\docs\SOURCES-AUTH-AI-REPORT.md`: trust precedence, limiter identity and source fingerprint limitations.
- `dotnet\docs\route-groups.json`: run/latest/base-year/rebase are DraftsRuns, not ReadsCalc.
- `contract\CONTRACT-REPORT.md`, `contract\FINDINGS.md`, `contract\COVERAGE.md` and named draft/P2 recordings: nested errors, F-14/F-15/F-16/F-18, export members and recorded lifecycle/control cases.
- `parity\export_runs.py` and `parity\export_drafts.py`: existing state-machine/hash evidence to consume rather than re-port.
