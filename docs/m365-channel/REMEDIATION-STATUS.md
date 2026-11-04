# Remediation run status (RM)

Customer-neutral. Resume from this file if interrupted. Start: tip `0b3a09a`, tag `pre-remediation-2026-11-04`. `main` must stay at
`029b9ad2d2c002c09167375748120c7a8af3bc03` (never moved, merged into, reset or pushed). Branch of record `feat/m365-channel`; work in `wp/RM-*` branches,
merged `--no-ff`. No frontend changes (findings go to REMEDIATION-FINDINGS.md). Nothing is pushed.

Baseline (FINAL-STATE.md): backend 4957 passed / 136 skipped / 1 xfailed; frontend 929 (not touched); terraform test 70 (on a clean copy of infra/);
check_all 21 of 22 (the all-tree gitleaks row); hosted agent version 20 is the rollback target.

| WP | Title | Status | Branch | Merge SHA | Evidence |
| --- | --- | --- | --- | --- | --- |
| RM-01 | Small-group suppression | done | wp/RM-01-small-group-suppression | f5c7ac5 | backend 4998 passed / 136 skipped / 1 xfailed (+39 new: 35 in `test_data_small_groups.py`, 4 architecture); whitelabel 0 enforced; audit-export 0; links 0 broken; gitleaks (167+ commits) none; vendored copy matches; code-standards ratchet green, no baseline change; D-119 |
| RM-02 | Cowork fails closed | done | wp/RM-02-cowork-fails-closed | 174be1e | backend 5061 passed / 136 skipped / 1 xfailed (+63 new: 31 `test_cowork_fails_closed.py`, 32 `channel/test_gw_channel_binding.py`); whitelabel 0 enforced; audit-export 0; links 0 broken; gitleaks none; vendored copy re-vendored and matches (shared refusal message changed); ratchet green, baseline unchanged; D-120. Residual: `CHANNEL_CALLER_CHANNELS` unset keeps enum-level trust (not mapped in Terraform; owner action) |
| RM-03 | Auth default and audit alerts | done | wp/RM-03-auth-default-audit-alerts | fcb8141 | backend 5129 passed / 136 skipped / 1 xfailed (+68 new: 11 `test_audit_alerts.py`, 5 `channel/test_gw_audit_alerts.py`, 29 `test_auth_default.py`, 13 `test_writer_sources.py`, 10 `test_architecture_audit_alerts.py`); `terraform test` 70 passed on a clean copy (fmt and validate clean); whitelabel 0 enforced; audit-export 0; links 0 broken; gitleaks none; vendored copy matches; code-standards ratchet green (baseline tightened for `check_deployment_configuration`); D-121. Public profile now sets `ALLOW_ANONYMOUS_SYNTHETIC` (applies at the next provision). Alert query not run against a workspace (unverified) |
| RM-04 | Abuse/fuzz tests | done | wp/RM-04-abuse-tests | fa0f6d8 | backend 5244 passed / 136 skipped / 1 xfailed (+115 new: `test_data_query_abuse.py` seeded fuzzer over six categories x two dialects x 500 seeds, apostrophe names bound and absent from SQL text, 20 refused derived expressions; 4 architecture); the fuzzer found and the WP fixed four holes (trailing-newline identifiers and aliases reached SQL text, uncapped tax-year list, out-of-range client id, plus a recorded tenant-helper limit); whitelabel 0 enforced; audit-export 0; links 0 broken; gitleaks none; vendored copy matches; ratchet green, baseline unchanged; D-122. Existing tests changed narrowly: three quote-only values moved to "accepted", one capability example value changed |
| RM-05 | Numeric guard coverage | done | wp/RM-05-numeric-guard-coverage | 7750c91 | backend 5305 passed / 136 skipped / 1 xfailed (+61 new: 33 `channel_orchestrator/test_orch_numeric_lanes.py`, 14 `test_numeric_guard_lanes.py`, 14 `channel/test_gw_numeric_lanes.py`); orchestrator goldens unchanged; a mutation (the new check patched out) fails six tests; whitelabel 0 enforced; audit-export 0; links 0 broken; gitleaks (HEAD) none; vendored copy matches; ratchet green; D-123. Closed a gap the tests found: a placeholder could point into the person's lane (`compose_reply` now drops such a narration); takes effect at the next orchestrator deployment |
| RM-06 | MAF alignment spike and hand-rolled inventory | todo | | | |
| RM-07 | Generated FunctionTools | todo | | | |
| RM-08 | Tool rules as MAF middleware | todo | | | |
| RM-09 | Foundry chat client | todo | | | |
| RM-10 | Planner collapse and MAF Workflows | todo | | | |
| RM-11 | Agent as code | todo | | | |
| RM-12 | Hosting | todo | | | |
| RM-13 | Parity and conformance | todo | | | |
| RM-14 | MCP facade decision | todo | | | |
| RM-15 | Knowledge tier (design and port) | todo | | | |
| RM-16 | Live redeploy | todo | | | |
| RM-17 | Composition root | todo | | | |
| RM-18 | Routers through the mediator | todo | | | |
| RM-19 | Ports and gold_reader split | todo | | | |
| RM-20 | Typed Settings | todo | | | |
| RM-21 | Small wins | todo | | | |
| RM-22 | Docs | todo | | | |
| RM-23 | Code out of docs | todo | | | |
| RM-24 | Scripts | todo | | | |
| RM-25 | Orchestrator and infra tidy | todo | | | |

## Tier 1 complete (RM-01 to RM-05)

`python frontend/tools/check_all.py` was run once at the end of the tier, on `feat/m365-channel` at the RM-05 merge (`7750c91`), with the mock API on :8000, a CSV backend on :8001 (started with `ENVIRONMENT=local AUTH_MODE=none DATA_SOURCE=csv`, the explicit local opt-in RM-03 requires) and Vite on :5173: **21 of 22 passed**; the one failure is the known baseline row (`gitleaks (HEAD + working tree)`: HEAD scans clean, the working-tree scan reports the gitignored local files). The frontend suite ran 929 tests (not changed). Servers were stopped afterwards (port 8000 still shows an orphaned listening socket with no owning process, which the OS releases on its own).

Backend after Tier 1: **5305 passed / 136 skipped / 1 xfailed** (baseline 4957 passed; +348 over the run; the only cases removed are three quote-only parametrised ones in `test_data_validate.py`, moved to a new test, see D-122). `terraform test` 70 passed on a clean copy after RM-03 (the only infra change).

## Blockers

None.
