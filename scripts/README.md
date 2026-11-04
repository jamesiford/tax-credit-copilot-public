# scripts/

Operator, CI and deployment tooling. Nothing here ships in the API or web package. A test
(`backend/tests/test_architecture_scripts.py`) fails if a script is added without a row below.

Run from the repository root with the repo's `.venv` (`.venv\Scripts\python.exe` on Windows) unless a row says
otherwise. "Run by" says who invokes it: **azd** (an `azure.yaml` hook), **CI** (a `.github/workflows` job),
**script** (another script calls it), **test** (a backend test imports or runs it), **owner** (a person, by hand).

## Naming and layout rules

- Scripts are named with hyphens (`check-links.py`, not `check_links.py`).
- **Scripts that azd or CI run, and everything they call, stay at the top level under their current name**: a
  hook, a workflow step, a test or a doc names them by path, and a rename or move would break the deploy
  silently. That is `postprovision.ps1`, `deploy-channel.ps1`, `apply-migrations.py`, `grant-warehouse-sql.py`,
  `seed-operational-store.ps1`, `package-app.py`, `sql_common.py`, `check-whitelabel.ps1`, `audit-export.py`.
- A script goes in a subfolder only when nothing else references it (no hook, workflow, Dockerfile, doc or test).
  Today that is `maintainer/`.
- Two names keep an underscore on purpose, because Python imports them by name and a hyphen cannot be imported:
  `sql_common.py` (imported by `apply-migrations.py`, `run-sql.py`, `grant-warehouse-sql.py` and loaded by tests
  under that name) and the helper packages `branding_icons/` and `cowork_plugin/`.

## azd hooks and what they call

| Script | Purpose | Inputs | Run by |
| --- | --- | --- | --- |
| `postprovision.ps1` | Runs after every `azd provision` / `azd up`: schema migrations, the synthetic source load (public profile), Warehouse grants, then the operational seed. A failed step fails the hook. | Terraform outputs in the azd environment (`TCC_FABRIC_CREATED`, `WAREHOUSE_SERVER`, `GATEWAY_IDENTITY_NAME`, ...) | azd (`postprovision`) |
| `deploy-channel.ps1` | Zip-deploys the Microsoft 365 channel gateway, only when the channel is enabled (azd cannot make a service conditional). | azd environment; builds the zip with `package-app.py` | azd (`postdeploy`), CI (`deploy.yml`) |
| `apply-migrations.py` | Applies schema migrations (`docs/data/schema/migrations/`) to a guarded Fabric Warehouse; `--bootstrap` only on a Warehouse Terraform just created. | `--target`, `--bootstrap`; Warehouse settings from the environment | `postprovision.ps1`, CI (`deploy.yml`), owner |
| `grant-warehouse-sql.py` | Grants an identity T-SQL access to `tcc_gold` / `tcc_ops` (profiles `api`, `gateway`, `lakehouse`). Idempotent. | `--target`, `--profile`, `--principal`, `--dry-run` | `postprovision.ps1`, CI (`deploy.yml`), owner |
| `seed-operational-store.ps1` | Seeds `tcc_ops` claims and engagements so the coverage matrix is not blank after provisioning. Idempotent. | azd environment | `postprovision.ps1`, owner |
| `sql_common.py` | Shared plumbing (target resolution and guard, environment loading) for the three SQL scripts above and `run-sql.py`. A module, not a command. | imported | the SQL scripts, tests |
| `package-app.py` | Zips an App Service package honouring the service's `.webappignore`, so CI ships what `azd up` would. | `backend` or `frontend`, output path | `deploy-channel.ps1`, CI (`deploy.yml`), test |

## CI

| Script | Purpose | Inputs | Run by |
| --- | --- | --- | --- |
| `check-whitelabel.ps1` | White-label deny-list over every tracked text file. `-Enforce` exits non-zero on a hit not in the allow-list. | `-Enforce` | CI (`ci.yml`), owner, `maintainer/export-public.ps1` |
| `audit-export.py` | Export-readiness audit: binaries, raster/PDF ban, Office XML, synthetic data. `--enforce` exits 1 on a finding. | `--enforce` | CI (`ci.yml`), owner, `maintainer/export-public.ps1`, test |
| `whitelabel-allowlist.txt` | The allow-list both of the above read. Data, not a script. | n/a | the two scripts |

## Quality gates and generators (owner or test)

| Script | Purpose | Inputs | Run by |
| --- | --- | --- | --- |
| `code-standards.py` | Reports or tightens the coding-standards ratchet; `--update` refuses to loosen it. | `--update` | owner, test (`test_code_standards.py`) |
| `check-links.py` | Fails on a relative Markdown link that does not resolve. | optional file list | owner, test (`test_doc_links.py`) |
| `check-sdk-versions.py` | Prints pinned versus latest AI SDK versions; `--strict` exits 1 when behind. Needs the network for "latest". | `--strict` | owner |
| `prompt-manifest.py` | Checks or refreshes `agents/prompts/manifest.json` (prompt versions). | `--refresh` | owner, test |
| `generate-semantic-model-doc.py` | Regenerates `docs/data/SEMANTIC-MODEL.md` from the semantic model; `--check` exits 1 if stale. | `--check` | owner, test |
| `generate-schema-variants.py` | Generates `docs/data/schema/tcc-schema.sqlserver.sql` from the Fabric DDL. | none | owner, test (banner) |
| `ai-eval.py` | Runs the AI evals and prints a table; `--live` uses the configured providers. | `--live`, `--json` | owner, test (`ai_evals`) |
| `vendor-orchestrator.py` | Copies the shared framework-free modules into `channel_orchestrator/` (the vendored copy is gitignored); `--check` verifies it. | `--check` | owner, the orchestrator's build, test |
| `portable-rules/` | `flex_rules.py` (stdlib-only hand-off of the business rules) and `crosscheck.py` (proves it matches the engine). Explained in `docs/data/portable-rules/README.md`. | none; `TCC_BACKEND` optional | owner, test (`test_architecture_docs_code.py`) |

## Channel operations (owner)

| Script | Purpose | Inputs | Run by |
| --- | --- | --- | --- |
| `channel-writers.py` | Manages the writer allow-list (`add`, `remove`, `list`). | subcommand, object id | owner, test |
| `channel-audit.py` | Prints one user's channel audit timeline. | `--user`, `--since`, `--until`, `--tool` | owner, test |
| `channel-smoke.ps1` | Shows what the platform received for your last Teams / Copilot message, then pings the gateway as you. | `az login`, azd environment | owner, test |
| `channel-live-smoke.py` | Live smoke of the deployed gateway as the signed-in operator. | `GATEWAY_BASE_URL`, `GATEWAY_TOKEN`, `WRONG_TOKEN`, ... | owner |
| `live-ai-checks.py` | Live checks of the model provider chain from inside the network. | scenario, `AI_*` / `FOUNDRY_*` environment | owner |
| `assign-channel-roles.ps1` | Assigns the Entra app roles the channel needs, through Graph with your own sign-in. Supports `-WhatIf`. | principal ids as parameters | owner, test |
| `publish-m365.ps1` | Publishes a Foundry hosted agent to Microsoft 365 Copilot and Teams (idempotent REST flow). | agent and tenant parameters | owner, test |
| `poc-pause.ps1` | Pauses or resumes the PoC's compute; `-Resume` reverses it. | `-Resume` | owner |
| `create-model-connection.ps1` | Creates a Foundry Model Gateway connection without putting a secret in the repo or state. | connection parameters | owner, test |
| `grant-fabric-mi-access.ps1` | Grants the API's managed identity a role on an existing Fabric workspace when Terraform does not manage access. | workspace and identity parameters | owner |
| `run-sql.py` | Runs T-SQL against a guarded Warehouse target; `--resolve` only prints the target. | `--target`, `--file`, `--section` | owner |
| `mock-ai-gateway.py` | OpenAI-compatible stand-in for the customer's model gateway (tests, local, the PoC's mock App Service). Its pip list is `mock-ai-gateway.requirements.txt`. | `MOCK_AUTH` and fault settings | owner, test, Terraform (`mock_ai_gateway`) |

## Cowork plugin and icons (owner)

| Script | Purpose | Inputs | Run by |
| --- | --- | --- | --- |
| `build-cowork-plugin.py` | Builds the Copilot Cowork plugin zip reproducibly under `dist/`. | `--config`, `--strict` | owner |
| `render-icons.py` | Renders the agent icon PNGs from `channels/branding/*.svg`. Needs `requirements-icons.txt`. | `--preview`, `--renderer`, `--out` | owner, `publish-m365.ps1`, `build-cowork-plugin.py`, test |
| `cowork_plugin/` | Helper package for `build-cowork-plugin.py` (manifest, frontmatter, validation, packaging). | imported | `build-cowork-plugin.py` |
| `branding_icons/` | Helper package for `render-icons.py` (PNG encoder and renderers). | imported | `render-icons.py` |
| `requirements-icons.txt` | pip list for the icon renderer. Data. | n/a | owner |

## `maintainer/` (nothing else references these)

| Script | Purpose | Inputs | Run by |
| --- | --- | --- | --- |
| `maintainer/export-public.ps1` | Exports a clean, tracked-only copy of the repository for public release into a new folder and runs the release checks inside it. Never overwrites. | optional `-Destination` | owner |
| `maintainer/split-router.py` | Splits a FastAPI router module into concern-shaped files without dropping decorators or module-level names. | module path, `--members`, `--plan` | owner |

Scripts outside this folder: `backend/tools/` is the engine's deterministic compute and a few data-maintenance
tools (it is not renamed, see D-143); `frontend/tools/` holds the UI gates.
