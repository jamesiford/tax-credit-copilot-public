# Microsoft 365 channel — status

Customer-neutral. This file is the only memory a resumed session has; keep it
truthful. Decisions live in [DECISIONS.md](DECISIONS.md).

Integration branch: `jamesiford-m365-capability-layer` (see D-01 — this session
runs in a worktree, so `feat/m365-channel` is held by the main checkout).

## Work packages

| WP | Title | Status | Branch | Merge SHA |
| --- | --- | --- | --- | --- |
| CH-01 | Capability layer (`application/capabilities/`) | done | `wp/CH-01-capabilities` | `0c8a4d8` |
| CH-02 | Numeric guard, composer, narrator agent, ADR-008 | in_progress | `wp/CH-02-numeric-guard` | — |

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

## Blockers

_None._
