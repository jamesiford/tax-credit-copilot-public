# Program drafts, programs, run batches, runs and the worker

Session `routes_drafts_runs` of wave `W2`. You run unattended: nobody will answer questions, so do not ask any.
Worktree: `C:\Projects\GitHub\tcc-dotnet-w2-drafts` (branch `dotnet/w2-routes_drafts_runs`, created from `dotnet/integration`).

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
- `replay`: the contract replay (semantic mode) meets the thresholds for your route groups; failures covered by your improvements register entries are shown separately and are capped
- report required: `dotnet/docs/ROUTES-DRAFTS-RUNS-REPORT.md`
- replay thresholds: drafts_runs >= 98%

If a gate fails you will be resumed with its output and asked to fix it. Run the same checks yourself before you finish.

---

## Rules (fixed by the conductor; they cannot be changed by the task)

- **Work only in `C:\Projects\GitHub\tcc-dotnet-w2-drafts`** (branch `dotnet/w2-routes_drafts_runs`). Do not edit the main checkout or any other worktree.
- **Never push, never open a pull request, never change a remote.** Pushing is also blocked mechanically; do not try to work around it. Commit locally in small, sensible commits with the trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- **You may create or modify only:** `dotnet/src/TaxCredit.Application/Features/DraftsRuns/**`, `dotnet/src/TaxCredit.Api/Endpoints/DraftsRuns/**`, `dotnet/src/TaxCredit.Worker/**`, `dotnet/tests/TaxCredit.Api.Tests/DraftsRuns/**`, `dotnet/docs/**`. The last entry, `dotnet/docs/**`, is always yours for reports, logs, status files and the improvements register; it never needs an exception. Any other change fails a gate. Never edit existing product files (`backend/`, `frontend/`, `infra/`, `scripts/`, `channel_orchestrator/`, `docs/`, `.github/`) unless they are inside your owned paths.
- **The reference is the Python product on CPython 3.12** (`C:\Projects\py312-oracle\.venv\Scripts\python.exe`): it shows what the system is meant to do, but it is not a specification to copy defect for defect. Build the designed functionality and the contract clients depend on; do not reproduce defects or framework accidents. Never change the Python code. Record each deliberate difference in `dotnet/docs/improvements/routes_drafts_runs.json` as the policy describes, and record Python oddities in `STATUS.json` under `findings`. A changed calculated figure is never an improvement. Never loosen a comparison, delete a test or weaken a threshold to make something pass.
- **Nobody can answer questions.** Use the policy decisions above. When a decision is missing, take the reading closest to the documented design and the Python behaviour, record it under `needs_human` in `STATUS.json`, and keep going.
- **Customer-neutral:** no customer names, tenant or server names, identifiers, tokens or secrets in any file, log or report. Synthetic data only.
- **Tests:** tag long-running tests `[Trait("Category", "heavy")]`; the fast gate excludes them. Keep the fast gate quick.
- **Shared files:** put package versions only inside your marked section of `Directory.Packages.props` if your session has one; never add a package another section already declares. Register your services and endpoints from your own project (an `AddXxx` extension or endpoint-group class); do not edit another session's files.
- **Keep a running log** of decisions, findings and gate results in `dotnet/docs/routes_drafts_runs-log.md`.
- **Budget:** you have a limited time and credit budget. Finish each stage with its checks green before polishing, and finish the whole task rather than perfecting one part.

---

## Hard stops (fixed by the conductor)

Write `dotnet/docs/HALT-routes_drafts_runs.md` (what happened, what you tried, what a human must decide), commit it, and end the run if any of these happens:

1. A push, a remote change, a change outside your owned paths, or a destructive command outside your worktree would be needed.
2. A secret, token, tenant or server name, customer identifier or private data would be written to a file.
3. Equivalent behaviour for the designed functionality cannot be reached after three honest attempts on the same item (this is a valid, important result: report it, do not hide it).
4. The Python oracle environment is not CPython 3.12, or imports the wrong checkout, and configuration cannot fix it.

---

## Finish (fixed by the conductor)

When the task is done, or you are stopping at a hard stop, write `dotnet/docs/status/routes_drafts_runs.json` in your worktree and commit it. It is machine-read; it must be valid JSON with this shape:

```json
{
  "session": "routes_drafts_runs",
  "branch": "dotnet/w2-routes_drafts_runs",
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
