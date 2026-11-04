# Master run status

Customer-neutral. Resume from this file if the run is interrupted.

Rollback tag: `pre-master-2026-11-03` (tip `58dcd53`).

## Stage 0 — Preflight: done

- Main checkout, branch `feat/m365-channel`, tree clean, merge `58dcd53` at the tip.
- `ASK-EVIDENCE-CONTRACT.md`, `frontend/src/components/ask/`, DECISIONS D-100..D-103 present.
- `channel_orchestrator/azure.yaml`: container protocols `responses` only; `agentEndpoint.protocols` `responses` + `activity`.
- azd environments present (root default, orchestrator project default). Python 3.14 `.venv` used.
- Baseline backend: 2817 passed, 136 skipped, 1 xfailed. Baseline frontend: 923 passed (after `npm install --legacy-peer-deps`
  restored the missing `@fontsource` files; one font-file test failed before that).

## Stage 1 — CH-15 demo polish: done (offline)

| WP | Status | Branch | Merge SHA | Evidence |
| --- | --- | --- | --- | --- |
| CH-15e known issues (Graph stale-token retry, client_resolve, debug-whoami posture) | done | wp/CH-15e-known-issues | c06c63c | backend 2866 passed |
| CH-15a display names from Graph | done | wp/CH-15a-display-names | dc03820 | backend 2932 passed; terraform test 63 passed |
| CH-15b agent icon (SVG + render + publish + Cowork build) | done | wp/CH-15b-agent-icon | 9b743df | backend 2970 passed; Chromium render (cairo DLL unavailable) |
| CH-15c narration quality, hedging guard, planner goldens, evals | done | wp/CH-15c-narration | acfc4c4 | backend 3067 passed |
| CH-15d portal chat evidence SSE | done | wp/CH-15d-portal-evidence | d12d3e0 | backend 3088 passed; frontend 929 passed; build ok; check_all 21/22 (the all-tree gitleaks row lists untracked/ignored working-tree files, pre-existing) |

Live redeploy (Stage 3) must: set `TCC_CHANNEL_RESOLVE_DISPLAY_NAMES=true` and provision; admin grants Graph `User.ReadBasic.All` to the gateway identity
(`assign-channel-roles.ps1 -GrantUserReadBasic`); render icons, publish as 1.0.3 with icons; rebuild and upload the Cowork zip; run
`python scripts/vendor-orchestrator.py` before the orchestrator `azd deploy`.
## Stage 2 — CH-16 governed Fabric data access: done (offline)

| WP | Status | Merge SHA | Evidence |
| --- | --- | --- | --- |
| CH-16a semantic model | done | 9992238 | backend 3996 passed (with 16b) |
| CH-16b spec, validation, SQL builders | done | 3149b1f | |
| CH-16c executors, limits, provenance | done | 0a63846 | backend 4675 passed |
| CH-16d capabilities, lanes | done | efd3f70 | backend 4811 passed |
| CH-16e planner, narrator, skills, goldens, equivalence | done | e85afd4 | backend 4918 passed; 29 goldens; 11 equivalence tests |
| CH-16f docs, security, grants, Fabric-agent evaluation | done | ed2fbb6 | backend 4942 passed; terraform test 70 passed |

## Stage 3 — CH-17 live redeploy and verification: part A (3.1 to 3.3) done; 3.4 to 3.7 belong to other agents

Rollback tag for code: `pre-final-run-2026-11-03` (tip of `feat/m365-channel` at the start of part A). Note the tag holds the NEW code; the
code that is live now (known-good) is the one stamped `GIT_COMMIT` in the azd environment (an older commit on this branch's history).

### Known-good baseline (before any Stage 3 change)

- Guards: subscription and tenant as required; only the PoC resource group is touched. Global Administrator (PIM) not active
  (Agent ID Administrator/Developer, Global Reader, Agent Registry Administrator), so Graph/Entra grants are admin actions.
- Hosted agent `tcc-channel-orchestrator`: latest version **16** (published manifest 1.0.2), endpoint selector `@latest` at 100%.
  Invariants (section 2 of the stage prompt) all PASS: 13 of 13 (helper: `agent-invariants.ps1`, see "Helpers").
- App Service deployments (Kudu): API, web and gateway were each zip-deployed once on 3 Nov from the earlier live-deploy run;
  `GIT_COMMIT` stamped on both API and gateway = the older commit recorded in the azd environment (`40404da`).
- `azd provision --preview` with the sandbox overlay copied to `infra/m365-poc.auto.tfvars` (gitignored): **No changes**.
- Live settings: `AUTH_MODE=entra`, `DATA_CLASSIFICATION=synthetic`, writer source `either`, `ai_provider_chain=foundry,gateway`
  on the API, `CHANNEL_DEBUG_WHOAMI=true` on the gateway and the agent (kept on purpose for the owner's retest).
- Graph `User.ReadBasic.All` is assigned to the gateway identity (verified read-only), so display-name resolution only needs the setting.
- Direct Responses call as the operator: `/whoami` answered by version 16, identity source `agent-user-id`, display name "(name not provided)".
### 3.2 New configuration: done

- azd values set: `TCC_CHANNEL_RESOLVE_DISPLAY_NAMES=true`, `TCC_DATA_QUERY_SOURCE_ENABLED=true`, `TCC_LAKEHOUSE_SQL_SERVER` and
  `TCC_LAKEHOUSE_SQL_DATABASE` (read-only from the Fabric API: the lakehouse SQL analytics endpoint shares the Warehouse host, the
  database is the lakehouse name, so the code fallbacks were right; set explicitly anyway), `GIT_COMMIT` = the code tip. Other `DATA_QUERY_*` keep defaults.
  `AUTH_MODE=entra`, `DATA_CLASSIFICATION=synthetic`, writer source `either` and the demo Foundry posture unchanged.
- Sandbox overlay copied to `infra/m365-poc.auto.tfvars` (gitignored, verified with `git check-ignore`); it keeps `channel_debug_whoami = true`.
- `azd provision`: 0 added, 2 changed (API and gateway app settings only: `DATA_QUERY_SOURCE_ENABLED`, `LAKEHOUSE_SQL_*`,
  `CHANNEL_RESOLVE_DISPLAY_NAMES`, `GIT_COMMIT`), 0 destroyed. A second `--preview` converges: **No changes**.
- The `postprovision` hook did not print under a redirected `azd provision`; it was run explicitly with `azd hooks run postprovision`:
  migrations 0 pending (0001 and 0002 recorded, `tcc_ops.schema_migration` present), schema and gateway grants idempotent,
  **lakehouse endpoint grants (read-only `SELECT` on the three source tables) succeeded**, seed wrote nothing.

### 3.3 Components: done, nothing rolled back

| Component | Result |
| --- | --- |
| API (`azd deploy api`) | deployed (azd's own status-change warning after 5 minutes was benign); the API answers through the gateway (`book_rank`, `data_catalog`, `data_query` 200); a lakehouse **source** count and a Warehouse count both returned for a synthetic client, so the API identity reads the lakehouse endpoint |
| Web (`azd deploy web`) | deployed, `/healthz` 200 |
| Migrations (`apply-migrations.py --target deployed`, no bootstrap) | 0 pending |
| Gateway (postdeploy hook, `deploy-channel.ps1`) | redeployed by each `azd deploy`; `/channel/health` 200, `/channel/v1/tools` 401 without a token, 200 with a delegated token and 32 tools (31 plus the debug ping), including `data_catalog`, `data_query`, `data_distinct_values` |
| Orchestrator (`vendor-orchestrator.py`, then `azd deploy` in `channel_orchestrator/`) | new hosted version **17**; all 13 agent invariants PASS afterwards, no repair needed; `/whoami` and a whole-book question answered by version 17 over the Responses protocol |
| Mock AI gateway | untouched |

Global Administrator was not needed in part A. Admin actions outstanding: none.

### Helpers (outside the repo, session scratch folder; copy elsewhere to keep)

`<session-state>/a470b217-.../files/`: `agent-invariants.ps1` (PASS/FAIL list of the section 2 invariants), `agent-invoke.ps1`
(Responses call as the signed-in operator; `-SessionId` for a follow-up turn, `-Raw` for the JSON), `agent-endpoint.ps1`
(`-Action Restore|Pin -Version n|Latest`: repairs the endpoint or pins the selector; `-WhatIf` prints the body).

### Rollback commands (not needed)

Agent: `pwsh agent-endpoint.ps1 -Action Pin -Version 16`, then `agent-invariants.ps1`. API/gateway: package the previously live commit
(`git archive <GIT_COMMIT recorded in the azd env before this run> backend`, `scripts/package-app.py`) and `az webapp deploy` it to that app.
Settings: `azd env set` the three new values back (`false`/empty) and `azd provision`.
## Stage 4 — CH-18: runs in "keep main untouched" mode (owner change of plan, 3 Nov)

`main` stays at `029b9ad2d2c002c09167375748120c7a8af3bc03`; it is never fast-forwarded, merged into, reset or rebased, and
neither is `origin/main`. No branch is deleted (wp/*, feat/ui-modern-theme, feat/m365-channel, jamesiford-*), and the tag
`pre-master-2026-11-03` stays. Branch of record: `feat/m365-channel`, tagged `m365-channel-poc-2026-11-03` at its final tip (tags
only, no push). Worktrees are removed only after proving them clean and fully merged and the live-state folders intact
(`.azure/tcc-poc-channel/`, `channel_orchestrator/.azure/tcc-orch/`, `overlays/m365-poc/`); otherwise they are left and listed.
FINAL-STATE.md gets a "Planned branch split (not done)" section and PUSH-CHECKLIST.md records it as an owner decision.
Status: todo

## Blockers

None.

Gate before Stage 3 (tip after CH-16f): backend 4942 passed / 136 skipped / 1 xfailed; frontend 929 passed, build ok; terraform fmt ok, test 70 passed. Operator's Global Administrator (PIM) is NOT active (roles: Agent ID Administrator/Developer, Global Reader, Agent Registry Administrator), so any step needing it is an admin action.
