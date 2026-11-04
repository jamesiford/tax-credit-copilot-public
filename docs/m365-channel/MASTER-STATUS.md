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
## Stage 2 — CH-16 governed Fabric data access: todo
## Stage 3 — CH-17 live redeploy and verification: todo
## Stage 4 — CH-18 branch of record, cleanup, hand-off: todo

## Blockers

None.
