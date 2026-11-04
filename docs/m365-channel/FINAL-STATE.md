# Final state of the Microsoft 365 channel PoC (3 November 2026)

Customer-neutral. Nothing in this file is an identifier; the private deployment notes hold those. **Nothing has been pushed.**

- **Branch of record:** `feat/m365-channel`, tagged `m365-channel-poc-2026-11-03` (annotated, local).
- **`main` is untouched** and still prints `029b9ad2d2c002c09167375748120c7a8af3bc03` (`git rev-parse main`); `origin/main` is the same commit.
- Safety references: `pre-master-2026-11-03` (start of the master run), `pre-final-run-2026-11-03` (before the live redeploy),
  `pre-consolidation-2026-11-03` (before cleanup).

## Per stage

| Stage | Result |
| --- | --- |
| 0 Preflight | done: location rules, azure.yaml protocol shape, baseline 2817 backend / 923 frontend tests |
| 1 CH-15 demo polish | done (offline): Graph display names, agent icon (SVG sources, rendered at build), narration quality and hedging guard, portal chat evidence stream, known issues |
| 2 CH-16 governed data access | done (offline): semantic model, structured query spec, SQL builders, executors, three capabilities, lanes, planner and skills, equivalence tests, docs and grants |
| 3 CH-17 live redeploy | done: API, web, gateway and hosted agent redeployed; agent version 20; published app 1.0.3; Cowork zip v2 built; live verification recorded in [evidence/live-final-2026-11-03.md](../archive/evidence/live-final-2026-11-03.md) |
| 4 CH-18 consolidation | ran in **keep-main-untouched** mode: no branch deleted, `main` not moved, worktrees removed only after proof |

## What is built

- **Channel gateway** (`backend/channel/`): a third App Service that authenticates every caller (a trusted agent with a
  channel-asserted user, or a delegated Cowork user), enforces who may write, and fronts the API's capability layer over REST
  and MCP. Every call is audited per user, writes are two-step and idempotent, and `verify_figures` checks a figure against the engine.
- **Orchestrator** (`channel_orchestrator/`): a Foundry hosted agent behind Azure Bot Service for Teams and Microsoft 365 Copilot
  Chat. A planner picks capabilities, the platform composes the reply from the engine's own rendering, a narrator writes only
  `{{facts.…}}` placeholders, and numeric and hedging guards reject any narration that is not exactly the facts.
- **Teams, Copilot Chat and Cowork:** Teams and Copilot Chat use the published agent (1.0.3, scope Shared); Cowork uses the plugin in
  `channels/cowork/` with delegated OAuth. The agent and plugin share one icon (`channels/branding/`, SVG only; PNGs are rendered at build).
- **AI platform and gateway support:** ports and adapters for model access, provider chains, an optional external model gateway
  (with a PoC mock behind its own toggle), resilience, observability and safety checks; SDKs live only under `infrastructure/ai/`.
- **Governed data access** ([DATA-ACCESS.md](DATA-ACCESS.md)): a checked-in semantic model, a validated structured query
  (no model-written SQL), every value bound, client scope as the first predicate, read-only execution with limits, and two output lanes so
  employee-level rows reach the person and never the model. Employee-level results are refused over Cowork unless the caller is a writer.
- **Display names:** the gateway resolves a name and UPN from Microsoft Graph for the Teams path (`User.ReadBasic.All`, fail-soft).
- **UI revamp:** the modern theme, top-bar shell and Ask workspace (merged from `feat/ui-modern-theme`), with a typed `evidence` stream from the portal chat.
- **Audit and hardening:** per-user audit rows for every channel call; the hardening plan is `HARDENING-SPIKE.md` and the demo-posture
  list is [DEMO-CLEANUP.md](DEMO-CLEANUP.md).

## Tests and gates (at the final code tip; documentation commits follow it)

| Gate | Result |
| --- | --- |
| Backend `pytest tests/ -q` (parity unset; synthetic parity gate included) | 4957 passed, 136 skipped, 1 xfailed |
| Frontend `npx vitest run` (`NODE_OPTIONS=--no-experimental-webstorage`) | 929 passed |
| `npm run build` | ok |
| `check_all.py` (with the mock API, a CSV backend and Vite running) | 21 of 22 rows pass; the failing row is the working-tree gitleaks scan, see below |
| Terraform fmt, validate, tflint | clean |
| `terraform test` | 70 passed on a clean copy of `infra/`. **In the live checkout it fails**, because the live overlay is copied to `infra/m365-poc.auto.tfvars` and overrides test variables. Copy `infra/` elsewhere (without that file) to test |
| `check-whitelabel -Enforce`, `audit-export --enforce` | 0 enforced findings |
| gitleaks on tracked history (`--log-opts=HEAD`) | no leaks (167 commits) |
| gitleaks on the working tree | 63 findings, all in ignored live state (`.azure/` state and `.env`) and `.venv/` packages; none tracked |
| Code-standards ratchet | green, no new baseline entries |
| Orchestrator vendored copy | matches the source |
| Private-identifier scan of tracked files | none (the only GUID is a public Azure built-in role id); customer-name hits are the allow-listed legacy ones |
| Raster files tracked | none |

Not run: a live non-writer refusal over Teams or Cowork (needs a second person; the offline tests cover it), a real slow-statement timeout, and live GenAI spans (the hosted agent exports no telemetry).

## How to run, build and deploy

```pwsh
cd backend ; ..\.venv\Scripts\python.exe -m pytest tests/ -q            # full backend suite (TCC_REQUIRE_PARITY unset without private fixtures)
cd frontend ; $env:NODE_OPTIONS='--no-experimental-webstorage' ; npx vitest run ; npm run build
python scripts/render-icons.py                                           # icons into dist/branding/
python scripts/build-cowork-plugin.py --config overlays/<name>/cowork.config.json --strict --out <folder>
python scripts/vendor-orchestrator.py                                    # before deploying the orchestrator
azd provision ; azd deploy api ; azd deploy web                         # never an unqualified `azd deploy`, never `azd up` on a live environment
cd channel_orchestrator ; azd deploy                                     # the hosted agent (its own azd environment)
pwsh scripts/publish-m365.ps1 -PublishScope Shared                       # never Tenant
pwsh scripts/poc-pause.ps1 -ResourceGroup <rg>                           # pause; add -Resume to resume
azd down --purge --force --no-prompt                                     # teardown (see OPERATIONS.md for what to clean by hand)
```

After every deploy or publish, re-check the agent invariants ([PUBLISHING.md](PUBLISHING.md)): the container declares `responses`
only, the endpoint declares `activity` and `responses`, the public M365 endpoint is on, and the instance identity keeps its roles.

## Where the live state lives, and why it is not tracked

`.azure/tcc-poc-channel/` (including the Terraform local state), `channel_orchestrator/.azure/tcc-orch/` and `overlays/m365-poc/`
sit in the main checkout and are gitignored because they hold environment values and state. They were copied here, compared with every
worktree before the worktrees were removed (the main checkout was the newer copy in every difference), and are intact. Back them up before
moving the checkout; losing the Terraform state means re-importing the resources.

## Demo posture and known limitations

The environment runs in the demo posture: Foundry data plane public (Entra only, firewall open), debug `/whoami` on, the mock model gateway
present, a writer allow-list. [DEMO-CLEANUP.md](DEMO-CLEANUP.md) lists what to switch off, in order. The model capacity was raised to
100 thousand tokens a minute for the demo and the revert is listed there. See [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md); the open ones
from the live run are: the twelve-month and per-location weekly-hours data questions are not reliably answered, the at-risk narration mentions a table
the Teams reply does not carry, and `/whoami` still prints "(name not provided)" (the gateway resolves the name for the audit).

## Open decisions for the owner

1. Where, if anywhere, to push, and how to split the branches ([PUSH-CHECKLIST.md](PUSH-CHECKLIST.md)).
2. When to close the demo posture.
3. Whether to keep the raised model capacity.

## Planned branch split (not done)

- `main` stays untouched at `029b9ad`.
- `feat/ui-modern-theme` is already UI/UX only: 10 commits off `main`, 196 files, 187 under `frontend/`. Only `README.md` and
  `.github/copilot-instructions.md` overlap with the channel work (its other non-frontend files are UI design documents and the overlay
  frontend example).
- A channel, AI platform and Fabric data branch is to be rebuilt off `main` without the UI merge (`58dcd53`), re-applying the later work. The AI
  platform was built on the early channel work, so they stay together.
- CH-15d (the portal chat evidence stream; it touches `frontend/src/api.js`, `frontend/tools/mock_api.py`, the Ask backend test and
  `askBackendShape.json`) depends on both, so it goes in an optional integration branch that contains both.
- The combined `feat/m365-channel` and the `pre-master-2026-11-03` tag remain the safety reference.

## Branch, tag and worktree inventory

| | Before Stage 4 | After Stage 4 |
| --- | --- | --- |
| Local branches | 52: `main`, `feat/m365-channel`, `feat/ui-modern-theme`, 10 `jamesiford-*`, 39 `wp/*` | the same 52, none deleted; every branch is merged into `feat/m365-channel` |
| `main` | `029b9ad` | `029b9ad` (unchanged) |
| Tags | `pre-master-2026-11-03`, `pre-final-run-2026-11-03`, `pre-consolidation-2026-11-03` | those three plus `m365-channel-poc-2026-11-03` |
| Worktrees | this checkout plus six others: the UI worktree (`tax-credit-copilot-public-ui`) and five under `copilot-worktrees/` (one detached prewarm, four session worktrees) | this checkout only |

Each removed worktree was clean, had no commits beyond `feat/m365-channel`, and (the only one holding live-state copies) had a live-state copy that
the main checkout superseded. Their branches were kept. Folders under `copilot-worktrees/tax-credit-copilot-public/` that git no longer
registers (twelve session folders and a log) were left in place: they are not this run's to delete.
