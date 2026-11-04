# Live remediation redeploy, 2026-11-04 (RM-16)

Customer-neutral and redacted: no token, tenant, subscription or Entra identifier, no email, no payroll value, no employee identifier.
Run as the signed-in sandbox operator (`<operator>`) from the main checkout on `wp/RM-16-live-redeploy`, against the deployed PoC,
inside the stage-3 guards (one resource group; the shared Fabric capacity read-only; no Entra, consent or secret change; demo network
posture unchanged; Global Administrator not active, none needed).

**Outcome: partly done, verification pending.** The code is deployed and every check that needs no data passed. Every data path
(and the audit that the orchestrator's reply depends on) answered `503` for the whole session, because **the shared Fabric capacity
was suspended** at 08:36 UTC by a scheduled job outside this repository and stayed suspended for the 90 minutes this run waited.
The guards forbid resuming or changing it from here, so the ten live questions, the prepared write, the review pack and the
data-dependent smoke checks were **not run**. Nothing was rolled back: no invariant and no question regressed. The exact commands to
finish are at the end.

## What was deployed (and what was not)

| Step | Result |
| --- | --- |
| Offline gate before any change | backend **6002 passed / 136 skipped / 1 xfailed** (the RM-14 count, reproduced); `check-whitelabel -Enforce` 0 enforced; `audit-export --enforce` 0; gitleaks (210 commits) no leaks; vendored copy matches |
| `az account show` | the pinned subscription and tenant |
| Rollback references | agent **version 20** (13 of 13 invariants measured before the change); code tags `pre-remediation-2026-11-04` (this run's start) and `m365-channel-poc-2026-11-03` (what was live) |
| `azd provision --preview` (azd env `tcc-poc-channel`, overlay copied to `infra/m365-poc.auto.tfvars`, identical to the overlay) | **5 in-place changes, 0 add, 0 destroy**, none of them a new setting of this run: the plan SKU `P1v2` to `P1v3` and `always_on` `false` to `true` on four apps (web, API, gateway, mock gateway). Drift between the live state and Terraform that this run did not cause. **Not applied** (D-137). The same 5 changes show after every deploy of this run, so the deploys changed none of it |
| `azd deploy api` | succeeded (1 m 25 s). Its postdeploy hook redeployed the **gateway** (Kudu: API and gateway each one new deployment, 15:27 and 15:28 UTC; web untouched) |
| API and gateway checks | gateway `/channel/health` 200; `/channel/v1/tools` without a token 401; web `/healthz` 200; REST and MCP `tools/list` both **32 tools**, equal to the catalog (the smoke's catalog step); no schema change since the stage-3 tag, so 0 pending migrations (the dry run itself could not reach the Fabric API, see below); the destructive bootstrap was never run |
| `python scripts/vendor-orchestrator.py` then `azd deploy` in `channel_orchestrator` | succeeded (1 m 28 s); agent **version 21** (content hash differs from 20), selector `@latest` 100 %, instance identity unchanged |
| Settings | unchanged: `DATA_MIN_GROUP_SIZE` not set (code default 5), `CHANNEL_CALLER_CHANNELS` not set, `CHANNEL_MCP_ALLOWED_ORIGINS` not set, `CHANNEL_DEBUG_WHOAMI` left `true` (an invariant) |

## Agent invariants (the Teams-silencing set)

| When | Result |
| --- | --- |
| Before (version 20) | 13 of 13 PASS |
| Immediately after the orchestrator deploy (version 21) | **13 of 13 PASS**: `responses` only on the container; endpoint `activity` and `responses`; public M365 endpoint on; schemes `BotServiceRbac` and `Entra`; selector `@latest` 100 %; debug and identity-source environment values; provider chain `foundry`; instance identity holds *Cognitive Services User*, *Foundry User* and the gateway app role; bot endpoint ends `/activityProtocol`; Teams channel enabled. No endpoint repair was needed |
| End of run (version 21) | **13 of 13 PASS** |

## Live checks that needed no data

`/whoami` as the operator on version 21: HTTP 200, `version: 21`, `identity.resolved: true`, source `agent-user-id`, providers `foundry`,
`tools_available` and `model_configured` true, display name "(name not provided)" as before (the audit holds the resolved name).

### The RM-09 checklist (D-127), point by point

| # | Point | Result |
| --- | --- | --- |
| 1 | `/netcheck` and `/modelprobe`: account host resolves, project host does not | **As predicted.** `<account>.openai.azure.com` resolves (public address), TCP and TLS ok, a bare request answers 401. `<account>.services.ai.azure.com` and `<account>.cognitiveservices.azure.com` do **not** resolve (`Temporary failure in name resolution`). `/modelprobe` (the sample's project-host path) fails with the same name-resolution error. So `FoundryChatClient` is still not usable from the hosted runtime and the decision (D-127) stands |
| 2 | The remote build installs `agent-framework-openai` and `openai`; the agent starts | **PASS.** Version 21 became active, answered, and the container log shows the framework's HTTP client (`httpx2`) making the call |
| 3 | A tool-calling question gets a model answer on the framework path | **PASS for the path, not for the audit field.** "Who should we call first and why?" and "What can you help me with?": the container log shows `POST https://<account>.openai.azure.com/openai/v1/chat/completions` **200 OK**, then `Function name: book_rank` chosen by the model and run through the tool rules. The `model` and `mode=tools` fields of the narration audit row could not be read because the audit write itself was refused (`503`, below). A `gpt-5` family deployment was **not** tried (only `gpt-4.1-mini` is deployed here) |
| 4 | A request really carries a bearer token; the identity keeps its two roles | **PASS.** The call above is authorised on a key-less account (local auth is off), so the token provider worked; the invariants confirm *Foundry User* and *Cognitive Services User* |
| 5 | Behaviour when the model is slow or errors | **Not run live** (no fault to inject without changing the account). The data outage below is the live evidence for the same degrade rule: a tool refusal is reported honestly and nothing is invented |
| 6 | Latency against the earlier path | **Indicative only.** Whole Responses calls took 6 to 12 s for `/whoami`, `/netcheck`, `/modelprobe`, "What can you help me with?" and the degraded whole-book question, each on a cold session (the earlier run's per-question times were not recorded, so there is no like-for-like). One HTTP client per turn is as designed |

F-17 (`FOUNDRY_MODEL` declared under `env:` although the prefix is reserved): live check done. `/netcheck` shows `FOUNDRY_MODEL=gpt-4.1-mini` in the container's
environment and the model call used that deployment, so the platform does not shadow or strip it. No rename is needed.

### The data outage, as the orchestrator behaves in it

Whole-book question with every data path down: the model chose `book_rank`, the gateway answered `503 Service Unavailable`, the orchestrator replied
**"I couldn't answer that: the audit trail is unavailable; nothing was done."** (no figure, no guess), and the container log carries one
`ERROR tcc.orchestrator.audit audit_write_failed source=narration operation=report error_code=audit_unavailable`: the RM-03 alert line, observed live
(names and codes only, no payload). This is the fail-closed behaviour working as designed; it is also why a paused capacity looks like a total outage.

### MCP facade (RM-14), against the deployed gateway

All with an operator token for the gateway's `Channel.Access` scope; no tool was called.

| Probe | Expected | Got |
| --- | --- | --- |
| `initialize` with `Origin: https://evil.example` and a valid token | 403 `origin_not_allowed`, before the token is read | **403** |
| `initialize`, no `Origin`, valid token | 200 and a session id | **200**, session id returned |
| any request, no token | 401 with a `Bearer` challenge | **401** (challenge header present; the console masks its value) |
| `tools/list` with no session id | 400 | **400** |
| `tools/list` with an unknown session id | 404 | **404** |
| `tools/list` with an unsupported `MCP-Protocol-Version` | 400 | **400** |
| `tools/list` with the session | 200, 32 tools | **200, 32 tools** |
| `ping` with the session | 200 | **200** |

Not run: a request from the real Cowork client (F-27, whether it sends an `Origin`): needs the owner's Cowork sign-in. The default stays "admit none".

## What the outage blocked

Gateway smoke after the API and gateway deploy (`channel-live-smoke.py --only catalog,reads,writes,verify,audit --compare-local`):
**4 passed, 21 failed**. The four are the catalog and 401 checks (32 tools, REST equals MCP, no token 401, wrong audience 401). The 21 failures are the read
tools, the write round trip and `verify_figures`, all `503` or a consequence of it (no calculated year could be listed). They are **not regressions**: the same code
answered `503` for a plain book question and for the audit write. The one write attempt of the smoke failed at `prepare` (500/500) and `claim_transition` was refused
at validation (422, no year found), so **nothing was written**; the restore step of that smoke had nothing to restore.

| Not run | Why |
| --- | --- |
| Ten live questions and the review pack question | no data path; the orchestrator can only say the audit is unavailable |
| The prepared write (not committed) and the audit check "prepare without commit" | same; the writer check, the preview and the audit all need the Warehouse |
| Smoke reads, writes, `verify_figures`, audit, `--compare-local` | same |
| `live-ai-checks.py` | needs the API's data and the model gateway path; skipped |
| Small-group suppression live, writer view and non-exempt view | needs data; the non-writer half is offline only (`test_data_small_groups.py`, 35 cases) as before |
| Cowork-like employee-level request as a writer, and as a non-writer | needs data (offline: `test_cowork_fails_closed.py`) |
| Apply-migrations dry run | the Fabric REST API (which resolves the Warehouse for the guard) answered 500 while the capacity was suspended; no schema file changed since the stage-3 tag |
| Confirmation by a different person refused | needs a second person (offline) |

## How to finish (owner action first)

1. **Resume the shared Fabric capacity** (the owner's action; this run may not touch it): `az resource show` on the capacity must say `Active`. It is suspended nightly
   at about 08:36 UTC by a scheduled caller that is not in this repository (the activity log shows the same suspend at 08:37 UTC on 3 November); the resumes
   the log shows on 3 November were made by the operator account. Allow a few minutes for the API to warm.
2. From the repository root, with the helper scripts (the private deploy notes list their durable copies):
   `pwsh agent-invariants.ps1` (13 of 13), `pwsh agent-invoke.ps1 -Text '/whoami'`;
   `. load-api-env.ps1 ; python scripts/channel-live-smoke.py --only catalog,reads,writes,verify,audit --compare-local`
   (expect all pass, the honest skip `finding_resolve`); then the twelve questions (`run-rm16-qs.ps1`: the ten of CH-17 plus
   "Give me a review pack for Northwind Care Systems for tax year 2025." and a prepared, uncommitted write "Move Northwind Care Systems tax year 2025 to proposed.").
3. Compare against [live-final-2026-11-03.md](../../archive/evidence/live-final-2026-11-03.md), then add the result here.
4. **If anything regresses:** `pwsh agent-endpoint.ps1 -Action Pin -Version 20`, then `pwsh agent-invariants.ps1` (13 of 13; `-Action Restore` if an endpoint was overwritten).
   For the API or gateway: package `git archive m365-channel-poc-2026-11-03 backend` with `scripts/package-app.py` and `az webapp deploy` it to the app.

## State left behind

Agent **version 21** latest, selector `@latest` 100 %, invariants 13 of 13; API and gateway on this run's code; web unchanged (no frontend change in the run);
Terraform plan unchanged (the 5 drift items above); no setting, role, grant or secret changed; nothing pushed; no write to any client's claim or engagement.
