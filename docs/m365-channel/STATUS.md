# Microsoft 365 channel — status

Customer-neutral. This file is the only memory a resumed session has; keep it
truthful. Decisions live in [DECISIONS.md](DECISIONS.md).

Integration branch: `jamesiford-m365-capability-layer` (see D-01 — this session
runs in a worktree, so `feat/m365-channel` is held by the main checkout).

## Work packages

| WP | Title | Status | Branch | Merge SHA |
| --- | --- | --- | --- | --- |
| CH-01 | Capability layer (`application/capabilities/`) | done | `wp/CH-01-capabilities` | `0c8a4d8` |
| CH-02 | Numeric guard, composer, narrator agent, ADR-008 | done | `wp/CH-02-numeric-guard` | `f1c7815` |
| CH-03 | Channel audit trail | done | `wp/CH-03-channel-audit` | `087847f` |
| CH-04 | Identity, authorization, writer entitlement | done | `wp/CH-04-identity-authz` | `603418e` |
| CH-05 | Prepare/commit safe writes | done | `wp/CH-05-safe-writes` | `e5634c3` |
| AI-01 | Latest stable SDKs | done | `wp/AI-01-sdk-upgrade` | merge `6b36f0f` |
| AI-02 | Ports, adapters, streaming mediator | done | `wp/AI-02-ports-adapters` | merge `2bab7a2` |
| AI-03 | External model gateway | done | `wp/AI-03-model-gateway` | merge `e7de7fc`; gateway adapter, auth, egress, mock gateway, Terraform (terraform test 30/30) |
| AI-04 | Resilience | done | `wp/AI-04-resilience` | merge `045aaef`; stack, budget, degraded narration (1975 passed) |
| AI-06 | Observability, prompt versioning, evals | done | `wp/AI-06-observability` | merge `2c72519`; OTel GenAI telemetry, prompt manifest, evals (1997 passed) |
| AI-07 | Safety | done | `wp/AI-07-safety` | merge `83fa319`; injection screen, output policy, stream gate (2104 passed) |
| AI-08 | Coding-standards ratchet | done | `wp/AI-08-standards` | merge `3a782d6`; ratchet baseline 540 → 483, five channel modules split (2128 passed) |
| AI-05 | Conversation continuity (stretch, last) | deferred | — | see D-60: needs a migration, two store adapters, a deployed-store check and Terraform; not started |
| CH-06a | `POST /api/capabilities/{tool}`, `GET /api/capabilities`, claim package create/link | done | `wp/CH-06a-capabilities-api` | merge `cbaad1a` |
| CH-06b | Channel gateway (`backend/channel`), MCP facade, `verify_figures`, ticketed downloads | done | `wp/CH-06b-gateway` | merge `f9a4711` |
| CH-07 | Terraform `channel` module, packaging, grants, docs | done | `wp/CH-07-channel-infra` | merge `ed36927` |
| CH-07b | Deploy the gateway from a hook (azd has no conditional service) | done | `wp/CH-07b-channel-deploy-hook` | merge `47a8741` |
| CH-08 | Hosted orchestrator (`channel_orchestrator/`), narration audit | done | `wp/CH-08-orchestrator` | merge `063afec` |
| CH-09 | `scripts/publish-m365.ps1` | in_progress | `wp/CH-09-publish-m365` | — |

## Evidence

### CH-01 (merged `0c8a4d8`)

- `cd backend ; ..\.venv\Scripts\python.exe -m pytest tests/ -q` — **1407 passed,
  122 skipped, 1 xfailed** (baseline before the WP: 1261 passed, 122 skipped,
  1 xfailed). Skips are the opt-in Fabric tests and the absent private reference
  fixtures; no new skip was added. Synthetic parity gate (81/51/49) green; the
  pinned constants and `certified-figures.json` are untouched.
- No existing test was edited. `test_architecture.py` gained five rules (framework
  / router / agent imports in `application/capabilities/`, stdlib-only for
  `catalog.py` and `format.py`, no `tools.*` in `api/chat.py`, and a
  crafted-violation check).
- `tests/route_inventory.json` unchanged (no route added or removed).
- `pwsh scripts/check-whitelabel.ps1 -Enforce` — 0 enforced (29 allow-listed).
  `python scripts/audit-export.py --enforce` — 0 findings.
  `gitleaks git --no-banner --redact --exit-code 1 .` — no leaks.
- `infra/` untouched, so no Terraform checks.

Capability functions (all in `application/capabilities/`, returning `ToolResult`):

| Tool | Signature |
| --- | --- |
| `book_rank` | `book_rank(limit=8, *, page_reader=None)` |
| `client_resolve` | `client_resolve(name_or_text, history=(), current_client_id=None, *, strict=False)` |
| `client_situation` | `client_situation(client_id, year=None)` |
| `client_eligibility` | `client_eligibility(client_id, tax_year, state="GA", method="min_max", *, window=None, include_population=False)` |
| `client_trend` | `client_trend(client_id, method="pay_period")` |
| `client_at_risk` | `client_at_risk(client_id, tax_year, state="GA", method="min_max")` |
| `client_discovery` | `client_discovery(client_id=None, tax_year=None, state=None, *, exclude_codes=None)` |
| `simulate` | `simulate(client_id, tax_year, worksite_id, action="add_headcount", magnitude=1.0, state="GA", method="min_max", hire_weekly_hours=None, hire_hourly_rate=None)` |
| `calc_walkthrough` | `calc_walkthrough(client_id=None, tax_year=None, state="GA", method="min_max", *, trail=None)` |
| `employee_drill` | `employee_drill(client_id, record_token, tax_year, state="GA")` |
| `findings_list` | `findings_list(client_id, tax_year, state=None)` |
| `claim_cell_history` | `claim_cell_history(client_id, program_code, tax_year)` |

Also `simulate_headcount(location, new_hires)` (the portal's straight-line what-if).
`verify_figures` and the seven `*_prepare` / `*_commit` write pairs are declared in
the catalog with `implemented: false`.

Behaviour deliberately preserved rather than fixed (see D-05, D-06): the chat's
eligibility brief reads the pay-period average whatever method the scope selects,
and its `discovery` / `multi_state` scans read the configured default tenant.

### CH-02 (merged `f1c7815`)

- Full backend suite: **1565 passed, 122 skipped, 1 xfailed** (CH-01 baseline:
  1407 passed). No new skip; synthetic parity gate green; pins untouched.
- New: `test_numeric_guard.py` (extraction shapes, every formatter spelling, wrong
  figures, non-ASCII and space-split digits, the flipped-digit mutation loop and
  its meta-test that fails when the guard is replaced by an always-pass one),
  `test_composer.py` (placeholders, narrator-typed figures, formatter-bug defence
  in depth, blocks-only fallback, guard-is-consulted), `test_channel_narrator.py`.
  `test_capabilities_envelope.py` now runs the flipped-digit loop over the blocks
  of every capability (more than a hundred corruptions, all refused).
- Existing test edited: `test_rules_ingestion.py` roster pin eleven -> twelve
  (D-18). `test_architecture.py` gained `envelope.py` in the stdlib-only rule.
- `ChannelNarratorAgent` registered in `agents/factory.list_agent_modules()`;
  its profile is checked by the existing agent-module contract tests. There is
  no `/api/agents` route in this repository (D-18).
- Standard gate: `check-whitelabel.ps1 -Enforce` 0 enforced; `audit-export.py
  --enforce` 0 findings; `gitleaks` no leaks; route inventory unchanged;
  `infra/` untouched.
- Docs: ADR-008 written and linked from `docs/README.md`; ADR-004 carries a
  status note; the "honest limit" paragraph in `.github/copilot-instructions.md`
  now says the portal chat path still streams unvalidated prose.

### CH-03 (merged `087847f`)

- Full backend suite: **1639 passed, 135 skipped, 1 xfailed** (CH-02: 1565 passed).
  The extra skips are the Warehouse contract variants (`TCC_FABRIC_TESTS`); no
  `skip`/`xfail` added to pass a gate; pins untouched.
- Migrations (SHA-256):
  - `0001_channel_audit.sql` `b3e9a9af988c9acc70bcb158c589358eca6983477654cb35f5385c12a0f8ef83`
  - `0002_engagement_actor.sql` `b6dea4400282db7c2b3198d0a75792c069f55fb0a0a477bd52a07b21cd37e7fa`
- New route `GET /api/audit/channel` (added to `tests/route_inventory.json`).
- New: `domain/channel.py`, four persistence adapters, `application/channel_audit.py`,
  `application/agent_audit.py`, `scripts/channel-audit.py`, gateway grant profile in
  `grant-warehouse-sql.py`, `CHANNEL_STORE` in ENV-VARS. Decisions D-20..D-24.
- No existing test edited. Standard gate: whitelabel 0 enforced, audit-export 0
  findings, gitleaks clean. `infra/` untouched.

### CH-04 (merged `603418e`)

- Full backend suite: **1706 passed, 135 skipped, 1 xfailed** (CH-03: 1639 passed).
  No skip/xfail added; pins untouched.
- New: `application/acting_user.py`, `application/authorization.py`,
  `infrastructure/auth/writers.py`, `scripts/channel-writers.py`,
  `tests/test_agent_principal.py` (67 tests). `Principal` gained `principal_type`
  and `acting_for`; `Mediator` gained a real Authorization stage. Decisions
  D-25..D-30.
- Routes: no route added or removed. `/api/me` gained `principal_type` and
  `acting_for`; `GET /api/audit/channel` refuses an agent principal;
  `PUT /api/claims/engagement` now records `set_by`/`set_at`.
- Existing tests edited (D-30): `test_mediator.py` stage test (Authorization is now
  a stage; `_scope_tenant` still is not) and `test_auth.py::test_me_...` (two
  additive fields).
- Docs: ADR-003 status note, `.github/copilot-instructions.md` pipeline bullet,
  mediator docstring, SECURITY.md, ENV-VARS (four new variables).
- Standard gate clean; `infra/` untouched. Owner actions: assign `TCC.Agent` to the
  gateway's service principal; for `entra_group`, grant Graph `GroupMember.Read.All`.

### CH-05 (merged `e5634c3`)

- Full backend suite: **1735 passed, 135 skipped, 1 xfailed** (CH-04: 1706 passed).
  No skip/xfail added; pins and `infra/` untouched; standard gate clean.
- New: `application/confirmations.py`, `capabilities/writes.py` (six prepare/commit
  pairs), `capabilities/write_specs.py`, commands `record_claim`, `transition_claim`,
  `set_engagement`, `tests/test_channel_writes.py` (28 tests). `plan_base_year`
  extracted from the base-year handler. Decisions D-31..D-35.
- Built: `finding_resolve`, `finding_reopen`, `claim_transition`, `claim_record`,
  `engagement_set`, `base_year_set`. Unbuilt: `claim_package_create` (Prompt 3) and
  `verify_figures`.
- Existing tests edited (D-35): the two unbuilt-write assertions in
  `test_capabilities_envelope.py` and `test_capabilities_equivalence.py`.
- Open for Prompt 3: the channel route that wraps reads in the auditor; the writes
  audit themselves, so it must not audit write capabilities a second time.

### AI-01 … AI-08 (Prompt 2B, merged `6b36f0f` … `3a782d6`)

- Suite trajectory (`cd backend ; ..\.venv\Scripts\python.exe -m pytest tests/ -q
  -p no:cacheprovider`): 1793 (AI-02) → 1929 (AI-03) → 1975 (AI-04) → 1997 (AI-06) →
  2104 (AI-07) → **2128 passed, 136 skipped, 1 xfailed** (AI-08). Skips are the
  opt-in Fabric tests, the absent private reference fixtures and the opt-in live AI
  evals; no skip or xfail was added to pass a gate. Synthetic parity gate (81/51/49)
  green throughout; the pinned constants and `certified-figures.json` are untouched.
- Every WP ran: `pwsh scripts/check-whitelabel.ps1 -Enforce` (0 enforced, 29
  allow-listed), `python scripts/audit-export.py --enforce` (0 findings) and
  `gitleaks git --no-banner --redact --exit-code 1 .` (no leaks). AI-03 also ran the
  infra gate: `terraform fmt -check -recursive`, `init -backend=false`, `validate`,
  `tflint --recursive`, `terraform test` (30 passed, 0 failed).
- `python scripts/prompt-manifest.py` agrees; `python scripts/ai-eval.py` offline:
  routing 19/19, narration 10/10, refusal 10/10.
- Existing tests edited, all recorded in DECISIONS (D-39/D-40, D-50, D-55, D-56,
  D-59): `test_agent_modules`, `test_channel_narrator`, `test_channel_audit`,
  `test_chat_scope`, `test_page_summary`, `test_architecture`, `test_architecture_ai`,
  `test_ai_fallthrough` (single injected fault → three, as a lone fault is now
  retried), `test_ai_degraded` (held text is not "shown"), `test_composer` and
  `test_numeric_guard` (import-purity now spans the split sibling set), `conftest.py`.
- Not verified against live Azure: `scripts/create-model-connection.ps1` (Bicep
  parameter names are a guess); the mock gateway's code deployment is a manual step;
  no `az`/`azd` was run.

### CH-06a (merged `cbaad1a`) and CH-06b (merged `f9a4711`)

- Integration branch is `feat/m365-channel` itself (D-61). Python 3.14 venv (D-62).
- Full backend suite after CH-06b: **2360 passed, 136 skipped, 1 xfailed** (Prompt 2B
  baseline: 2128 passed). No skip or xfail added; the synthetic parity gate (81/51/49) is
  green and the three pinned files are untouched. New: `tests/test_capabilities_api.py`
  (43) and `tests/channel/` (189: auth matrix, pipeline, ledger and `verify_figures`,
  MCP, config, ping, architecture, and 14 against the REAL API in-process).
- Standard gate: `check-whitelabel.ps1 -Enforce` 0 enforced (29 allow-listed);
  `audit-export.py --enforce` 0 findings; `gitleaks git` no leaks (two rounds of
  false positives on `idempotency_key="..."` literals in tests were rewritten, not
  allow-listed). The standards ratchet was TIGHTENED (483 baseline violations;
  `application/wiring.py` 605 -> 471).
- Routes: `tests/route_inventory.json` +2 (`GET /api/capabilities`,
  `POST /api/capabilities/{tool}`); new `tests/channel_route_inventory.json` pins the
  gateway's eight routes. `infra/` untouched in these two WPs.
- Existing tests edited (D-64): three that pinned `claim_package_create` and
  `verify_figures` as unbuilt.
- New runtime pin: `jsonschema==4.26.0`. The `mcp` SDK is deliberately not used (D-65).
- Gateway routes: `GET /channel/health`, `GET /channel/ready`, `GET /channel/v1/tools`,
  `POST /channel/v1/tools/{tool}`, `GET /channel/v1/downloads/{ticket}`, `POST|GET|DELETE
  /mcp`.

### CH-07 (merged `ed36927`)

- Full backend suite: **2385 passed, 136 skipped, 1 xfailed** (CH-06b: 2360 passed). New:
  `tests/test_channel_infra.py` (26). No skip or xfail added; pins untouched.
- Terraform (`infra/`): `terraform fmt -check -recursive` clean, `terraform init
  -backend=false` and `validate` clean, `tflint --recursive` exit 0, `terraform test`
  **43 passed, 0 failed** (baseline 30; 13 new in `tests/channel.tftest.hcl`, no existing
  test edited).
- Plan summary (mock providers, `public` profile): toggle **off** — channel module creates
  **0** resources, outputs empty, API restriction `Deny` + `web-app-subnet` only. Toggle
  **on** — exactly **4** resources added (`azurerm_user_assigned_identity`,
  `azurerm_linux_web_app`, `azurerm_role_assignment` for Monitoring Metrics Publisher,
  `azurerm_monitor_diagnostic_setting`); API restriction identical. `enterprise` with the
  toggle off: unchanged; with it on: refused. A real `terraform plan` against Azure was
  **not** run (D-70).
- Docs: CONNECTIVITY-MATRIX §1a (CH1-CH9 plus an identity/role table), component spec §4.7a,
  ENV-VARS §9a, SECURITY posture rows, RUNBOOK §13, DEPLOYMENT-HANDOVER values, C4 model
  (`c4arch.py validate`: 0 errors, 0 warnings; `build` regenerated the HTML, no raster images).
  `scripts/check-links.py` 0 broken.
- Standard gate: whitelabel 0 enforced; audit-export 0 findings; gitleaks clean.

### CH-07b (merged `47a8741`)

- Full backend suite: **2400 passed**, 136 skipped, 1 xfailed (CH-07: 2385). `terraform fmt/validate/tflint` clean, `terraform test` 43 passed. Whitelabel 0 enforced, audit-export 0, gitleaks clean, links 0 broken.
- `azure.yaml` services are `api` and `web` only (tested); `scripts/deploy-channel.ps1` runs from a `postdeploy` hook and `deploy.yml`; with the toggle off it exits 0 (tested by running it against a stubbed `az`). Edited assertions are listed in D-73.

### CH-08 (merged `063afec`)

- Full backend suite: **2569 passed**, 136 skipped, 1 xfailed (CH-07b: 2400). New: `tests/channel_orchestrator/` (160: 49 golden conversations in `golden/*.json`, the exactness property over four narrator behaviours, identity, runner, MAF, model adapters against the mock gateway, host, structure rules, vendoring, and 4 end-to-end tests against the REAL gateway and API) and `tests/channel/test_gw_narration.py` (6). No skip or xfail added; parity pins untouched; `tests/channel_route_inventory.json` gained `POST /channel/v1/audit/narration` (the gateway now serves 9 routes). One existing allow-list line was added to `test_gw_architecture.py` (`application.agent_audit`, with its reason).
- `infra/` untouched, so no Terraform checks (D-79: no container registry). Whitelabel 0 enforced; audit-export 0; `gitleaks git` clean (one allow-list entry for the generated vendor manifest's SHA-256 digests); links 0 broken; coding-standards ratchet green with no baseline change.
- The real Responses host (`azure-ai-agentserver-responses` 2.4.0) was driven in-process (`/readiness`, `POST /responses`, `/whoami`). Docker: stages up to `pip install` build and the later stages were checked without it; `pip install` in the build could not complete here (TLS interception on the egress), so the image was not built end to end (D-79).
- Not verified live, by design (Prompt 6): which identity signal Teams and Copilot Chat carry; whether the hosted agent reaches the gateway and the model from the private project (D-78); `azd ai agent` accepting `channel_orchestrator/azure.yaml`; Foundry-account `/openai/v1` access for the agent's identity (D-75).

## Blockers

_None._
