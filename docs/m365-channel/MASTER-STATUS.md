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
## Stage 2 — CH-16 governed Fabric data access: in progress

| WP | Status | Merge SHA | Evidence |
| --- | --- | --- | --- |
| CH-16a semantic model | done | 9992238 | backend 3996 passed (with 16b) |
| CH-16b spec, validation, SQL builders | done | 3149b1f | |
| CH-16c executors, limits, provenance | done | 0a63846 | backend 4675 passed |
| CH-16d capabilities, lanes | todo | | |
| CH-16e planner, narrator, skills, goldens, equivalence | todo | | |
| CH-16f docs, security, grants, Fabric-agent evaluation | todo | | |

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
