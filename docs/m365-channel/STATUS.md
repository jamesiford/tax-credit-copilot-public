# Microsoft 365 channel — status

Customer-neutral. This file is the only memory a resumed session has; keep it
truthful. Decisions live in [DECISIONS.md](DECISIONS.md).

Integration branch: `jamesiford-m365-capability-layer` (see D-01 — this session
runs in a worktree, so `feat/m365-channel` is held by the main checkout). Prompt 6 (CH-13)
ran on `jamesiford-m365-channel-live-deploy`, fast-forwarded to the tip of `feat/m365-channel` first (D-95).

**Blocked-soft work packages from Prompts 1–5: none.** AI-05 (conversation continuity) remains the deliberate stretch deferral (D-60); nothing deployed depends on it.

**Where things stand (3 November 2026).** Everything the offline stages set out to build is merged on `feat/m365-channel`:
**Stage 1 (CH-15, demo polish)** — display names from Graph, the agent icon, narration quality, the portal's evidence stream and the
known-issue fixes — and **Stage 2 (CH-16, governed data access)** — the semantic model, validated specifications and SQL building,
the three execution adapters with their limits, the `data_catalog` / `data_query` / `data_distinct_values` tools with the two output
lanes, the planner, narrator and Cowork changes, the goldens and equivalence tests, and (CH-16f) the documentation, the Terraform/azd
mapping and the lakehouse-endpoint grants. No work package is blocked. All of it is verified **offline only**; the live redeploy
(Stage 3, CH-17) is the first time any of it meets Fabric, a real model, Teams or Cowork, and the "unverified offline" lines under
each work package below are its checklist. Nothing has been pushed.

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
| CH-08b | Orchestrator gaps found re-reading the brief (D-85) | done | `wp/CH-08b-spec-gaps` | merge `4221270` |
| CH-09 | `scripts/publish-m365.ps1` | done | `wp/CH-09-publish-m365` | merge `3285ade` |
| CH-10 | Cowork plugin (`channels/cowork/`), builder and offline validator | done | `wp/CH-10-cowork-plugin` | merge `e93ed3d` |
| CH-11 | End-to-end workflow and exactness tests | done | `wp/CH-11-workflow-tests` | merge `f33ffa4` |
| CH-12 | Documentation, ADR-009, runbook, demo script | done | `wp/CH-12-documentation` | merge `b470494` |
| CH-12b | Demo network posture toggle and hardening plan | done | `wp/CH-12b-demo-posture` | merge `0bda7b9` |
| CH-13 | Live deployment, spikes, smoke tests and hand-off (Prompt 6) | done with open items (see Blockers) | `wp/CH-13-live-deploy` | merge `fec797d` |
| CH-14 | Hosted-agent model access (M-01), the silent Teams chat, claim_not_found, deploy health wait, live AI checks (Prompt 7) | done with open items (Teams proof is the owner's; see Blockers) | `wp/CH-14-model-access` | merge `b8ce56e` |
| CH-15e | Known issues from the live run: shared Graph client with stale-token refresh, exact-name `client_resolve`, typed-error goldens, debug-switch posture and DEMO-CLEANUP (Prompt 8, item 5) | done (live behaviour of the token refresh unverified) | `wp/CH-15e-known-issues` | merge `c06c63c` |
| CH-15a | Resolve display names from Microsoft Graph (Prompt 8, item 1): port, adapter on the shared Graph client, gateway agent-caller step, `CHANNEL_RESOLVE_DISPLAY_NAMES` / `channel_resolve_display_names` / `TCC_CHANNEL_RESOLVE_DISPLAY_NAMES`, `-GrantUserReadBasic` | done offline (live role, Graph and token-refresh behaviour unverified) | `wp/CH-15a-display-names` | merge `dc03820` |
| CH-15b | The agent icon (Prompt 8, item 2): SVG sources in `channels/branding/`, `scripts/render-icons.py` (Chromium here; cairosvg preferred where Cairo exists), `publish-m365.ps1 -ColorIconPath/-OutlineIconPath`, Cowork build on the rendered icons, no republish | done offline (no live republish; the next publish is 1.0.3 with the icons) | `wp/CH-15b-agent-icon` | merge `9b743df` |

| CH-15c | Narration quality (Prompt 8, item 3): narrator prompt v2 with six worked examples, `composer_hedging` (a qualifier within three tokens of a figure drops the narration), planner prompt and tool descriptions that separate the whole book from one client, planning goldens, routing and narration evals with must-contain and forbidden patterns | done offline (live model behaviour unverified) | `wp/CH-15c-narration` | merge `acfc4c4` |
| CH-15d | The portal chat emits `evidence` for the Ask workspace (Prompt 8, item 4): `tap` + `with_evidence` build one additive event per capability from its `ToolResult`, sensitive rows only for a signed-in principal, `confirmation` inert, golden file shared with the frontend, mock API serves a real-shape chat stream | done offline (live stream with a real model unverified) | `wp/CH-15d-portal-evidence` | merge `d12d3e0` |
| CH-16a | The governed data semantic model (Prompt 9): `application/data/semantic_model.py` + `model_*.py` (11 datasets, 4 employee-level), drift test against the DDL and source schema with reasoned exclusions, generated `docs/data/SEMANTIC-MODEL.md` | done offline | `wp/CH-16a-semantic-model` | merge `9992238` |
| CH-16b | Query specification, validation and SQL building (Prompt 9): frozen stdlib `QuerySpec` + JSON Schema, `validate()` with typed errors, `build_sql()` for T-SQL and SQLite (tenant marker first, every value bound), audience classifier; `{tenant:alias@AccountId}` marker | done offline | `wp/CH-16b-spec-sql` | merge `3149b1f` |
| CH-16c | Execution adapters, limits and provenance (Prompt 9): `DataQueryExecutor` port, Warehouse / Lakehouse SQL endpoint / SQLite adapters, timeout + row cap + per-user budget + bulkhead, provenance on every result, `application/data_wiring.py` | done offline | `wp/CH-16c-executors` | merge `0a63846` |
| CH-16d | The capabilities (Prompt 9): `data_catalog`, `data_query`, `data_distinct_values` (catalog, API registry, gateway/MCP list read-only, `sensitive` flag, audit line), the two lanes (`Block.audience`, `user_only_facts`, `lanes.py`, orchestrator projection), Cowork refuses employee-level rows unless a writer | done offline | `wp/CH-16d-data-capabilities` | merge `efd3f70` |
| CH-16e | Making the agent use it well (Prompt 9): planner and JSON-plan decision rule, data tool descriptions, JSON mode reads a lookup before it plans, narrator prompt v3 (six data examples), Cowork "go deeper" step + questions table + shared data rules, 29 goldens (`golden/data_use.json`), `data_routing` AI eval (34 plans) + 15 `nar-data-*` rows, equivalence tests on the real engine's Gold output | done offline (live model behaviour unverified) | `wp/CH-16e-agent-use` | merge `e85afd4` |
| CH-16f | Docs, security and the Fabric-agent evaluation (Prompt 9): `DATA-ACCESS.md` (design, lanes, limits, audit, what is and is not queryable, how to add a dataset, operations, grants, the Fabric Data Agent recommendation: off), ADR-009 / SECURITY / KNOWN-LIMITATIONS / ENV-VARS / CONNECTIVITY-MATRIX / DEPLOYMENT-HANDOVER updated, optional non-secret `DATA_QUERY_*` / `LAKEHOUSE_SQL_*` API settings in Terraform and azd (default plan unchanged), read-only lakehouse-endpoint grants for the API identity in `grant-warehouse-sql.py --profile lakehouse` and postprovision | done offline (the live endpoint grant and read are unverified) | `wp/CH-16f-data-docs-grants` | merge `ed2fbb6` |
| CH-17a | Live redeploy, part A (Prompt 10, 3.1 to 3.3): baseline recorded, new azd values and provision (no drift afterwards), lakehouse-endpoint grants, API, web, gateway and orchestrator (agent version 17) deployed, agent invariants 13/13 | done (publish, Cowork package and the full live verification are 3.4 to 3.6) | eat/m365-channel | see MASTER-STATUS |
| CH-17b | Live redeploy, part B (3.4 and 3.5): icons rendered, app **1.0.3 published at scope Shared**, one package to install (`publish-appPackage-v1.0.3.zip`), Cowork zip v2 built with `--strict` (plugin version 1.0.1), agent invariants 13/13 after the publish | done | feat/m365-channel | see MASTER-STATUS |
| CH-17c | Live verification (3.6, parts C1 and C2): gateway smoke 41/41 and data tools 99/99 against three reads; one bug found and fixed (`data_distinct_values` counted rows); orchestrator end to end, ten questions (8 answered well, 1 honest non-answer, 1 partly answered with the narration correctly withheld) with **two fix cycles** (rounding words, repeated calls, planner rules, framework stop message, narrator prompt v4, tool budget 8) and a model-capacity raise 20 to 100; display names and UPN resolved on every `teams` and `cowork` audit row, writes attributed to the UPN; evidence stream passes the contract (in process: Kudu has no SQL driver); Application Insights: **no** sensitive content (counts 0), GenAI spans not exported; F2 Active, mock gateway unchanged, Foundry demo posture recorded; final agent version **20**, invariants **13/13**; backend 4957 passed / 136 skipped / 1 xfailed | done (non-writer refusal over Teams and GenAI spans not observed live; see KNOWN-LIMITATIONS) | feat/m365-channel | [live-final-2026-11-03.md](evidence/live-final-2026-11-03.md) |

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

### CH-08b (merged `4221270`)

- Full backend suite: **2593 passed**, 136 skipped, 1 xfailed. A re-read of the brief found: numbered `1) Name` candidates, a stated drop of a superseded preview, the claim-package link after commit, a turn deadline, plain mappings for 401/403/429/timeout, a span per gateway call, `/whoami` fields, `conversation_id` in the report, a what-if's numbers and a base year being the reader's, and golden coverage for every write flow with a per-answer numeral check (D-85).

### CH-09 (merged `3285ade`)

- Full backend suite: **2615 passed**, 136 skipped, 1 xfailed (CH-08b: 2593). New: `tests/test_publish_m365.py` (22; needs `pwsh`, skipped without it) over `tests/publish_shim.py`, a programmable fake `az`. No skip or xfail added; pins untouched.
- Asserted on the requests the script makes: the sequence, the bot and channel bodies, the merged PATCH (existing protocols and unknown schemes survive; nothing configured gets `responses` + `activity`), the publish and package bodies, scope → scheme, the tenant guard (no request at all without `-ConfirmTenantPublish`), the provider check (prints the command, calls nothing else, never registers), the version bump, "no titleId is not success", `-WhatIf` (reads, never writes), and that no token appears in any call.
- `docs/m365-channel/evidence/publish-whatif.txt`: the `-WhatIf` transcript, placeholders only (a test pins that). `PUBLISHING.md` written. `infra/` untouched. Whitelabel 0 enforced; audit-export 0; `gitleaks git` clean; links 0 broken.
- Not run against a live subscription (Prompt 6). Decisions: D-84.

### CH-10 (merged `e93ed3d`)

- Full backend suite: **2686 passed**, 136 skipped, 1 xfailed (CH-09: 2615 passed). New: `tests/channel/test_cowork_package.py` (67) and `tests/channel/test_gw_render.py` (4). No skip or xfail added; parity pins untouched; `infra/` untouched.
- `python scripts/build-cowork-plugin.py --config channels/cowork/config.example.json`: builds offline, 13 files, reproducible (two builds, same bytes). Placeholder-config SHA-256 at merge `972fd949ccaed5a6fe996f58be4856c3577909bfee9d0c44c5ace816583ef663`; after CH-11 reworded two skill steps (the `client_resolve` confirmation) it is `da3a96072bf5464a6971ac4de158da9166de92954ce4fac7e17d611bfdea73e6` (app id from the default seed); `--strict` refuses it with exit 1. The manifest also validates (0 errors) against the published 1.29 JSON schema; `atk package` 1.1.14 builds the tree in a throwaway Agents Toolkit project. `wiqd` was not installed and `atk validate` needs sign-in (D-87).
- Gateway change (D-88): the MCP text carries a `Provenance:` line so a footer is copied, not invented.
- Whitelabel 0 enforced; audit-export 0; `gitleaks git` clean; links 0 broken.
### CH-11 (merged `f33ffa4`)

- Full backend suite: **2765 passed**, 136 skipped, 1 xfailed (CH-10: 2686). New: `tests/channel/test_workflows.py` (38), `test_workflows_audit.py` (16), `test_workflows_chaos.py` (25) over `workflow_harness.py`: the gateway in front of the REAL API app and capability layer (Entra on, SQLite stores, the synthetic book, findings detection over the committed synthetic payroll), driven as the orchestrator (REST, app-only token acting for a person) and as Cowork (MCP, the person's own token). No skip or xfail added; parity pins untouched; `infra/` untouched.
- W1 and W2 run as scripts of tool calls on both surfaces; a document built only from returned blocks verifies, every one-figure mutation of it is rejected; a writer's changes are two steps, land once, are attributed and audited with the commit's `confirmation_ref` equal to its preview's; a reader is refused every commit and nothing is written. Per-user audit separation through `GET /api/audit/channel` and `scripts/channel-audit.py`; ten reads agree across REST, MCP, the API capability endpoint and the direct call (and four against the portal's own endpoints). Chaos: API timeout and broken road, rate limit, oversized body, replayed/tampered/wrong-user/expired confirmation, a writer revoked mid-conversation. A corrupted capability is caught by the envelope scan and by `verify_figures` end to end.
- Two findings, both recorded as limits rather than fixed: `client_resolve` asks even for one exact name when no client is selected (the skills now confirm and call again with `current_client_id`); the figure guard compares values, so a wrong figure equal to another real figure in the conversation is not seen (pinned by `test_known_limit_*`).
- Whitelabel 0 enforced; audit-export 0; `gitleaks git` clean.
### CH-12b (merged `0bda7b9`)

- Full backend suite: **2765 passed**, 136 skipped, 1 xfailed (unchanged: no Python added). Terraform: `terraform fmt -check -recursive` clean, `init -backend=false` and `validate` clean, `tflint --recursive` exit 0, `terraform test` **57 passed, 0 failed** (baseline 43; 14 new in `tests/foundry_network.tftest.hcl` and `tests/foundry_network_enterprise.tftest.hcl`, no existing test edited). A mutation (the any-address rule made always true) was shown to fail its test.
- `foundry_public_network_access` (default `false`), `foundry_allowed_ip_ranges` and `foundry_allow_any_ip`; azd values `TCC_FOUNDRY_PUBLIC_NETWORK_ACCESS` and `TCC_FOUNDRY_ALLOWED_IP_RANGES`. Default: the account body is byte for byte what it was (asserted through the module's `network_settings` output) and the check resource has `count` 0, so the default plan gains nothing. On: only `publicNetworkAccess` and `networkAcls` differ, local auth stays off, the private endpoint stays; output `network_posture` and a plan warning. Refused: enterprise, customer data, a malformed or `/31` range, any `/0` without the second switch, ranges without the toggle (D-93).
- Docs: `docs/architecture/HARDENING-PLAN.md`, `docs/m365-channel/HARDENING-SPIKE.md` (spike S6, runnable), `SECURITY.md` posture row, CONNECTIVITY-MATRIX §4a, DEPLOYMENT-HANDOVER and ENV-VARS rows, RUNBOOK §13.5, `docs/README.md`. **D-78 is corrected** (D-92) in DECISIONS and ORCHESTRATOR.md: the "standard agent setup" is the classic path; the hosted-agent path is per the documentation, unproven until S6; Cosmos DB is ruled out.
- Whitelabel 0 enforced; audit-export 0; `gitleaks git` clean. No Azure resource was created or changed.
### CH-12 (merged `b470494`)

- Full backend suite: **2765 passed**, 136 skipped, 1 xfailed (no Python changed). `scripts/check-links.py` 80 files, 0 broken; whitelabel 0 enforced; audit-export 0; `gitleaks git` clean.
- Written: `docs/m365-channel/README.md` (architecture, who can do what, the two data flows as Mermaid, the audit model, orchestrator versus Cowork), `DEMO-SCRIPT.md` (Teams, Copilot Chat, Cowork, the per-user audit, an 18-line manual checklist; synthetic clients only), `KNOWN-LIMITATIONS.md`; `docs/architecture/ADR-009-m365-channel.md`; ADR-008 finalised as built (`verify_figures`, the provenance line, two limits found by CH-11); RUNBOOK §13.6-13.9 (writers, paused capacity, a failed publish, a guard-rejection spike); SECURITY.md Cowork row; TARGET-ARCHITECTURE gap analysis; root README "Channels"; `docs/README.md` links; COWORK-SETUP forward links resolved. Order of CH-12 and CH-12b: D-94.
### CH-13 (live deployment, Prompt 6)

- Backend suite: **2767 passed**, 136 skipped, 1 xfailed (CH-12: 2765; two new tests in `test_postprovision_guards.py`; one test narrowed, see D-96). No skip or xfail added; parity pins untouched; the synthetic parity gate is green. Terraform: `fmt -check`, `validate`, `tflint` clean, `terraform test` **61 passed** (57 at CH-12b; four new, one assertion updated for the mock's port) with the local overlay moved aside. Whitelabel 0 enforced; audit-export 0; `gitleaks git` no leaks; links 0 broken; a search of tracked files for every real identifier used in this run found none.
- Deployed to the sandbox (public profile, synthetic classification, channel on, `AUTH_MODE=entra`, existing Fabric workspace reused, not created). `azd up`: 46 resources; migrations 0001 and 0002 applied, **0 pending afterwards**; `terraform plan` (via `azd provision --preview`): **No changes**. Web 302 to sign-in; direct API 403; gateway `/channel/health` 200, `/channel/ready` ready, `/channel/v1/tools` 401 without a token.
- Certified figures on the deployed Warehouse via `backend/tools/check_certified_live.py`: **10,236 / 539 / 656, reproduce**.
- Live smoke ([evidence/live-smoke-2026-11-03.md](evidence/live-smoke-2026-11-03.md)): **44 passed, 0 failed** across three runs (41 main + 2 non-writer + 1 limits), plus an honest SKIP each for `finding_resolve` and the 429. Facts from the gateway were identical to the in-process engine over the same Warehouse for every read tool on two clients. Audit: 659 rows, all `cowork`/`delegated`, no payroll content.
- Entra: web redirect URI and federated credential; `TCC.Agent` to the gateway identity; `Channel.Invoke` to the agent identity; Graph `GroupMember.Read.All` to the gateway and API identities. No admin action is outstanding.
- Hosted agent: deployed with `azd ai agent` (active version 7, selector `@latest`), published with scope `Shared`; the endpoint reads `activity` and `responses` with a Bot Service scheme. **Nothing was sent from Teams.**
- Scripts added: `assign-channel-roles.ps1`, `channel-live-smoke.py`, `channel-smoke.ps1`, `poc-pause.ps1`; `channel-audit.py --detail`; `OPERATIONS.md`.

| Spike | Question | Outcome |
| --- | --- | --- |
| S1 | What identity signal does a Teams message carry? | **Needs a person** (checklist item 1) |
| S2 | Does the sender's display name arrive? | **Needs a person** (same message) |
| S3 | Can the hosted agent reach the gateway, and by which rule? | **Answered**: yes; authorised by the `Channel.Invoke` role; egress is the public internet. A direct call carries no identity (nothing runs), and `x-ms-user-identity` is refused unless delegation is authorised |
| S4 | Does `azd ai agent` accept the orchestrator project? | **Answered**: after the schema fix (D-99), and it creates the Bot resource too |
| S5 | Cowork end to end | **Needs a person** (OAuth client registration, install, W1 and W2) |
| M-01 | Can the hosted agent reach the Foundry model endpoint? (named S6 in Prompt 6; S6 is the hardening spike) | **Fixed in CH-14**: DNS, not a firewall; see D-101 |

### CH-13 merge

Merged `--no-ff` into the session integration branch `jamesiford-m365-channel-live-deploy` as `fec797d`; `feat/m365-channel` itself is left for the owner to fast-forward.

1. **Spikes S1, S2 and S5 need people.** Nothing can send a Teams message or sign into Cowork. The manual checklist is the appendix of [DEMO-SCRIPT](DEMO-SCRIPT.md); `scripts/channel-smoke.ps1 -Since <time>` prints what the platform received.
2. **M-01 (model access) is fixed**; the silent Teams chat (container-level `activity`) is fixed (D-100). Both are verified only up to the agent definition and a direct call; the Teams proof is the owner's retry (DEMO-SCRIPT, "Retry in Teams").
3. **A group-only writer is refused by the API** until its Graph token cache turns over (about a day after 3 Nov 2026); the operator is on the allow-list as well. Not an admin action: every role this prompt allowed was granted.
4. **The live external model gateway test is pending the customer's real endpoint.** The mock was deployed and checked from inside the network; the API's narration through it, the forced fallbacks in both orders, the `api_key` and `oauth_client_credentials` modes, and the spans in Application Insights were **not** exercised live (the API is reachable only through the signed-in portal). See CH-13 evidence.
5. `finding_resolve` was not exercised live (no open finding exists); the 429 rate limit was not reachable live (proven offline).

### CH-15e (merged `c06c63c`)

Prompt 8, item 5 (known issues). Offline; no `az`, `azd`, Graph or live calls.

- **Graph client (D-104).** `infrastructure/auth/graph_client.py`: `GraphClient` and `GraphTokenProvider`; a 401 or a 403 `Authorization_RequestDenied` invalidates the cached token and retries once (60 s cool-down); `EntraGroupEntitlement` refactored onto it with fail-closed unchanged and no existing test edited. CH-15a reuses `GraphClient.request`. Tests: `tests/test_graph_client.py` (403 then 200 after refresh, 401, persistent denial, cool-down, plain-callable provider, claims fallback).
- **`client_resolve` (D-105).** One exact full name or alias resolves (`facts.resolved`), a full name beats a shared first-word alias, partial and ambiguous text still ask, portal `strict` and `chat_scope` untouched. Cowork skills updated; `tests/test_client_resolve_channel.py`; orchestrator goldens `golden/known_issues.json` (exact name, "their", typed `claim_transition_prepare` errors in plain words). One existing test helper edited (`test_workflows.resolve`, it asserted the removed limitation).
- **Debug switch (D-106).** Defaults already false everywhere; startup WARNING in gateway and orchestrator; `DEMO-CLEANUP.md`; pinned by `tests/channel/test_gw_debug_posture.py` and `tests/channel_orchestrator/test_orch_debug_posture.py`.
- **Gate.** Backend `pytest tests/ -q` on the merged tree: **2866 passed, 136 skipped, 1 xfailed** (baseline 2817/136/1; the skip count is unchanged). Code-standards ratchet green, baseline tightened by two entries (`client_resolve`), none added. `check-whitelabel.ps1 -Enforce`: 0 enforced; `audit-export.py --enforce`: 0 findings; `gitleaks` on the branch commits: no leaks; no raster file tracked. Infrastructure, routes and frontend untouched, so Terraform, the route inventory and the frontend gates were not run. Parity pins untouched.
- **Unverified offline.** That the App Service managed-identity endpoint honours the cache bypass (needs the live redeploy; see KNOWN-LIMITATIONS).

### CH-15a (merged `dc03820`)

Prompt 8, item 1 (display names). Offline; no `az`, `azd`, Graph or live calls.

- **Port and adapter (D-107).** `application/display_names.py`; `infrastructure/auth/graph_people.py` over `GraphClient`/`GraphTokenProvider` (2 s timeout, 24 h / 5 min cache, bounded, single-flight, fail-soft, oid-only warnings).
- **Gateway.** `channel/people.py` names an agent caller whose name is missing or `(name not provided)` in `run_tool`, narration audit and MCP `tools/call`; Cowork never reaches Graph. Composed in `application/channel_wiring.py` (re-exported by `wiring.py`).
- **Configuration.** `CHANNEL_RESOLVE_DISPLAY_NAMES` (default false); Terraform `channel_resolve_display_names` (default false, one setting only when true); azd `TCC_CHANNEL_RESOLVE_DISPLAY_NAMES` in `infra/main.tfvars.json`; ENV-VARS, DEPLOYMENT-HANDOVER, OPERATIONS, SECURITY updated. `assign-channel-roles.ps1 -GrantUserReadBasic` (idempotent; admin action).
- **Gate.** Backend `pytest tests/ -q`: **2932 passed, 136 skipped, 1 xfailed** (was 2866/136/1; +66 new: 35 adapter, 19 gateway, 7 role-script, 5 other contract tests picked up by the new setting and files). Code-standards ratchet green, no baseline change. `check-whitelabel.ps1 -Enforce` 0 enforced; `audit-export.py --enforce` 0 findings; `terraform fmt -check -recursive`, `init -backend=false`, `validate`, `tflint --recursive` clean; `terraform test` 63 passed; gitleaks on the branch commits: no leaks.
- **Unverified.** The role grant, the Graph call and the token refresh on the live platform (the redeploy's job). Live settings to set: `TCC_CHANNEL_RESOLVE_DISPLAY_NAMES=true` (then `azd provision`) after an administrator runs `assign-channel-roles.ps1 -GrantUserReadBasic`.

### CH-15b (merged `9b743df`)

Prompt 8, item 2 (the agent icon). Offline; no `az`, `azd` or live calls, and **no republish**.

- **Assets (D-108).** `channels/branding/agent-icon.svg` (192x192) and `agent-icon-outline.svg` (32x32), customer-neutral, SVG only; the old placeholder SVGs under `channels/cowork/assets/` are removed. `frontend/public/brand-mark.svg` unchanged; `docs/m365-channel/README.md` links the icon by a relative path.
- **Renderer (D-108).** `scripts/render-icons.py` over `scripts/branding_icons/` (`cairosvg` first, Playwright Chromium otherwise; `scripts/requirements-icons.txt`, dev-only, not in `backend/requirements.txt`). Output `dist/branding/color-192.png`, `outline-32.png` (and `--preview` 512), gitignored. cairosvg could not load the Cairo DLL here, so Chromium rendered them; checked against the owner's preview PNGs.
- **Publish.** `publish-m365.ps1 -ColorIconPath/-OutlineIconPath` (default the rendered files when present) send `colorIconBase64` / `outlineIconBase64` in the publish body and the package request after checking the PNG signature, 192x192 / 32x32 and RGBA for the outline; base64 never printed (`-WhatIf` shows lengths); `-DeveloperName` is limited to 32 characters; version auto-increment kept (next publish `-AppVersion 1.0.3`). The `-WhatIf` evidence transcript regenerated.
- **Cowork build.** Uses the rendered icons (`TCC-I001` when none and no renderer), writes `dist/tcc-cowork-plugin.build.json` with the zip, icon and file hashes; `accent_color` default matches the tile.
- **Gate.** Backend `pytest tests/ -q` on the branch: **2970 passed, 136 skipped, 1 xfailed** (was 2932/136/1; the skip count is unchanged, and the renderer tests ran with Chromium). New: `tests/channel/test_agent_icon.py`, `tests/test_publish_m365_icons.py`. Code-standards ratchet green, no baseline change. `check-whitelabel.ps1 -Enforce` 0 enforced; `audit-export.py --enforce` 0 findings; `check-links.py` 0 broken; gitleaks on the branch commits: no leaks; no raster tracked (tested). Infrastructure, routes and frontend untouched, so Terraform, the route inventory and the frontend gates were not run. Parity pins untouched.
- **Live redeploy must.** `python scripts/render-icons.py`; `publish-m365.ps1 ... -AppVersion 1.0.3` (icons default to `dist/branding/`, or pass `-ColorIconPath`/`-OutlineIconPath`); rebuild the Cowork zip (`build-cowork-plugin.py`, icons are inside it) and re-upload; in Teams remove the old app and add the new package so the icon refreshes.

### CH-15c (merged `acfc4c4`)

Prompt 8, item 3 (narration quality). Offline; no `az`, `azd`, Graph or live calls.

- **Narrator prompt (D-109).** `channel_narrator.md` version 2 (manifest records 1 and 2): senior-colleague voice, answer first, engine labels verbatim, no rank prose, no hedging, copy the placeholder exactly, six worked examples; `tests/test_channel_narrator_prompt.py` composes every example through the real composer.
- **Hedging guard (D-109).** `application/composer_hedging.py`, wired into `composer._narrate`; vendored with the other `composer_*` modules. `tests/test_composer_hedging.py` is table-driven (24 hedged and 10 clean phrasings, the three-token window, negations rejected, degradation to the engine's own answer).
- **Planner (D-109).** Catalog descriptions (`book_rank` whole-book only; client tools "ONE client (needs a client)"), planner and JSON-plan prompts; `golden/planning.json` (10 cases) and `test_orch_planning.py`.
- **Evals.** `routing.jsonl` +8 offline +2 live-only rows with `forbidden`; `narration.jsonl` +14 rows through the composer with `must_contain` and forbidden wording; `test_narration_wording_eval.py` proves the new rows can fail. Offline thresholds unchanged at 1.0.
- **Existing tests edited (two, narrowly).** `test_channel_narrator.py` no-digit test ignores a list index inside a fact path; `test_orch_e2e.py` pinned `7+prompt1`, now `7+prompt2`.
- **Gate.** Backend `pytest tests/ -q` on the branch: **3067 passed, 136 skipped, 1 xfailed** (was 2970/136/1; +97; skip count unchanged). Code-standards ratchet green, no baseline entries added. `prompt-manifest.py` agrees; `vendor-orchestrator.py --check` matches; `check-whitelabel.ps1 -Enforce` 0 enforced; `audit-export.py --enforce` 0 findings; `check-links.py` 0 broken; gitleaks on the branch commits: no leaks. Infrastructure, routes and frontend untouched. Parity pins untouched.
- **Unverified offline.** How a live model follows the new prompt, and whether it still picks `book_rank` for a client question (the redeploy must re-run `scripts/live-ai-checks.py`). The orchestrator's vendored copy is gitignored: `python scripts/vendor-orchestrator.py` before `azd deploy`.

### CH-15d (merged `d12d3e0`)

Prompt 8, item 4 (the portal chat emits evidence). Offline; no `az`, `azd`, Graph or live calls.

- **Backend (D-110).** `api/chat/evidence.py` shapes a capability's `ToolResult` into a contract item (text and rows verbatim, headings become block titles, warnings become `Note` callouts, provenance limited to the contract's keys); `api/chat/evidence_tap.py` holds `tap()` and `with_evidence()`. Pipelines pass the result through `tap(...)` (no function grew); `_run_intent` wraps each pipeline, so an `evidence` event precedes the next frame after a capability ran and always precedes `done`. Every existing event and field is unchanged. Sensitive capabilities (and any tool the catalog does not know) withhold table rows unless `principal.authenticated` (new `_AUTHENTICATED` ContextVar, default False); the count is kept. `confirmation` stays inert and the contract doc's new Status section says so.
- **Frontend.** No component changed. `src/lib/askBackendShape.json` (golden, two real items) is compared to the backend's output in `test_chat_evidence.py` and read through the real `streamChat` reader in `components/ask/AskWorkspace.backend.test.jsx`. `api.js` comment corrected.
- **Tooling.** `frontend/tools/mock_api.py` answers `POST /api/chat` with a stream in the backend's framing built from the golden file; `check_a11y.py` scans the open workspace for the dev fixture AND the real shape and fails if the real shape draws no evidence tab.
- **Gate.** Backend `pytest tests/ -q`: **3088 passed, 136 skipped, 1 xfailed** (was 3067/136/1; +21 in `tests/test_chat_evidence.py`; skip count unchanged). Frontend `npx vitest run`: **929 passed** (was 923; +6), `npm run build` green. `python frontend/tools/check_all.py` with the mock API on :8000 forwarding to a real backend on :8001 (`DATA_SOURCE=csv`, boots here) and Vite on :5173: 21 of 22 rows pass (tests, build, tokens, metrics, type floor, visible rows at baseline 7/13/17, brand, contrast, cell fit, table width, filters, forced states 37/0, a11y 0 serious/critical across fixture and real-shape workspace scans, sweep at baseline, whitelabel, export audit); the 22nd, the all-tree gitleaks row, reports 63 findings in untracked or ignored working-tree files that pre-date this WP, while `gitleaks git --log-opts=feat/m365-channel..HEAD` on this branch's commits finds none. (A first run without the :8001 backend failed the data-dependent rows because the mock forwards `/api/scope` upstream; that is the tool's documented prerequisite, not a code failure.) Code-standards ratchet green with no baseline entry (`dispatch._dispatch`, `_pipeline_eligibility`, `_pipeline_portfolio` and `_pipeline_simulate` did not grow). `check-whitelabel.ps1 -Enforce` 0 enforced; `audit-export.py --enforce` 0 findings. Routes untouched (no inventory change); Terraform untouched; parity pins untouched.
- **Unverified offline.** A live stream with a real model (Foundry) emitting evidence, and the evidence for `eligibility`, `trend`, `at_risk` and `simulate` against real Gold data: tests build their results from synthetic envelopes and the real `book_rank`. `eligibility`/`trend` blocks are platform-rendered by the same capabilities the channel already ships, so the shape is the same.

### CH-16a (merged `9992238`)

Prompt 9, semantic model. Offline; no `az`, `azd` or live calls.

- **Model (D-111).** `application/data/` (standard library only): `semantic_model.py` (types, validation at construction, `default_model()`), `model_dsl.py` (shared column defaults), `model_gold_facts.py`, `model_gold_units.py`, `model_gold_credit.py`, `model_source.py`, `model_excluded.py`. Datasets: `employee_period_fact`, `employee_eligibility`, `onezero_matrix`, `payroll` (employee level); `unit_month_summary`, `run_method_summary`, `run_manifest`, `unit_year_master`, `unit_credit_installment`, `location`, `pay_code`.
- **Drift test.** `tests/test_semantic_model_drift.py` parses the Warehouse bootstrap and every migration (`tests/ddl_schema.py`) and reads `data/source/to_delta.TABLE_SPECS`: every column is modelled, blocked or excluded with a reason; every table is modelled or on `model_excluded.py`; a crafted extra column fails it.
- **Docs.** `docs/data/SEMANTIC-MODEL.md` is generated (`scripts/generate-semantic-model-doc.py`, `--check`); `tests/test_semantic_model_doc.py` fails if it is stale.
- **Gate.** Backend `pytest tests/ -q`: **3161 passed, 136 skipped, 1 xfailed** (was 3088/136/1; +73, skip count unchanged). `check-whitelabel.ps1 -Enforce` 0 enforced, `audit-export.py --enforce` 0 findings, gitleaks (git history) no leaks, code-standards ratchet green with no baseline change. The ratchet skips any path containing `data/`, so `tests/test_data_access_standards.py` applies the same measurement to `application/data/` directly.

### CH-16b (merged `3149b1f`)

Prompt 9, specification, validation and SQL building. Offline; no `az`, `azd` or live calls.

- **Code (D-112).** `application/data/`: `spec.py` (`QuerySpec`, `from_dict`/`to_dict`, caps), `spec_schema.py` (`query_spec_schema(model)`), `errors.py` (20 typed `QueryError`s with stable `code`), `validate.py` + `validate_columns.py` + `validate_filters.py` + `values.py` + `resolve.py` (-> `plan.Plan`), `classify.py` (`result_audience`, `employee_level_labels`), `dialect.py`, `build.py` + `build_where.py` (`build_sql`, `build_query`).
- **Existing code touched, narrowly.** `infrastructure/persistence/tenant_sql.py`: the marker may carry `@Column` from the closed set `{client_id, AccountId}`; `bind` is shorter than before (a `_predicate` helper) and the module is exactly 250 lines. No existing test edited; `test_architecture.py` unchanged (its `warehouse_*.py` glob already covers the CH-16c adapter).
- **Tests (835 new).** `test_data_spec.py`, `test_data_validate.py` (every typed error, hostile values, audience table), `test_data_build_sql.py` (golden T-SQL and SQLite, 25 generated specs x 11 datasets x 2 dialects, SQLite execution through `TenantScopedQuery` against a two-client fixture, cross-client isolation and join isolation for every dataset, superseded rows hidden, hostile-value fuzz, LIKE escaping), `test_tenant_sql_column.py`, `test_data_access_standards.py` (stdlib-only imports plus the standards), drift test extended for the builder's hard-coded columns.
- **Gate.** Backend `pytest tests/ -q`: **3996 passed, 136 skipped, 1 xfailed** (was 3161/136/1; skip count unchanged). `check-whitelabel.ps1 -Enforce` 0 enforced, `audit-export.py --enforce` 0 findings, gitleaks no leaks, code-standards ratchet green, baseline untouched.
- **Interfaces for CH-16c/d.** `build_query(spec, model, dialect, schemas=DEFAULT_SCHEMAS, *, known_years=None) -> BuiltQuery(sql, params, plan, dialect)`; `build_sql(...) -> (sql, params)`; execute with `TenantScopedQuery(plan.client_id).bind(sql, params)`; drop the probe row (`TRUNCATION_PROBE`) and report truncation; `result_audience(plan)` is `"user"` or `"both"`.

### CH-16c (merged `0a63846`)

Prompt 9, execution adapters, limits and provenance. Offline; no `az`, `azd` or live calls.

- **Code (D-113).** `application/data/`: `exec_errors.py` (7 typed errors: `query_timeout`, `query_budget_exceeded`, `query_busy`, `data_source_unavailable`, `data_source_disabled`, `not_read_only`, `query_failed`), `executor.py` (`DataQueryExecutor`, `Rows`, `assert_read_only`, `read_capped`), `limits.py` (`QueryLimits`, `Bulkhead`), `provenance.py`, `run_context.py`, `service.py` (`DataQueryService`, `QueryResult`). `application/data_wiring.py` composes it; `application/rate_limit.py` is the gateway's token bucket moved (re-exported by `channel/limiter.py`). Adapters in `infrastructure/persistence/`: `warehouse_data_query.py` (T-SQL core + Warehouse), `lakehouse_sql_connection.py` + `lakehouse_data_query.py`, `sqlite_data_query.py` + `sqlite_data_source.py`.
- **Existing tests edited (two, narrowly).** `test_architecture.py` names the lakehouse and SQLite adapters in the tenant rule; `channel/test_gw_architecture.py` allows `application.rate_limit` for the gateway. Both in D-113.
- **Tests (+679).** `test_data_query_contract.py` (one suite, SQLite + Warehouse + Lakehouse fakes), `test_data_query_service.py`, `test_data_query_wiring.py`, `test_data_query_architecture.py` (mutation checks; guard accepts all 550 builder statements; every dataset runs through the SQLite adapter).
- **Gate.** Backend `pytest tests/ -q`: **4675 passed, 136 skipped, 1 xfailed** (was 3996/136/1; skip count unchanged). `check-whitelabel.ps1 -Enforce` 0 enforced, `audit-export.py --enforce` 0 findings, gitleaks on the branch commits no leaks, code-standards ratchet green with no baseline change. Routes, Terraform and parity pins untouched.
- **Left for CH-16f.** Terraform/azd mapping of `DATA_QUERY_*` and `LAKEHOUSE_SQL_*` (documented in `ENV-VARS.md` now), the lakehouse-endpoint grants.
- **Unverified offline.** T-SQL execution and the pyodbc timeout behaviour (fakes shaped like pyodbc errors, SQLSTATE `HYT00`), the lakehouse endpoint connection, and that `connection.timeout` is honoured on a pooled Fabric link.
- **Interfaces for CH-16d.** `get_data_query_service()` (`application.data_wiring`) -> `DataQueryService.run(spec: QuerySpec, *, principal: str) -> QueryResult(columns: tuple[ResultColumn], rows: tuple[tuple], audience: "user"|"both", employee_level_labels, provenance: QueryProvenance)`; `.available_sources() -> frozenset[Source]`; `provenance.to_dict()`, `.source_line`, `.notes`, `.truncated`. Errors: any `QueryError` subclass (`.code`, `.message`, `.field`; `QueryBudgetExceeded.retry_after_s`).

### CH-16d (merged `efd3f70`)

Prompt 9, the capabilities. Offline; no `az`, `azd` or live calls.

- **Code (D-114).** `application/capabilities/`: `catalog_data.py` (the three specs; vendored), `data_catalog.py`, `data_query.py` (`data_query`, `data_distinct_values`), `data_render.py` (result -> facts, blocks, provenance), `data_access.py` (service getter, status table, the Cowork rule), `lanes.py` (vendored; the model projection), `envelope.py` (`Block.audience`, `ToolResult.user_only_facts`), `errors.py` (`DataQueryRefused`), `invoke.py`, `registry.py`. `application/data/audit_summary.py` + `AuditCall.summary`. Gateway: `channel/lane_guard.py`, `pipeline.py`, `render.py`. Orchestrator: `toolset.py` (`ToolRun.model_facts`, `model_answer`), `compose.py`, `tools.py`, `planner.py`. **No route added**; Terraform untouched.
- **Existing tests edited (narrowly).** `test_capabilities_envelope.py` (`data_query` is the one named `**`-function), `test_architecture.py` (two vendored modules), `channel/test_gw_architecture.py` (two allow-list entries), `channel_orchestrator/orch_harness.py` (data tools answered by the real capabilities).
- **Tests (+136).** `test_data_capabilities.py` (catalog, query, lanes, refusals, Cowork, distinct values, every dataset through the numeric guard), `test_data_capabilities_api.py` (HTTP: client authorization, 403/422/429 bodies), `test_data_lanes.py`, `test_data_catalog_contract.py` (schema equals the specification's own; descriptions; sensitivity flags; validator), `test_data_audit_summary.py`, `channel/test_gw_data_lanes.py` (Cowork refusal, audit line, tool list annotations), `channel_orchestrator/test_orch_data_lanes.py` (egress for both planner modes, projection) and four golden cases (`golden/data.json`).
- **Gate.** Backend `pytest tests/ -q`: **4811 passed, 136 skipped, 1 xfailed** (was 4675/136/1; skip count unchanged). `check-whitelabel.ps1 -Enforce` 0 enforced, `audit-export.py --enforce` 0 findings, gitleaks on the branch commits no leaks, code-standards ratchet green with no baseline change, `vendor-orchestrator.py --check` agrees. Frontend and Terraform untouched.
- **Left for CH-16e/f.** Planner prompt and narrator examples, the skills' "go deeper" step, the 25 goldens, equivalence tests (CH-16e); `DATA-ACCESS.md`, `SECURITY.md`, `ENV-VARS.md`, `CONNECTIVITY-MATRIX.md`, Terraform mapping and grants (CH-16f).
- **Unverified offline.** A live Cowork or Teams call with a real model; the gateway's MCP text for a 50-row table in Cowork; T-SQL execution (CH-16c's caveat stands).
- **Interfaces for CH-16e.** Tools: `data_catalog(dataset?, search?)`, `data_query(<QuerySpec fields flat>)`, `data_distinct_values(client_id, dataset, column, tax_years?, limit=50)`; `catalog.LOOKUP` tags the first and last. Facts: `data_query.{dataset,audience,row_count,displayed_rows,row_limit,truncated,tax_years,method,as_of,source,columns[],rows[],select,group_by,measures,filters,notes}`; `data_distinct_values.{values[{value,row_count}],value_count,truncated}`; `data_catalog.{dataset_count,datasets[],notes}`. Refusal codes: the `QueryError` codes, `column_not_listable`, `employee_level_not_available`.

### CH-16e (merged `e85afd4`)

Prompt 9, making the agent use it well. Offline; no `az`, `azd` or live calls.

- **Planner and descriptions (D-115).** One decision rule (fixed engine tools first; `data_catalog` then `data_query` for descriptive or comparative payroll questions; `data_distinct_values` to resolve a name; never an invented column; name every measure with `as`; another client is a question back) in `PLANNER`, `PLAN_JSON` and the three descriptions. JSON mode now runs a lookup-only plan, shows the model its result and asks once more (`planner._with_json`, `_plan_round`). `tests/channel_orchestrator/test_orch_data_planning.py` (words in both prompts, the MAF tools and the JSON catalogue; the two-round trip over the real capabilities).
- **Narrator prompt v3.** Data-result rules and six worked examples (aggregate by location, method comparison, capped, catalog miss, employee-level rows, "why" engine-first), each composed through the real composer; manifest refreshed; the numeric and hedging guards unchanged. Existing assertions edited narrowly: prompt version and recorded versions, example count and topics, the e2e agent-version pin (now reads the prompt's version).
- **Catalog miss.** A `data_catalog` search with no match says the data has nothing for it and not to guess (`tests/test_data_catalog_search_miss.py`). The orchestrator's failure sentence no longer doubles its full stop.
- **Cowork skills.** `tcc-client-review-pack` step 8 "Go deeper (optional)" (steps renumbered 9-12), `references/data-questions.md` (ten questions with the authoritative fixed tool), a data section in `tcc-figures-and-writes` and data rows in its error table; verbatim and `verify_figures` rules untouched. `scripts/cowork_plugin/validate_content.py` accepts dataset names and the data error codes; `tests/channel/test_cowork_data_skills.py` holds every name the table teaches to the semantic model.
- **Goldens (29).** `golden/data_use.json`: descriptive by location, month and designation; name resolved by distinct values; method comparison from the run summary and from employee-level counts; a method the reader named; two "why" questions (fixed tool then data); a catalog miss; an invented column, a blocked identifier, SQL in a value, SQL as a tool; employee-level rows to the user lane (a new `model_never_sees` assertion checks no prompt carried a person-level value), an aggregate over payroll rows the model may see, a person-level dimension never listed; two named clients, a filter on the client column, another client's id in the arguments; a capped result, no rows, a timeout, an exhausted allowance, a busy warehouse; whole-book and credit questions never use data tools; JSON mode; no model. Each asserts the gateway tool sequence and, through the runner, that every numeral in an answer is in the facts or the reader's words. `test_orch_data_goldens.py` holds the set (>= 25, every kind, negative controls for `model_never_sees` and the sequence).
- **AI evals.** New offline suite `data_routing` (34 recorded plans run through the real catalog, validator and SQLite fixture: sequence, forbidden tools, typed refusal, lane, cap flag, catalog miss; threshold 1.0, `thresholds.json` offline only) and 15 `nar-data-*` narration rows (9 pass, 6 reject) through the composer. `tests/ai_evals/test_data_evals.py` proves both can fail. Existing offline thresholds unchanged at 1.0.
- **Equivalence (11 tests, 0 mismatches).** `tests/data_engine_fixture.py` + `tests/test_data_equivalence.py`: the real engine run (`RunClientCalculationCommand`) written by the real `GoldWriter` to SQLite and read by the real `GoldReader`; `data_query` equals `client_trend` (eligible, evaluated, annual average, credit per tax year per method), `client_eligibility` (population counts, annual average), the units-grid read (credit and headcount per unit-year), the installment read, `headcount_series` and `month_summaries` (headcount per month overall and per unit) and `onezero_matrix` month sums equal `unit_month_summary`. A negative control proves the comparison can fail. No model or builder change was needed. The fixed side for monthly headcount is the reader, not a tool (no tool returns it).
- **Gate.** Backend `pytest tests/ -q` on the merge: **4918 passed, 136 skipped, 1 xfailed** (was 4811/136/1; +107; skip count unchanged). `check-whitelabel.ps1 -Enforce` 0 enforced, `audit-export.py --enforce` 0 findings, `check-links.py` 0 broken, gitleaks on the branch commits no leaks (one false positive on a fixture string in an unmerged commit was fixed before the merge), code-standards ratchet green with no baseline change (a complexity-12 `_facts` was split), `prompt-manifest.py` and `vendor-orchestrator.py --check` agree, Cowork package build/validate tests green. Frontend, Terraform, routes and parity pins untouched. `scripts/ai-eval.py` offline: routing 27/27, narration 39/39, refusal 10/10, data_routing 34/34.
- **Left for CH-16f.** `DATA-ACCESS.md`, `SECURITY.md`, `KNOWN-LIMITATIONS.md`, `ENV-VARS.md` rows beyond CH-16c's, `CONNECTIVITY-MATRIX.md`, the Terraform/azd mapping, the Fabric Data Agent evaluation, the lakehouse grants.
- **Unverified offline.** How a live model follows the new planner rule and narrator examples (re-run `scripts/live-ai-checks.py` and `scripts/ai-eval.py --live` at the redeploy; `data_routing` has no live subject), JSON mode against a real gateway without tool calling, and T-SQL execution (CH-16c's caveat stands). The vendored orchestrator copy is gitignored: `python scripts/vendor-orchestrator.py` before `azd deploy`; the planner's JSON second round and the new prompt only reach the live agent after that redeploy.

### CH-16f (merged `ed2fbb6`)

Prompt 9, docs, security, Terraform mapping, grants and the Fabric Data Agent evaluation. Offline; no `az`, `azd` or live calls.

- **Docs (D-116).** New `docs/m365-channel/DATA-ACCESS.md` (design, lanes, limits, audit and provenance, queryable / not queryable, how to add a dataset or column and the drift test that forces the decision, operational notes, the grants, and a one-page Fabric Data Agent recommendation: **off**, with the conditions for a sandbox-only exploratory lane). Updated: ADR-009 §8, SECURITY.md (posture row + dependency row), KNOWN-LIMITATIONS (four rows), ENV-VARS (rows completed, azd table, scripts table), CONNECTIVITY-MATRIX (R5a, CH10), DEPLOYMENT-HANDOVER (azd values), the channel README index.
- **Terraform / azd.** Seven optional non-secret API settings: `DATA_QUERY_SOURCE_ENABLED` (only when `data_query_source_enabled` is true; default false), `DATA_QUERY_TIMEOUT_SECONDS`, `DATA_QUERY_MAX_ROWS`, `DATA_QUERY_RATE_PER_MINUTE`, `DATA_QUERY_MAX_CONCURRENCY`, `LAKEHOUSE_SQL_SERVER`, `LAKEHOUSE_SQL_DATABASE` (each only when set; numeric ranges validated). azd values `TCC_DATA_QUERY_*` / `TCC_LAKEHOUSE_SQL_*` in `infra/main.tfvars.json`. The gateway receives none. `infra/tests/data_query.tftest.hcl` (7 runs).
- **Grants.** `scripts/grant-warehouse-sql.py --profile lakehouse`: object-level `GRANT SELECT` on `Payroll`, `Location`, `PayCode` (read from the semantic model) for the API identity, on the lakehouse SQL analytics endpoint; refuses the gateway identity; guarded (same workspace host as the guarded Warehouse). postprovision runs it only when `TCC_DATA_QUERY_SOURCE_ENABLED=true`. `backend/tests/test_lakehouse_grants.py` (16 tests) pins the T-SQL (SELECT only; no write, schema, role or DENY) and the postprovision wiring; `test_data_access_docs.py` (8) keeps code, Terraform, azd, ENV-VARS and the page consistent.
- **Gate.** Backend `pytest tests/ -q`: **4942 passed, 136 skipped, 1 xfailed** (was 4918/136/1; +24; skip count unchanged; one existing contract test, the handover-doc check, caught the new azd values and the handover was updated, not the test). `terraform fmt -check -recursive`, `init -backend=false`, `validate`, `tflint --recursive` clean; `terraform test`: **70 passed** (was 63; +7). `check-whitelabel.ps1 -Enforce` 0 enforced (29 allow-listed), `audit-export.py --enforce` 0 findings, `check-links.py` 0 broken, `test_code_standards.py` green with no baseline change, `gitleaks` no leaks.
- **Unverified offline.** That the lakehouse endpoint accepts object-level `GRANT` to the API identity by name and that the workspace role alone already suffices; the first live T-SQL read of the source tables; the claims about the Fabric Data Agent are from Microsoft documentation of 3 November 2026 (preview; the Foundry tool is documented as scheduled for deprecation on 6 November 2026) and should be re-read before anyone acts on them.