# Local runbook: configure, run and calculate (.NET host)

How to set the environment, deploy the agents, run the backend and frontend, and generate calculations for clients.
Everything here was checked against the code in this repository on 2026-11-17 unless a line says **unverified**.

## 1. Mental model (read this first)

| Piece | What it is | Port |
|---|---|---|
| `TaxCredit.Api` | HTTP API. **Queues** runs; it does not execute them (except the single-client synchronous route, section 5). | 8000 |
| `TaxCredit.Worker` | Background process that **executes** queued runs. Without it, a run stays `queued` forever. | none |
| Operational store | Claims, findings, runs, batches. Local SQLite file `dotnet\artifacts\local\operations.db`, shared by the API and the Worker. | n/a |
| Lakehouse | Read-only source of payroll, read over the SQL analytics endpoint. | n/a |
| `frontend` | Vite dev server, proxies `/api` to the API. | 5173 |

The Python product ran a worker thread inside the API when `ENVIRONMENT=local` (`RUN_WORKER_INLINE`). The .NET host does not: start the Worker.

## 2. Environment variables

You normally set none by hand. `backend\.env` is the single input; `dotnet\local-env.ps1` maps it to the .NET names and
`configure-local.ps1` / `run-local.ps1` / `run-worker.ps1` apply them.

### 2a. Set these in `backend\.env`

| `backend\.env` name | Becomes (.NET) | What it does |
|---|---|---|
| `LAKEHOUSE_SQL_SERVER` | `SOURCE_SQL_SERVER` | SQL analytics endpoint host of the lakehouse that holds payroll. Required. |
| `LAKEHOUSE_SQL_DATABASE` | `SOURCE_SQL_DATABASE` | The lakehouse's endpoint database. Required. |
| `SOURCE_SCHEMA` | `SOURCE_SCHEMA` | Schema holding the source tables (default `tcc_source`; set `flex` for the existing lakehouse; set but empty means a non-schema lakehouse, `dbo`). |
| `AUTH_MODE` | `AUTH_MODE` | `none` for local development (needs `ENVIRONMENT=local`), `entra` when deployed. |
| `FABRIC_WORKSPACE`, `FABRIC_LAKEHOUSE` | same | Workspace and lakehouse names. Without them `/api/workspace` answers 503 and the portal shows "Workspace unavailable". |
| `ONELAKE_ENDPOINT` | same | Optional. Private-link blob host, only if the workspace is private-link. |
| `REFERENCE_ACCOUNT_ID` | same | Optional. The account the sealed reference run is about; unset means the reference views are off. |
| `WAREHOUSE_SERVER`, `WAREHOUSE_DATABASE` | `FABRIC_SQL_SERVER`, `FABRIC_SQL_DATABASE` | Only for `-Persistence warehouse` (claims, findings, runs written to the Fabric Warehouse). Not needed for the SQLite default. |

`SOURCE_READ_MODE` in `.env` is read only by the Python backend; the .NET host always reads over the SQL endpoint, so it is harmless here.

### 2b. Set by the scripts (do not edit)

| Variable | Value | What it does |
|---|---|---|
| `ENVIRONMENT` | `local` | Marks a developer run; lets `AUTH_MODE=none` through. |
| `DATA_SOURCE` | `lakehouse` (`csv` offline) | Which payroll source the host uses. |
| `TCC_PERSISTENCE_PROVIDER` | `sqlite` (or `warehouse`) | Where claims, findings, runs and batches live. API and Worker must match. |
| `ARTIFACT_STORE` | `local` | Claim-package bytes on local disk (`dotnet\artifacts\local\bytes`). |
| `AZURE_TOKEN_CREDENTIALS` | `AzureCliCredential` | Forces the `az login` identity instead of Visual Studio / VS Code sign-ins. |

### 2c. Optional tuning (not set by default)

| Variable | Default | What it does |
|---|---|---|
| `OPERATIONAL_DB` | `dotnet\artifacts\local\operations.db` | Path of the SQLite store. |
| `ARTIFACT_LOCAL_ROOT` | `dotnet\artifacts\local\bytes` | Where artifact bytes go. |
| `TCC_REPOSITORY_ROOT`, `RULES_DIR` | discovered | Repository root and rule-pack folder. |
| `PORTFOLIO_FOOTPRINT_MODE` | `auto` | `auto` asks the SQL catalogue for a payroll row estimate and refuses the footprint above the limit; `on` always runs it under the timeout; `off` never runs it. |
| `PORTFOLIO_FOOTPRINT_MAX_ROWS` | 50000000 | The largest estimated payroll table `auto` will scan for the footprint. |
| `PORTFOLIO_FOOTPRINT_TIMEOUT_SECONDS` | 20 | Statement timeout for the footprint query (the server cancels it). |
| `PORTFOLIO_FOOTPRINT_CACHE_SECONDS` | 300 | How long the row estimate, and a timeout, are remembered. |
| `RUN_BATCH_MAX_ITEMS` | 5000 | Largest batch a request may queue. |
| `RUN_BATCH_CONFIRM_ABOVE` | 25 | A batch larger than this needs the typed confirmation count. |
| `RUN_STALE_WORKER_SECONDS` | 60 | After this long with queued work and no live Worker lease, the Runs page shows "queued runs in this batch are not progressing". |
| `RATE_LIMIT_PER_MINUTE` | 60 | Per-caller limit on draft save, preview, export and batch start. |
| `PAY_CODE_POLICY` | `assume` locally | `strict` blocks a calculation on an unmapped pay code. |
| `FISCAL_RULES_POLICY` | `assume` | `strict` blocks a client with no fiscal rule instead of assuming a calendar year. |
| `DATA_CLASSIFICATION` | `synthetic` | Must be `customer` for real data in a deployed environment. |

### 2d. AI settings (only when AI is wired, section 6)

`FOUNDRY_PROJECT_ENDPOINT` (Foundry project), `FOUNDRY_MODEL` (model deployment name), `AI_PROVIDER_CHAIN` (`foundry`, `foundry_connection`, `gateway`),
`AI_MODEL_ROUTER|NARRATOR|ANALYSIS` (model per role), `AI_AGENT_VERSION_PINS` (`AgentName=version,...`, rollback is a setting). Full list: `docs/architecture/ENV-VARS.md` section 8.

### 2e. Frontend

Vite reads `frontend\.env.local` (copy `frontend\.env.example`). `VITE_API_BASE` bypasses the dev proxy; `TCC_API_TARGET` (shell variable) points the proxy elsewhere; `VITE_BRAND_*` set the brand; the theme switch is `modern` (default) or `classic`.

## 3. Run the backend

Prerequisites: .NET SDK from `dotnet\global.json`, `az login` as an identity that can read the lakehouse SQL endpoint, and the Fabric capacity **Active**.

**Visual Studio**

1. `.\dotnet\configure-local.ps1` (once, and after editing `backend\.env`). It writes launch profiles for the API **and** the Worker (gitignored: they hold your host name).
2. Solution > Configure Startup Projects > Multiple startup projects: `TaxCredit.Api` = Start, `TaxCredit.Worker` = Start.
3. Pick `TaxCredit.Api - live lakehouse` and `TaxCredit.Worker - live lakehouse` and press Run.
4. Check `http://127.0.0.1:8000/api/ready`: `ready: true` and the account count.

**Terminal** (two terminals)

```pwsh
.\dotnet\run-local.ps1     # API on 127.0.0.1:8000
.\dotnet\run-worker.ps1    # Worker, polls the queue until Ctrl+C
```

`-Offline` on either script uses synthetic seed data and makes no Azure calls. `.\dotnet\run-worker.ps1 -Once` drains what is queued and exits.

## 4. Run the frontend

```pwsh
cd frontend
npm install        # first time, or after package changes
npm run dev        # http://localhost:5173, proxies /api to 127.0.0.1:8000
```

To use the modern theme, be on branch `feat/ui-modern-theme` (`git checkout feat/ui-modern-theme`), then hard-refresh (Ctrl+Shift+R).

## 5. Generate calculations for a client

There are two routes, and only one needs you to wait.

| From the UI | What happens | Wait on the page? |
|---|---|---|
| **Portfolio / Targeting**: select clients, **Run** | Previews, then queues a batch and takes you to **Runs** (`/runs/<batch>`). The **Worker** executes it. | **No.** Close the tab if you like; the batch continues. The Runs page polls while open and pauses when hidden. |
| **A client's trend grid**: Run | Calls `POST /api/v2/clients/{id}/runs`, which calculates inside the API request. | **Yes**, until it returns. |

Steps for a batch:

1. Make sure the Worker is running (section 3). If the Runs page says "queued runs in this batch are not progressing", the Worker is not running.
2. Select the client(s) and Run. Confirm the preview (a typed count is required above 25 items).
3. Watch **Runs**: items go `queued` > `running` > `succeeded` / `skipped` / `failed`. Failures show their cause and can be retried.
4. Results appear on the portfolio and on the client's pages.

Measured live on 2026-11-17 (before the S4 changes): one client, 384,433 payroll rows, program GA_JTC, tax year 2024, live lakehouse: **3 min 35 s** end to end
(about 28 s before the calculation starts, 79 s calculating, and about 108 s after it). The S4 profile (`RUN-PROFILE.md`) explains the last 108 s: SQLite
inserts of the Gold rows plus a fourth read of the payroll. Two fixes followed: inserts re-bind one prepared statement, and a calculation reads the
payroll once instead of four times.

Measured offline (`.\dotnet\bench-run.ps1`: synthetic client, fake source transport, real worker, SQLite; a shared 12-core workstation, so +/- 2x noise).
Live source latency is not in these numbers.

| Payroll rows | Before | After | Peak memory before / after | Stored Gold rows |
|---:|---:|---:|---:|---|
| 100,000 | 52 s (median of 3) | 19 s (median of 3) | 1.5 GB / 0.7 GB | hash-identical |
| 400,000 | 272 s | 94 s | 6.9 GB / 2.8 GB | hash-identical |
| 1,000,000 | 1,337 s | 534 s | 14.1 GB / 6.1 GB | hash-identical |

What remains is mostly the Domain run (engine, gold projection and unit replay: 66 s at 400,000 rows, several minutes at 1,000,000) and memory. Two things to know
above about 500,000 rows: the worker lease is 600 s (`RunExecutionOptions`), and the whole payroll is held in memory (about 7 KB per row after the fix). Plan on
minutes per client, not seconds.
From the command line (no UI): `POST /api/v2/clients/{id}/runs` with `{"year": 2024, "state": "GA"}` (synchronous), or queue with the Run dialog and drain with `.\dotnet\run-worker.ps1 -Once`.

## 6. Agents

**Prompt agents** (twelve, listed in `backend/agents/agents.json`; prompts in `backend/agents/prompts/`). Versions are immutable; an identical
definition is reused. The model comes from `FOUNDRY_MODEL` / `AI_MODEL_<ROLE>`, never from the repository.
**The .NET API does not publish them yet**: with `FOUNDRY_PROJECT_ENDPOINT` set it reports the provider `unavailable` ("No Foundry invocation factory is installed"),
and `/api/ready` shows `ai: disabled`. The Python backend publishes them in the background at startup (`FoundryAgentCatalog.warm`) when it has
`FOUNDRY_PROJECT_ENDPOINT`. **Unverified live** (no live publish has been run).

**Hosted agent** (the Teams / Microsoft 365 orchestrator, `channel_orchestrator/azure.yaml`). It needs the channel gateway deployed first.

```pwsh
python scripts/vendor-orchestrator.py               # copies the shared modules in (the zip needs them)
cd channel_orchestrator
azd env new <name>
azd env set FOUNDRY_PROJECT_ENDPOINT https://<account>.services.ai.azure.com/api/projects/<project>
azd env set CHANNEL_GATEWAY_URL <gateway url>
azd env set CHANNEL_GATEWAY_AUDIENCE <gateway audience>
azd env set TENANT_ID <tenant id>
# optional: FOUNDRY_MODEL (default gpt-4.1-mini), AI_PROVIDER_CHAIN (default foundry), CHANNEL_NAME, CHANNEL_IDENTITY_SOURCES
azd deploy
```

You need **Foundry Project Manager** on the project to deploy. To put it in Teams and Copilot (needs **Foundry User**, Azure Bot Service Contributor, `Microsoft.BotService` registered):

```pwsh
pwsh scripts/publish-m365.ps1 -WhatIf -ProjectEndpoint <endpoint> -AgentName tcc-channel-orchestrator -ResourceGroup <rg> -BotName <bot> -DisplayName "Tax Credit Copilot" -ShortDescription "..." -FullDescription "..."
pwsh scripts/publish-m365.ps1 <same arguments without -WhatIf>
```

Details: `docs/m365-channel/PUBLISHING.md`, `docs/m365-channel/ORCHESTRATOR.md`. **Unverified live**: those docs say `azd` has not been run against a subscription.

## 7. Data reads at billions of payroll rows

What is in place (`TaxCredit.Infrastructure.Sources`):

- A client's payroll is read with a parameterized `WHERE account_id = @p0`, so only that client's rows leave the SQL endpoint.
- Only columns the engine needs are selected.
- Dimension tables (location, address, employment, ...) are read by key in batches of 900, not scanned.
- Scope (years, states, dates) and the source fingerprint are computed by SQL aggregates, not by loading rows.
- Rows stream and the read stops at a size cap instead of after loading.
- The portfolio footprint is **bounded and guarded** (stage S1, `docs/SCALE-S1-REPORT.md`): it is read only for the clients on the page or in the batch, in `IN (...)` batches of 900 bound parameters, behind a row-estimate guard and a statement timeout. When it is refused the portfolio page still answers, with a `degraded` entry.

What is **not** in place, and matters at scale:

| Gap | Effect with billions of rows | Python had |
|---|---|---|
| Portfolio footprint: a refused, timed-out or switched-off read leaves the map and state filters empty (portfolio) or refuses the batch that needs it (planner). `auto` estimates rows from the SQL catalogue only; there is no Delta-log estimate, and no pre-aggregated summary yet. | Where clients operate is unknown above `PORTFOLIO_FOOTPRINT_MAX_ROWS` unless the mode is `on`. | Same settings, plus a Delta-log estimate and a one-hour decision cache |
| Per-client row cap is fixed at 1,000,000 (`SourceTooLarge`). | A client over 1M rows is refused. Candle Bottle is 384k. | `SOURCE_MAX_ACCOUNT_ROWS`, default 50M, configurable |
| No per-account dataset cache or version check; every run re-reads the client. | Repeat runs for one client pay the full read each time. | `SOURCE_CACHE_*`, `SOURCE_VERSION_CHECK_SECONDS` |
| No Silver (account-partitioned) table path. | The `account_id` filter only prunes well if the Payroll table is partitioned or clustered by `account_id`. | `SOURCE_SILVER` |
| `LoadPortfolioPayPeriods` loads every account's payroll into memory (used by entity simulation). | Not usable at this scale. | n/a |

Recommended next steps, in order: (1) serve the footprint from a small pre-aggregated summary table; (2) make the row cap a setting;
(3) partition or cluster the Payroll Delta table by `account_id`; (4) cache per-client datasets with a version check.

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| A run stays `queued` | The Worker is not running. Start it (section 3). |
| `/api/ready` not `ready: true` | Fabric capacity suspended, `az login` expired or wrong account, or `LAKEHOUSE_SQL_*` wrong. |
| "Workspace unavailable" | `FABRIC_WORKSPACE` / `FABRIC_LAKEHOUSE` missing from `backend\.env`; rerun `configure-local.ps1`. |
| Port 8000 in use | Another API (or the Python one) is running; stop it. |
| Table says "0 assessed" | Nothing has been calculated yet; operational state starts empty in the local SQLite file. |
