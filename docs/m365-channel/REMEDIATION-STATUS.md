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
| RM-04 | Abuse/fuzz tests | todo | | | |
| RM-05 | Numeric guard coverage | todo | | | |
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

## Blockers

None.
