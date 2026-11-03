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
| AI-06 | Observability, prompt versioning, evals | in_progress | `wp/AI-06-observability` | — |
| AI-07 | Safety | todo | — | — |
| AI-08 | Coding-standards ratchet | todo | — | — |
| AI-05 | Conversation continuity (stretch, last) | todo | — | — |

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

## Blockers

_None._
