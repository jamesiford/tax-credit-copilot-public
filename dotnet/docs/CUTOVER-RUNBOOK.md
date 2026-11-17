# NOT READY FOR CUTOVER

This is an operator procedure, **not an executed traffic change**. Keep the existing/Python routing and writer authority. Approval for this session permits bounded observation, not deployment, migrations, grants, production writes, model calls or traffic switching. No assets from the parallel deployment session are assumed present.

The [final report](FINAL-REPORT.md), [fresh replay board](integration-replay.json), [complete deviations](SHADOW-DEVIATIONS.md) and [live admission record](integration-live.json) are mandatory inputs to the change review. Current live access, native schema/type behavior, identity/employer binding and acceptance thresholds remain unproved. Passing a percentage is not acceptance of the remaining cases.

## 1. Assemble and approve the change

1. Name a change commander and explicit API/ReadsCalc, claims/artifact, drafts/queue, gateway, orchestrator, identity, database and statutory approvers. Record which exact method/templates and complete lifecycles they approve. Review every applicable `DEC-*` and fresh unresolved case in `SHADOW-DEVIATIONS.json`; a register match is documentation, not approval.
2. Supply upstreams at runtime: `PYTHON_API_UPSTREAM`, `DOTNET_API_UPSTREAM`, `PYTHON_GATEWAY_UPSTREAM`, `DOTNET_GATEWAY_UPSTREAM`, `PYTHON_RESPONSES_UPSTREAM`, `DOTNET_RESPONSES_UPSTREAM`. Keep addresses, audiences, identities, employer/account selection and credentials out of configuration committed to this repository. Do not substitute an API listener for the standalone gateway's in-process application composition.
3. Keep the Python deployment independently runnable, with its approved configuration, compatible package/artifact access and current forward schema. Verify rollback access before changing routing. Never assume redeploying an image restores accepted data.
4. Agree the evidence window, sample workload, data/source/Git revisions, observation duration, error/latency acceptance thresholds and rollback triggers **before** the slice. None is established by this task; blank criteria mean hold. Repeat admission and all affected evidence after code, rules, source mapping, grants, ingress, host count or routing changes. Old count/max equality is not a freshness certificate.
5. Database operators independently apply/review the existing Python forward migrations and grants. Prove the supplemental `finding_audit`, write sequence and work/source-observation contracts, native DECIMAL/AVG/datetime behavior, retry behavior and effective permissions. No EF migrations, schema bootstrap on an existing Warehouse, new broad grants or destructive cleanup. A read-only observer must prove no protected write rights, including table-level rights; `ApplicationIntent=ReadOnly` is insufficient.
6. Obtain the current shadow approval and conductor capacity admission. A missing/paused/unproved capacity or missing safe credential/endpoint produces **unmeasured**, not a synthetic substitute. Do not activate capacity to make a check pass. Confirm that existing live host startup cannot lazily register agents, warm an engine or initialize protected storage outside the approval.

## 2. Establish the trust and proxy boundary

The BFF/proxy is a trust boundary, not a header relay. Validate the original caller and each upstream's expected audience. Do not rewrite JWT claims or turn the gateway's own service principal into the acting person. Use the reviewed delegated/on-behalf-of mechanism where different audiences require it; only preserve an acting-person identity that authenticated ingress established. Strip/replace all client-supplied platform and acting-user headers; isolate direct origins so they cannot bypass this check. Prove employer binding separately from tenant sign-in and from an operator's `reviewed` attestation.

Route by **method and exact template** in the table below, not an overlapping prefix or a path without its verb. Preserve query parameters, pagination, status meaning, JSON field types, money strings/scale, null/presence and canonical hashes. Keep API `detail` and channel protocol error families intact. Do not rewrite producer failures into a proxy 200, HTML or a generic envelope. Preserve relevant `Location`, content/hash and authentication headers without exposing backend storage addresses.

For chat/Responses and MCP event streams, retain event order, content type, cancellation and backpressure; disable response buffering, caching and transformations that hold/coalesce events. Set stream-aware timeouts by owner agreement, not the small shadow read timeout. A transport reconnect is not permission to replay a write. Route an MCP session's POST/GET/DELETE and outstanding state to the same authority; preserve affinity until a reviewed expiry/drain. Process-local affinity does not supply restart or fleet durability.

Mirror only a separately reviewed, bounded, side-effect-free catalogue. This harness admits only public health, bounded stored eligibility and draft listing (the latter still needs writer entitlement), and only after all live prerequisites. **Never mirror** audited gateway tool calls, narration, refresh/rebase GETs, assessment/run/rule-application/verification, draft/export mutations, package creation, ticket mint/redemption, artifact-access audit, prepare/commit, confirmations or queue work. Do not suppress mandatory authorization or audit to make a mirror look read-only. Other apparently safe reads require a new full-path review, not inference from GET.

## 3. Advance complete slices, in this order

All rows below are currently **hold**. Success means the named owners have accepted fresh, appropriately scoped evidence and explicit observation/rollback criteria; it never means every raw difference has disappeared.

| Slice / approvers | Evidence and explicit non-ready conditions | Routing change after approval | Immediate smoke / rollback authority |
|---|---|---|---|
| Framework / API + identity + change commander | Real ingress, audience, dependency readiness and safe health response observed; current capacity admitted. `/api/health`, `/api/ready` and channel health are observations, not proof of data, grants or binding. Hold on any missing prerequisite. | First exact, approved health/document methods only. Small-group framework cap exemption does not approve data routes or framework emulation. | Observe each upstream through the BFF, expected status/error/auth behavior and real dependency readiness. Commander returns these exact methods to prior upstream on an agreed trigger. |
| Stored reads / ReadsCalc + source + identity + statutory | Same caller rights, source/program/year/method, page/filter and window; repeated/interleaved safe pairs, source markers, exact values/types and failure denominators. Hold on drift/unavailable markers, unresolved accepted-value/status differences, unproved native types or missing binding. | Move only accepted read templates; keep calculation/writes on their prior authority. Shared accepted Gold/manifest destination and read compatibility must already be proved. | Read the same approved sample via proxy; inspect payload-free status/equality/count/timing evidence, not private logs. ReadsCalc owner and commander roll the read slice back on incorrect or unavailable results. |
| Claims, findings and package lifecycle / claims + artifacts + database + statutory | Producer residuals, valid-request authorization, stored values, artifact/member/header integrity and durable audit reconciled; schema/grants and accepted destination proved. Hold on scale, identifiers, long-valid-text 500s or any uncertain write. | Move coherent claim/assessment/finding writes and their reads. Keep package creation, metadata and download for each generation on one authority; do not redirect old tickets to a new issuer. | With a separately approved synthetic subject, observe one full authorized lifecycle and immutable result/audit. No shadow dual writes. Commander and owning writer freeze intake and invoke section 5 if acknowledgement is uncertain. |
| Draft/export and recalculation / drafts + queue + persistence + change commander | Full draft version/review/export lifecycle; override/queue partial acceptance reconciled; long native lease behavior and durable run/Gold/manifest publication proved. Exact F-18 counters only; no figure waiver. Hold if either Worker can still consume or lease/queue intent is unresolved. | Move the complete draft/export version lifecycle. Move override/rebase, run-batches, run requests/status and Worker authority as one coordinated lifecycle under section 4. | Observe accepted work, one active consumer authority, terminal durable state and matching Gold/manifest generation using approved synthetic work. Queue owner and commander stop intake/consumer before rollback. |
| Gateway REST/MCP / gateway + canonical producer owners + privacy + identity | All dependent producer contracts accepted; person lanes, all eleven datasets, real identity allocation and audit/ticket behavior reconciled. Durable/fleet idempotency policy agreed; actual standalone transport evidence fresh. Hold on any of the documented 19 residual cases or unproved ingress. | Switch coherent REST/MCP sessions and their tool/prepare/commit/audit/ticket lifecycles, not individual convenience tools across authorities. Gateway remains an independent host with in-process application services. | Observe delegated identity, status/facts, audit and session continuity; no live confirmation mirror. Gateway owner and commander freeze new sessions, retain the old authority for outstanding sessions/tickets, then roll back new traffic. |
| Chat/Responses / orchestrator + gateway + identity + operations | Scripted composition plus independently approved real ingress/exporter evidence; conversation/confirmation retention, restart/replica affinity and uncertain-write recovery protocol agreed. Hold: checkpoint/budget memory is not durable and production `resultLookup` does not exist. | Move new conversations only after canonical gateway dependencies are ready. Keep a conversation, budget, confirmations and recovery identity on one authority; never split by individual turn. | Observe stream ordering/cancellation and a scripted synthetic read conversation without a model/real confirmation in shadow. Orchestrator owner/commander freeze new conversations; reconcile outstanding state before changing affinity. |
| Sealed workspace / reference-data + statutory owners | **All eleven operations remain unavailable** without the private extract. Synthetic 81/51/49 is not private 10,236/539/656 certification. | No cutover of these operations; preserve the documented unavailable contract. | Verify unavailable behavior only. Reference owners alone can approve a separately reconciled certification plan. |

## 4. Transfer writer/Worker authority without double consumption

1. Stop admission of new affected mutations and queue submissions at the existing authenticated ingress; do not discard accepted requests. Inventory pending batches, saved overrides, work identity, leases, accepted manifests, package generations, idempotency keys and outstanding confirmations in their authorized operational destination. Keep the shadow report value-free.
2. Through the existing per-service supervisor controls, disable restart/scale-out of the retiring Worker authority, stop **all its replicas**, and wait for confirmation. Never kill processes by a shared name or start an independent Worker during contract reset. Inspect in-flight leases: allow a verified completion/drain or reconcile expiry/rollback with the queue owner. The 600-second synchronous lease has no periodic compute heartbeat; elapsed time alone is not safe re-execution proof.
3. Verify both stacks point to the **same accepted Gold, run-manifest, work/claim and artifact destinations**, with compatible schema, identities and rule/fiscal conventions. Do not combine .NET success with a Python read from another store or run an independent queue for the same accepted work. Saved override intent may exist even when enqueue failed; an unchanged resave is not a repair.
4. Enable exactly one replacement writer/Worker authority only after the old one is proved stopped and in-flight intent is reconciled. Switch the coupled request/status/read routes in the approved configuration revision. Prove no other replica/supervisor can resume consumption. A disabled HTTP route alone does not stop a Worker.
5. Resume bounded approved intake and observe durable success/failure, manifest/Gold coherence, leases and audit against the pre-agreed window. Verify actual safe exporter receipt; instrumentation registration is not delivery proof. Preserve unsuccessful observations and stop on unknown acknowledgement; never submit a “comparison” mutation to the other stack.

## 5. Roll back routing and authority, not history

The change commander owns the routing decision; the queue/persistence owner owns writer restart and lease reconciliation; the artifact/gateway/orchestrator owners own their outstanding state. On a correctness, trust, dependency or agreed performance trigger:

1. Freeze new affected writes/sessions before changing an upstream. Stop the new Worker authority and its restart policy as above, then identify all accepted and in-flight work. Do not run both Workers to “drain faster.”
2. An accepted-but-unacknowledged mutation is **unknown**, not failed. Retain its original identity/correlation/idempotency and inspect authorized durable run/claim/audit/artifact records under the owning team's procedure. Do not invent a result-recovery endpoint, retry with a new key, submit it to Python, or interpret a missing in-memory checkpoint as proof nothing happened. The production bridge currently has no `resultLookup`.
3. Reconcile pending confirmations and idempotency reservations before changing issuer/authority. Same-confirmation atomic consume does not give cross-replica exclusion for different confirmations sharing a key. Keep single-use/expiring tickets and downloads with the issuing generation until consumed or expired; preserve access audit. Treat process restart, replica changes and expired in-memory budgets/checkpoints as explicit state-loss risks, not transparent failover.
4. Restore the last approved **method/template routing revision**, preserving error/stream/session semantics. Keep old sessions/generations on their authority where required; freeze those that cannot safely continue. Restart Python's one Worker authority only after the replacement is stopped and the queue owner has reconciled leases/accepted work.
5. Keep successful manifests, immutable artifacts, claims, override intent, audit and compatible forward schema additions. Do not delete accepted rows, restore an older database image, reverse migration history or run schema-wide scratch cleanup. Binary rollback cannot undo a mutation. If the prior binary cannot safely read the forward schema, keep intake frozen for an owner-approved compatibility repair.
6. Observe the restored path over the agreed window and close only after writer exclusivity, durable outcome reconciliation, dependency/auth behavior and retained evidence are accepted. Document remaining unknowns, not success-shaped defaults.

## 6. Reproduce the evidence safely

Run from `dotnet` with SDK 10.0.404 and the configured CPython 3.12 oracle. Build Release first. `spikes\shadow\run_tests.py` emits only test counts; `TaxCredit.Shadow --self-test` exercises all 31 inherited SQL fixtures and three closed templates. `hermetic.py --baseline`, `paired_performance.py` and `cross_surface.py` launch only ordinary loopback hosts with distinct synthetic stores and terminate their own processes. Their fixed artifact directories must be fresh; retain existing evidence rather than silently overwrite it. Public reset/env/mint overlays are **isolated-host controls only**, never instructions for a demo endpoint.

`observe.py --live` accepts no endpoint/credential command-line arguments. Supply runtime-only `SHADOW_CAPACITY_CHECK`, the `SHADOW_*` inputs documented in [the harness README](../spikes/shadow/README.md), current approval and reviewed ingress/binding/right/destination prerequisites. The read-only permission proof precedes fingerprints/HTTP. A missing prerequisite records unmeasured coverage, without contacting data endpoints. No model, Blob write, migration/grant, protected-schema mutation or live ticket/audited tool is part of this invocation.

## 7. Exact method/template ownership

The generated table below is exhaustive for the 110 operations in `route-groups.json`. It is a **retention plan**, not enabled proxy configuration. API gateway placeholders are not standalone gateway evidence. `POST /responses` is documented separately because it belongs to the independently hosted orchestrator, not this captured API inventory; no additional SDK management routes are approved by implication. Worker authority is not an HTTP route.

<!-- W4-ROUTE-TABLE -->

| Method and exact template | Producer | Coupled lifecycle / retained authority |
|---|---|---|
| `GET /openapi.json` | framework | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `HEAD /openapi.json` | framework | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /docs` | framework | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `HEAD /docs` | framework | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /docs/oauth2-redirect` | framework | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `HEAD /docs/oauth2-redirect` | framework | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /redoc` | framework | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `HEAD /redoc` | framework | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/ready` | framework | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/health` | framework | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/me` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/eligibility/{tax_year}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/progress/{tax_year}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/forecast/{tax_year}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/alerts/monthly/{tax_year}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/triggers` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/performance/{tax_year}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/onezero/matrix/{tax_year}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/onezero/{tax_year}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/onezero/{tax_year}/employee/{employee_id}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `POST /api/onezero/employee/{employee_id}/review` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/designations/{state}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/reconcile/{tax_year}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/qc/{tax_year}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/onezero/retroactive/scan` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/simulate/portfolio/{tax_year}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `POST /api/simulate/unit` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `POST /api/simulate/employee` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `POST /api/simulate/onezero` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/ingestion/{tax_year}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `POST /api/ingestion/{tax_year}/exceptions/{exception_id}/resolve` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/ingestion/{tax_year}/rows` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/proximity/{tax_year}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/scope` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/scope/client/{account_id}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/v2/clients/{client_id}/units` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/v2/clients/{client_id}/units/{unit_id}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `GET /api/v2/employees/{record_token}` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `POST /api/employee/drill` | reads_calc | accepted stored read/source/statute; writes remain coupled; **retain existing** |
| `POST /api/clients/{client_id}/packages` | claims_artifacts_rules | package-generation/metadata/download/audit lifecycle; **retain existing** |
| `GET /api/clients/{client_id}/artifacts/{artifact_id}` | claims_artifacts_rules | package-generation/metadata/download/audit lifecycle; **retain existing** |
| `GET /api/audit/channel` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `GET /api/claims/coverage/{client_id}` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `GET /api/claims/coverage` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `GET /api/claims/cell/{client_id}/{program_code}/{tax_year}` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `POST /api/claims` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `POST /api/claims/cell/{client_id}/{program_code}/{tax_year}/transition` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `PUT /api/claims/engagement` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `POST /api/claims/assess` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `GET /api/claims/lifecycle` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `GET /api/v2/portfolio` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `GET /api/v2/clients/{client_id}/situation` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `GET /api/rules` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `POST /api/rules/{code}/verify` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `GET /api/rules/ingested/{state}` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `GET /api/rules/ingested/{state}/refresh` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `GET /api/rules/ingested/{state}/proposals` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `POST /api/rules/ingested/{state}/apply` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `GET /api/rules/ingested/{state}/changelog` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `GET /api/findings/{client_id}/{tax_year}` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `POST /api/findings/{finding_id}/resolve` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `POST /api/findings/{finding_id}/reopen` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `GET /api/findings/{client_id}/{finding_id}/history` | claims_artifacts_rules | claims/rules/findings plus accepted run destination; **retain existing** |
| `GET /api/v2/program-drafts` | drafts_runs | draft-version/review/export lifecycle; **retain existing** |
| `POST /api/v2/program-drafts` | drafts_runs | draft-version/review/export lifecycle; **retain existing** |
| `GET /api/v2/program-drafts/{draft_id}` | drafts_runs | draft-version/review/export lifecycle; **retain existing** |
| `PUT /api/v2/program-drafts/{draft_id}/documents` | drafts_runs | draft-version/review/export lifecycle; **retain existing** |
| `POST /api/v2/program-drafts/{draft_id}/validate` | drafts_runs | draft-version/review/export lifecycle; **retain existing** |
| `POST /api/v2/program-drafts/{draft_id}/request-review` | drafts_runs | draft-version/review/export lifecycle; **retain existing** |
| `POST /api/v2/program-drafts/{draft_id}/review` | drafts_runs | draft-version/review/export lifecycle; **retain existing** |
| `POST /api/v2/program-drafts/{draft_id}/preview` | drafts_runs | draft-version/review/export lifecycle; **retain existing** |
| `POST /api/v2/program-drafts/{draft_id}/withdraw` | drafts_runs | draft-version/review/export lifecycle; **retain existing** |
| `POST /api/v2/program-drafts/{draft_id}/export` | drafts_runs | draft-version/review/export lifecycle; **retain existing** |
| `GET /api/v2/program-drafts/{draft_id}/export/manifest` | drafts_runs | draft-version/review/export lifecycle; **retain existing** |
| `GET /api/v2/programs` | drafts_runs | program/run/override/queue/Worker/Gold/manifest authority; **retain existing** |
| `GET /api/v2/programs/{code}` | drafts_runs | program/run/override/queue/Worker/Gold/manifest authority; **retain existing** |
| `POST /api/v2/run-batches` | drafts_runs | program/run/override/queue/Worker/Gold/manifest authority; **retain existing** |
| `GET /api/v2/run-batches` | drafts_runs | program/run/override/queue/Worker/Gold/manifest authority; **retain existing** |
| `GET /api/v2/run-batches/{batch_id}` | drafts_runs | program/run/override/queue/Worker/Gold/manifest authority; **retain existing** |
| `GET /api/v2/run-batches/{batch_id}/items` | drafts_runs | program/run/override/queue/Worker/Gold/manifest authority; **retain existing** |
| `POST /api/v2/run-batches/{batch_id}/cancel` | drafts_runs | program/run/override/queue/Worker/Gold/manifest authority; **retain existing** |
| `POST /api/v2/run-batches/{batch_id}/retry-failed` | drafts_runs | program/run/override/queue/Worker/Gold/manifest authority; **retain existing** |
| `POST /api/v2/clients/{client_id}/units/{unit_id}/base-year` | drafts_runs | program/run/override/queue/Worker/Gold/manifest authority; **retain existing** |
| `GET /api/v2/clients/{client_id}/units/{unit_id}/rebase` | drafts_runs | program/run/override/queue/Worker/Gold/manifest authority; **retain existing** |
| `POST /api/v2/clients/{client_id}/runs` | drafts_runs | program/run/override/queue/Worker/Gold/manifest authority; **retain existing** |
| `GET /api/v2/clients/{client_id}/runs/latest` | drafts_runs | program/run/override/queue/Worker/Gold/manifest authority; **retain existing** |
| `GET /api/capabilities` | ai | canonical producer/narration/conversation authority; **retain existing** |
| `POST /api/capabilities/{tool}` | ai | canonical producer/narration/conversation authority; **retain existing** |
| `POST /api/chat` | ai | canonical producer/narration/conversation authority; **retain existing** |
| `POST /api/summary` | ai | canonical producer/narration/conversation authority; **retain existing** |
| `GET /api/workspace` | workspace_sealed | all eleven unavailable; reference owner; **retain existing** |
| `POST /api/workspace/refresh` | workspace_sealed | all eleven unavailable; reference owner; **retain existing** |
| `POST /api/workspace/source/search` | workspace_sealed | all eleven unavailable; reference owner; **retain existing** |
| `POST /api/workspace/eligibility/search` | workspace_sealed | all eleven unavailable; reference owner; **retain existing** |
| `POST /api/workspace/employee` | workspace_sealed | all eleven unavailable; reference owner; **retain existing** |
| `GET /api/workspace/onezero/{method}` | workspace_sealed | all eleven unavailable; reference owner; **retain existing** |
| `POST /api/workspace/onezero/contributors` | workspace_sealed | all eleven unavailable; reference owner; **retain existing** |
| `GET /api/workspace/calculation-walk` | workspace_sealed | all eleven unavailable; reference owner; **retain existing** |
| `GET /api/workspace/assumptions` | workspace_sealed | all eleven unavailable; reference owner; **retain existing** |
| `GET /api/workspace/comparison` | workspace_sealed | all eleven unavailable; reference owner; **retain existing** |
| `POST /api/workspace/comparison/stage` | workspace_sealed | all eleven unavailable; reference owner; **retain existing** |
| `GET /channel/health` | gateway | gateway/canonical producer/audit/session/ticket authority; **retain existing** |
| `GET /channel/ready` | gateway | gateway/canonical producer/audit/session/ticket authority; **retain existing** |
| `GET /channel/v1/tools` | gateway | gateway/canonical producer/audit/session/ticket authority; **retain existing** |
| `POST /channel/v1/tools/{tool}` | gateway | gateway/canonical producer/audit/session/ticket authority; **retain existing** |
| `POST /channel/v1/audit/narration` | gateway | gateway/canonical producer/audit/session/ticket authority; **retain existing** |
| `GET /channel/v1/downloads/{ticket}` | gateway | gateway/canonical producer/audit/session/ticket authority; **retain existing** |
| `POST /mcp` | gateway | gateway/canonical producer/audit/session/ticket authority; **retain existing** |
| `GET /mcp` | gateway | gateway/canonical producer/audit/session/ticket authority; **retain existing** |
| `DELETE /mcp` | gateway | gateway/canonical producer/audit/session/ticket authority; **retain existing** |
| `POST /responses` (outside captured inventory) | orchestrator | Whole conversation/confirmation; **retain existing** |
