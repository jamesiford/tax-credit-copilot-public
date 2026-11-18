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
| `SOURCE_MAX_ACCOUNT_ROWS` | 1000000 | Most payroll rows one client may have; a bigger client is refused with a 422 naming this setting. Whole number, minimum 1000; anything else stops the host at startup. Memory is about 3.5 KB per row at peak (see `docs/SCALE-S2-REPORT.md`), so 1,000,000 rows needs about 3.5 GB. |
| `SOURCE_PORTFOLIO_MAX_ACCOUNTS` | 25 | Most clients a portfolio-wide payroll load (entity portfolio simulation) will read; a bigger book is refused before any payroll is read. Whole number, minimum 1. |
| `SOURCE_PORTFOLIO_MAX_ROWS` | 5000000 | Running payroll-row total a portfolio-wide load may not pass; checked per client from the SQL scope aggregate before that client's payroll is read. Whole number, minimum 1000. |
| `SOURCE_CACHE_MODE` | `off` | `off` or `on`. `on` keeps each client's projected payroll in memory between requests (stage S3, `docs/SCALE-S3-REPORT.md`). **An operator decision with a stated staleness window; read section 7 first.** `off` is exactly the previous behaviour: no cache, no extra query. Anything else stops the host at startup. |
| `SOURCE_CACHE_MB` | 512 | Estimated memory the cache may hold (an estimate of the row dictionaries, not a measurement). Whole number, minimum 16. Least recently used clients are dropped to fit. |
| `SOURCE_CACHE_ACCOUNTS` | 64 | Most clients the cache may hold. Whole number, minimum 1. |
| `SOURCE_VERSION_CHECK_SECONDS` | 300 | How long a matching source marker is trusted. Inside it a page read asks the source nothing; after it the next read takes the cheap marker again and reloads only if it changed. This is the **staleness window** for page reads. Whole number, minimum 1. Calculation runs ignore it. |
| `TCC_BULK_LOAD` | `on` | SQL Server-family stores only (Warehouse, Azure SQL): large inserts use `SqlBulkCopy` inside the publish transaction. `off` is the kill switch and restores multi-row INSERT statements (about 500 rows/s on the Warehouse). |
| `TCC_BULK_LOAD_MIN_ROWS` | 1000 | Inserts smaller than this keep using statements. |
| `TCC_BULK_TIMEOUT_SECONDS` | 3600 | Timeout of one table's bulk load. |
| `TCC_RETAIN_SUPERSEDED_RUNS` | 2 | How many superseded runs per client-program keep their employee-grain Gold rows (`employee_period_fact`, `onezero_matrix`, `employee_eligibility`); older ones are pruned after the publish commits. Whole number, minimum 1; `all` prunes nothing. Manifests and unit-level tables are never pruned. |
| `RUN_LEASE_SECONDS` | 600 | Queue lease of an item; a worker that goes silent for this long loses it. |
| `RUN_LEASE_RENEW_SECONDS` | a third of the lease | How often a running item renews its lease while it calculates and writes. Must be shorter than the lease. |
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
- Rows stream and the read stops at a size cap (`SOURCE_MAX_ACCOUNT_ROWS`) instead of after loading.
- The portfolio footprint is **bounded and guarded** (stage S1, `docs/SCALE-S1-REPORT.md`): it is read only for the clients on the page or in the batch, in `IN (...)` batches of 900 bound parameters, behind a row-estimate guard and a statement timeout. When it is refused the portfolio page still answers, with a `degraded` entry.

What is **not** in place, and matters at scale:

| Gap | Effect with billions of rows | Python had |
|---|---|---|
| Portfolio footprint: a refused, timed-out or switched-off read leaves the map and state filters empty (portfolio) or refuses the batch that needs it (planner). `auto` estimates rows from the SQL catalogue only; there is no Delta-log estimate, and no pre-aggregated summary yet. | Where clients operate is unknown above `PORTFOLIO_FOOTPRINT_MAX_ROWS` unless the mode is `on`. | Same settings, plus a Delta-log estimate and a one-hour decision cache |
| Per-client row cap is a setting (`SOURCE_MAX_ACCOUNT_ROWS`, default 1,000,000) but the default is deliberately not Python's 50M: at about 3.5 KB of peak memory per row a 50M-row client would need about 170 GB in one process (`docs/SCALE-S2-REPORT.md`). | A client over the cap is refused with a 422 whose remedy names the setting and the limit. Candle Bottle is 384k (about 1.4 GB). | `SOURCE_MAX_ACCOUNT_ROWS`, default 50M |
| Per-client dataset cache is **opt-in** (`SOURCE_CACHE_MODE=on`, default `off`; stage S3, `docs/SCALE-S3-REPORT.md`). With it off every read re-reads the client. | Repeat reads and runs for one client pay the full read each time unless an operator turns the cache on. | `SOURCE_CACHE_*`, `SOURCE_VERSION_CHECK_SECONDS` (on by default) |
| No Silver (account-partitioned) table path. | The `account_id` filter only prunes well if the Payroll table is partitioned or clustered by `account_id`. | `SOURCE_SILVER` |
| `LoadPortfolioPayPeriods` (entity portfolio simulation) still holds every account's projected rows at once, but is now bounded: it refuses before reading when the book has more than `SOURCE_PORTFOLIO_MAX_ACCOUNTS` (25) clients or the running row total passes `SOURCE_PORTFOLIO_MAX_ROWS` (5,000,000). | A larger book gets a 422 `portfolio_too_large` telling the caller to select fewer clients. The default row bound is still about 13 GB of projected rows, so lower it on a smaller host. | n/a |

Recommended next steps, in order: (1) serve the footprint from a small pre-aggregated summary table; (2) cut the per-row projection cost
(the engine's dictionary row is 2.6 KB of the 3.5 KB, `docs/SCALE-S2-REPORT.md`); (3) partition or cluster the Payroll Delta table by `account_id`;
(4) decide whether to turn the per-client cache on (below).

### Persisting a run to the Warehouse (stage S5, `docs/SCALE-S5-REPORT.md`)

Measured on the live Fabric Warehouse with `SqlBulkCopy` (one connection, inside the publish transaction), synthetic client, `employee_period_fact` rows: 100,000 rows 37 s, 400,000 rows 58 s, 1,000,000 rows 99 s in total
(the `employee_period_fact` table itself 7.7 s, 28 s and 63 s). The multi-row INSERT path it replaces took more than 35 minutes for a 384,418-row client. A running item now renews its queue lease on a timer, so a write that
outlasts the lease no longer loses it. If a Warehouse ever rejects the bulk protocol, set `TCC_BULK_LOAD=off`.

### The per-client projection cache (`SOURCE_CACHE_MODE`, off by default)

Payroll rows are deliberately **not** cached unless an operator turns this on. With `SOURCE_CACHE_MODE=on` one process-wide, bounded LRU
(`SOURCE_CACHE_MB` estimated bytes **and** `SOURCE_CACHE_ACCOUNTS` clients) holds each client's finished projection, so the runs, scope,
eligibility and trend reads of one client share one read of the lakehouse. Concurrent requests for one client run one read.

- **Inside `SOURCE_VERSION_CHECK_SECONDS`** a page read asks the source nothing. **After it** the next read takes a cheap marker (the
  fingerprint: payroll row count, maximum `modify_date`, the Payroll column mapping, plus a digest of the active pay-code lookups) and keeps
  the entry only if it still matches.
- **A calculation run, a queued run step and a claim assessment always take a fresh marker** and ignore the window, so the manifest's source
  observation (taken uncached at write time) stays truthful and a run never trusts the clock.
- A failed read, a client over `SOURCE_MAX_ACCOUNT_ROWS` and an unknown client are never cached. `SqlClientSource.ClearCache()` empties it.
  Restarting the host empties it. Nothing is written to disk.
- Hits, misses, evictions, reloads, entries and estimated bytes are on the OpenTelemetry meter `TaxCredit.SourceCache`
  (`tcc.source_cache.*`). No client id is a label.

**Staleness statement.** A page read can be up to `SOURCE_VERSION_CHECK_SECONDS` behind the source. After that, a change is detected **only**
if it changes the Payroll row count, the maximum `modify_date` (and where `modify_date` is entirely null, only the count can detect a change),
the Payroll column mapping or the active pay-code lookups. **Not detected, until a restart or `ClearCache()`:** an update that keeps both the
count and the maximum modified date; any change to the dimension tables (Entity, Location, Address, StateCountyZip, PayCode, Employment, fiscal
rules, pay frequency), which the marker does not look at; SQL endpoint synchronization lag; and the gap between the marker and the rows being
two separate observations. A run carries the same undetected classes; it only refuses to be served from the clock. Turn the cache on only
where those are acceptable for the data, and keep the window short for a source that is edited in place.

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| A run stays `queued` | The Worker is not running. Start it (section 3). |
| `/api/ready` not `ready: true` | Fabric capacity suspended, `az login` expired or wrong account, or `LAKEHOUSE_SQL_*` wrong. |
| "Workspace unavailable" | `FABRIC_WORKSPACE` / `FABRIC_LAKEHOUSE` missing from `backend\.env`; rerun `configure-local.ps1`. |
| Port 8000 in use | Another API (or the Python one) is running; stop it. |
| Table says "0 assessed" | Nothing has been calculated yet; operational state starts empty in the local SQLite file. |
