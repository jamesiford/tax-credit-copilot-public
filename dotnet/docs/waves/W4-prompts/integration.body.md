## Your role

Deliver an explicitly approved, read-only Python/.NET shadow comparison on the demo environment, performance measurements, consolidated deviations register, strangler cutover/rollback runbook and final report. You are an observer/test-harness author, not an unrestricted convergence engineer or deployment operator.

Implement in `dotnet\spikes\shadow\` and `dotnet\tests\TaxCredit.Shadow.Tests\`, with new dependencies only in the integration package section. Reports include `dotnet\docs\FINAL-REPORT.md` and `CUTOVER-RUNBOOK.md`. Product hosts, Python, contract comparers/recordings, schemas, infrastructure and earlier registers are inputs. Attribute product defects to their producers rather than hiding them in the observer.

The merged reports prove local functionality, not live certification. W3's API-board gateway column is not standalone gateway parity. The report may establish that cutover is not ready; synthetic evidence must remain distinguishable from live measurements.

## Preflight

Read `dotnet\docs\SPIKE-REPORT.md`, `DOMAIN-SLICE-REPORT.md`, `PLATFORM-RISKS.md`, `PERSISTENCE-REPORT.md`, `SOURCES-AUTH-AI-REPORT.md`, `COMPOSITION-REPORT.md`, `COMPOSITION-SCHEMA-PROVISIONING.md`, `HOST-ARCHITECTURE.md`, all four route-feature reports, `ROUTES-CONVERGENCE-REPORT.md`, `GATEWAY-REPORT.md`, `GATEWAY-CONVERGENCE-REPORT.md`, `HALT-integrate-W3.md` and `ORCHESTRATOR-REPORT.md`. Read their latest logs, `port-map.md`, `findings.md`, `pack-validation-deviations.md`, both ReadsCalc handoffs and the three orchestrator traceability indexes.

Read `contract\README.md`, `CONTRACT-REPORT.md` sections 4-6, `FINDINGS.md`, `docs\AUTH-CONTRACT.md`, `docs\normalisation.md`, `inventory\channel.json`, scenarios and `parity\README.md`. Inspect `dotnet\docs\route-groups.json`, `run_wave_replays.py`, `replay-gateway-policy.json`, all improvements registers and current policy.

Record a value-free provenance matrix: source/binary revisions, topology, runtimes, data classification, provider kinds, approval/capacity observations, grants available and unverified features. Run from `dotnet` for SDK 10.0.404; use the configured CPython 3.12 oracle. Keep `.env` contents out of evidence.

Verify `TCC_SHADOW_APPROVED` and active capacity using the conductor's read-only admission check before live requests, including cleanup. Historical platform approval is insufficient. Missing approval, capacity, safe credentials or endpoints means explicit unmeasured coverage, with an offline harness and reproducible invocation; do not activate capacity or provision services.

`deploy_ops` runs in parallel; its unmerged assets cannot be assumed present. Use verified existing endpoints or ordinary local hosts with isolated state and approved live reads. Record the measured topology; shadow approval does not authorize deployment.

## Stage I1: prove the observation boundary and data-safe diagnostics

Implement offline/self-test and explicitly admitted live modes. Keep targets/credentials runtime-only. Classify requests by their complete side-effect path, including audit, lazy initialization, recalculation and ticket consumption. Use a closed catalogue with row/page/byte/time/concurrency bounds, not arbitrary URLs or SQL.

GET/tool names are not read-only proofs. Exclude refresh/rebase, run/assessment, rule verification/application, package creation, mutating draft/export paths, prepare/commit, narration audit and ticket redemption from live shadow. Gateway reads can persist audit rows in `tcc_ops`: measure those only with isolated synthetic operational state or report them unmeasured live. Preserve mandatory audit and authorization.

Use read-only SQL credentials for approved source/Gold reads. The sole scratch exception is `tcc_scratch_dotnet`; no writes to `tcc_gold`, `tcc_ops`, lakehouse tables or Blob. Inspect actual transport/startup behavior rather than inferring safety from a test name.

Read `dotnet\spikes\platform\Runner\ScratchGuard.cs`, `DemoEnvironment.cs` and `Cleanup.cs`. Reuse the guard where practical with shadow-owned admission/output. The old runner requires a different approval and deletes all scratch objects: do not invoke it as this session's cleanup. Track pre-existing/shared ownership and remove only objects created by this invocation. Scratch may remain unused.

Before SQL connections, exercise the 20 forbidden/11 allowed guard cases, including ScriptDom's separate `BulkOpenRowset` node, plus cleanup-ownership tests. Use closed SQL templates/parameterized tenant filters. Prove targeted cleanup in `finally` and recovery, retaining value-free object counts.

`contract\compare.py` returns rendered `expected`/`actual`; raw replay writers persist them. Keep live comparisons in memory. Emit only route templates, synthetic sample labels, safe field-path templates, categories, equality verdicts, aggregate counts and timings. Sanitize dynamic keys, filenames, URLs and exceptions too. No raw live bodies, prompts, SQL values, headers, IDs, tokens, stack traces or downloaded bytes may reach files/logs.

Reuse comparator/normalisation functions in memory; a shadow-owned subprocess bridge must not emit values or use value-bearing temporary files. Compare whole-response/content digests, reporting equality rather than low-entropy scalar hashes.

Result: negative tests refuse forbidden mutations before dispatch and prove sentinel private-looking data cannot escape through diagnostics, reports, traces or temporary files. Comparator mutations must still detect changed money/type/status, missing/null fields, event order and member content.

## Stage I2: establish the current hermetic baseline without confusing scorers

Use ordinary API and standalone gateway hosts against synthetic seeds. `dotnet\docs\run_wave_replays.py` runs nine API and three `g1_` gateway scenarios. Gateway services compose in-process, with no second API listener. Reset/mint/env/drain belong only to isolated hosts, never demo endpoints.

Use public replay setup selecting each scenario's profile/auth/writer/rate overlay. Earlier P2-to-P1 and anonymous-mode setup defects are repaired in `contract\README.md`. Do not erase setup with another unqualified reset or run independent Workers during process-local reset.

Produce fresh reports at absolute paths with existence checks. Runner success can mean completion with differences. Separate raw synthetic statistics, policy-adjusted statistics and improvements matches.

Evaluate historical count/error disputes and the framework-cap halt against injected current policy: framework's small group is now exempt, and recorded list metadata is intended. This does not resolve genuine status/value failures. Keep the F-18 dry-run counter exception scoped to its exact recorded paths.

Use exact method/template ownership from `route-groups.json`; `g1_` is gateway regardless of API placeholders. Track `_unassigned`, sealed workspace and controls separately. W3 has 1,514 API exchanges versus 255 standalone gateway exchanges; reconcile control/HTTP denominators and wrapper membership rather than averaging percentages.

W3 convergence supersedes the gateway delivery diagnostic of 233/255: standalone final is 236/255 (92.55%), with 19 failed cases/49 fields. Residuals are two MCP person-lane cases/16 fields (`call.client_at_risk.typical`, `call.findings_list.typical`), two eight-versus-eleven dataset catalogue cases/17 fields, and fifteen genuine allocation-drift cases/16 fields. Missing datasets are `payroll`, `location`, `pay_code`. These are not missing-fact waivers.

Result: a per-group table with revision, host, denominators, raw failures, global tolerances, register-dependent cases, unresolved failures and evidence origin, preserving the separate gateway measurement.

## Stage I3: pair approved live reads and compare without exporting values

Pair eligible requests on caller rights, source, program/year/method, pagination/filters and observation window. Actual identifiers stay in memory; reports use sample ordinals/template routes.

Use only authentication needed for approved reads, not live Foundry/Graph diagnostics, publishing, Blob writes, new grants or broad Entra tests. Unproved ingress identity/employer binding excludes private reads; orchestrator header mapping is not authentication.

Observe source fingerprints before/after paired samples, emitting only kind, changed/unchanged verdict and timing. Count/max markers are not Delta IDs, freshness guarantees or snapshots. Interleave/repeat reads to identify drift; changed or unprovable observations are inconclusive. Equal markers cannot exclude count/max-preserving edits.

Compare byte/content hashes and semantic results separately. Reuse `contract.compare.compare_record`, semantic `split` mode and existing normalisations. Preserve decimal-string scale, null/presence, status/code, array order, schemas/descriptions and certified values. Hash mismatch plus semantic equality is an encoding difference, not a changed figure.

For isolated ZIP/XLSX tests compare ordered members, sizes/content hashes and header/body integrity. Container exceptions exclude trails, canonical hashes and per-file manifests. Audit-writing or ticket-consuming live downloads remain excluded.

Per group report planned/eligible/attempted/paired/completed/inconclusive counts, hash/semantic matches, failure categories and unmeasured reasons. Retain failures/dependency outages in denominators. Full synthetic write coverage remains separate from the necessarily narrower read-only live sample.

Compare canonical facts across API and REST/MCP where safe, using isolated operations for audit-writing surfaces. Test orchestrator composition with scripted transports/records, not live models or confirmations. Its 39 records and 313 indexed E/P/U/X guarantees are not full cross-surface certification.

Result: payload-free live evidence, exclusions/drift explained, no protected-schema side effects and cleanup proof or explicit scratch-unused status.

## Stage I4: measure performance against defensible baselines

There is no recorded live Python route/write baseline. `PLATFORM-RISKS.md` measured .NET open plus `SELECT 1` at 3.983 seconds, not throughput, retry/pooling or native type parity. The historical task's write anecdote is not a verified baseline.

Carry the actual Python microbenchmarks from `SPIKE-REPORT.md` into the performance table, correctly labelled pure-engine, single-thread, minimum-of-five:

| Synthetic rows / method | Historical Python | Historical .NET Release |
|---|---:|---:|
| 9,477 / Pay Period | 97.5 ms | 43.7 ms |
| 9,477 / Min-Max | 42.8 ms | 30.6 ms |
| 189,540 / Pay Period | 1,756 ms | 400 ms |
| 189,540 / Min-Max | 865 ms | 279 ms |

These are not HTTP/live Fabric speedups. Keep new paired observations separate. Reuse `parity\bench_python.py` and existing engine entry points; do not benchmark production writes.

Measure bounded cold/warm reads with sample count, order, concurrency, dataset-size class, build/runtime, timing boundary and timeout/failure count. Report medians and supported tail percentiles, warm-up policy and source/network conditions. Separate token/connect/query/end-to-end time where measurable; otherwise label combined. Keep payloads/rows out of traces.

Use shared-capacity-safe load, not saturation. Preserve failed observations and do not resubmit uncertain requests. No production SLO/regression threshold is established: report deltas with acceptance awaiting owner agreement.

Result: a traceable performance table separating historical/new data, units/scope and explicitly unmeasured cells.

## Stage I5: consolidate deviations and operational open decisions

Write `dotnet\docs\SHADOW-DEVIATIONS.json` and a human-readable register linked from `FINAL-REPORT.md`. Inventory all waves, including empty registers, duplicate `W1-skeleton.json`/`skeleton.json` and convergence entries. Deduplicate without losing source IDs/files; distinguish historical/withdrawn entries, current deliberate differences, unresolved defects and policy tolerances.

For each difference capture wave/register/ID, exact route/case/path, reason, evidence, effect class, reproduction/disposition and owner-review status, including differences outside the latest sample. Register matches are documentation, not cutover approval. Flag broad/stale entries without rewriting sources.

Keep inherited figure/authorization boundaries explicit: M-01 year-pack ingestion overrides; first-program pricing in multi-program states; zero-worksite SQL/projector differences; strict contextual leap shifts; native monetary AVG/decimal scale; CAP-10 QC-drop behavior; legacy fiscal/tax-year selection; historic equal-time override order; F-14 valid-request writer exceptions; gateway person-lane refusals; dataset availability and genuine ID allocation differences. Reconcile earlier page-independent-count demands with the current recorded-semantics policy instead of reopening an obsolete policy contradiction.

Include operational decisions not representable as replay waivers: native schema/grants still unproved; supplemental `finding_audit`, write sequence and work/source-observation tables; save-override versus queue-acceptance atomicity; 600-second synchronous-compute lease without periodic renewal; count/max freshness limits; real exporter delivery; trusted orchestrator ingress/employer binding; host-local gateway idempotency-key exclusion; in-memory orchestrator checkpoints/budgets; missing production result-recovery endpoint. An uncertain mutation is not repaired by retrying it in shadow.

Result: a complete, source-linked deviations/decisions register with no numerical or missing-fact concealment, and an exact list of application/deployment work outside this session's ownership.

## Stage I6: write the cutover/rollback runbook and final evidence report

Write `dotnet\docs\CUTOVER-RUNBOOK.md` as an operator procedure, not an executed traffic switch. Include a route-method ownership table, both upstreams as runtime inputs, the proxy/BFF trust boundary, health/readiness observations, change approvals, evidence freshness/window, unresolved blockers and who must approve each slice.

Sequence read-only slices before writes, then complete dependent lifecycles rather than individual convenience endpoints. Define coupling explicitly: API writes and recalculation must share the accepted Gold/manifest destination; package creation/metadata/download remain coherent; batches, Worker and overrides have one active writer authority; gateway tools depend on canonical application producers; orchestrator conversation/confirmation state cannot be split arbitrarily. Keep all eleven sealed workspace operations on their documented unavailable path; the private reference extract remains uncertified.

Document proxy method/path routing, auth/audience/acting-person preservation, error/SSE handling, MCP session affinity and no buffering of event streams. Mirror only proved side-effect-free requests. Do not mirror commits, mutating GETs, audit-writing calls, ticket redemption or queue work to both stacks. Specify how to stop Python and .NET Workers from simultaneously consuming work during transition and how pending confirmations/idempotency identities are reconciled.

For each slice state readiness evidence, owner-approved success/observation criteria, explicit non-ready conditions, routing change, immediate smoke observations and rollback decision/authority. Provide a reversible configuration example under `dotnet\spikes\shadow\` if useful; it must default to no traffic change and require supplied upstreams. Its tests use local synthetic upstreams.

Rollback changes routing and writer ownership, not accepted data or schema history. Preserve compatible forward schema additions, successful manifests, immutable artifacts and audit. Address in-flight work, accepted-but-unacknowledged writes, leases, expiring/single-use tickets, outstanding confirmations, process restart and cross-replica limitations. Do not invent a recovery endpoint or promise that redeploying an image undoes a mutation. Keep the Python deployment independently runnable.

`FINAL-REPORT.md` should begin with the actual cutover-readiness verdict and distinguish delivered tooling, synthetic evidence, live evidence and unverified obligations. Link per-group statistics, paired performance, deviations, redaction/guard mutation tests, scratch cleanup proof and the runbook. Reconcile historical test-count arithmetic and explicitly identify which heavy suites and dual-host replay results exist at this revision; earlier fast-suite passes are not evidence that final heavy/native suites ran.

Result: a complete reproducible evidence package and operator runbook, including unresolved decisions and unavailable live coverage without success-shaped substitutes.

## Traps to expect

- Historical W2 ownership halts and policy contradictions are not necessarily current blockers. Check convergence and current policy; a report/table labelled PASS can still be a differently scoped projection.
- API registry placeholders can make the API-board gateway column look perfect. Only the standalone gateway's `g1_` replay measures that surface.
- Raw comparison paths and `expected`/`actual` values can leak private content even when ordinary application logs are redacted. Treat failure diagnostics as a data boundary.
- A read-only-looking capability may write audit, a package link may mint a ticket and a download may consume it. Inspect the complete path before live dispatch.
- DECIMAL(19,4) storage metadata is distinct from typed payload equality; `"3500.0"` and `"3500.0000"` are different strings. A numerical equality helper must not erase the difference.
- SQL fingerprints are not snapshots. A stable marker, matching response hash or fast response is not certification of source freshness.
- Current orchestration checkpoints survive fresh graph construction within one process, not restart. Local confirmation race tests do not establish fleet-wide exactly-once behavior.

## Evidence this plan is based on

- `dotnet\docs\SPIKE-REPORT.md`, `parity-report.md` and `DOMAIN-SLICE-REPORT.md`: pure-engine certification, historical microbenchmarks, capstone scope and no private-reference proof.
- `dotnet\docs\PLATFORM-RISKS.md` and `platform-risks-log.md`: only token connectivity and zero-object cleanup measured; repaired `BulkOpenRowset` safety case; no Python throughput baseline.
- `dotnet\docs\PERSISTENCE-REPORT.md`, `SOURCES-AUTH-AI-REPORT.md`, `COMPOSITION-REPORT.md` and `COMPOSITION-SCHEMA-PROVISIONING.md`: native proof limits, exact decimal binding, strict leap seam, schema additions and synchronous lease boundary.
- `dotnet\docs\ROUTES-READS-REPORT.md`, `ROUTES-CLAIMS-REPORT.md`, `ROUTES-DRAFTS-RUNS-REPORT.md`, `ROUTES-AI-REPORT.md` and `ROUTES-CONVERGENCE-REPORT.md`: historical isolated-route failures, subsequent composition/scoring repairs and residual storage/value/status cases.
- `dotnet\docs\GATEWAY-REPORT.md`, `GATEWAY-CONVERGENCE-REPORT.md`, `HALT-integrate-W3.md`, `replay-gateway-policy.json` and `HOST-ARCHITECTURE.md`: separate-host topology, incomparable board scopes, person-lane/dataset/ID differences and native access not certified.
- `dotnet\docs\ORCHESTRATOR-REPORT.md`, `orchestrator-spec-traceability.md`, `orchestrator-composition-traceability.md` and `orchestrator-workflow-traceability.md`: 39 deterministic records versus 313 indexed guarantees, incomplete cross-surface matrices, ingress trust and in-memory unknown-write recovery limits.
- `contract\CONTRACT-REPORT.md`, `contract\FINDINGS.md`, `contract\docs\normalisation.md`, `dotnet\docs\findings.md` and all `dotnet\docs\improvements\` registers: field-level traps, narrow container exceptions, intended deviations and figure-sensitive owner questions.
