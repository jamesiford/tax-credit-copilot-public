# Run orchestration: running many clients

How to recalculate more than one client: one, a list, a filtered group or everyone, as tracked work with progress,
retry and cancel. The design is [ADR-012](ADR-012-run-orchestration.md). The single-client controls
(`POST /api/v2/clients/{id}/runs`, `POST /api/claims/assess`, "Run assessment" and "Run TY… now" in the portal) are unchanged.

## The model in one minute

- A **batch** is a request: what to do (`assess`, `calculate`, or `assess_and_calculate`), for which clients, which years.
- An **item** is one client, and optionally one tax year. With no years given there is **one item per client** and its
  year is the client's latest runnable year, resolved when the item starts. (A run replays and writes every authored year
  of the client's payroll whatever year it is asked for, so one item per client does the work once.)
- A **worker** leases queued items, runs each through the existing commands (`RunClientCalculationCommand`,
  `AssessClientCommand`), and records the outcome. It does not reimplement a calculation.
- The queue is two tables in `tcc_ops` (`run_batch`, `run_batch_item`, migration `0004`), beside the run manifest. A run an
  item produced is linked by `run_id`.

| Kind | What each item does |
|---|---|
| `assess` | Records claims for the client (no Gold write). |
| `calculate` | Runs the calculation and writes Gold, and records the claim for that year. |
| `assess_and_calculate` | Runs the calculation and records claims for every year (what the single-client endpoint does by default). |

## Start a batch

`POST /api/v2/run-batches` (a person's token; the channel gateway's agent token is refused here, and starts batches through
the Microsoft 365 capability instead).

```json
{ "kind": "calculate",
  "scope": { "kind": "filter", "filter": { "band": "exposed", "state": "GA" } },
  "dry_run": true }
```

- `scope.kind`: `one` or `list` (`client_ids`), `filter` (the portfolio filters `program`, `year`, `outcome`, `scope`,
  `status`, `near`, plus `band`, `state`, `unassessed`, `unavailable`), or `all`. A filter is resolved on the server from the
  client book, claims and manifests. **No payroll is read to choose clients.**
- `dry_run: true` previews and writes nothing. Preview first.
- Above `RUN_BATCH_CONFIRM_ABOVE` items (default 25) the start needs `confirm_items` equal to the item count. Above
  `RUN_BATCH_MAX_ITEMS` (default 5000) it is refused; only scope `all` may override, with `override_size_limit`.
- `idempotency_key` makes a repeated request return the first batch. Without a key, an identical request that is still queued
  or running returns that batch.
- `tax_years` makes one item per client-year. Each of those replays every year, so the cost is N times higher. `refresh_once:
  false` requires explicit years for the same reason.
- `force: true` runs even when the last run still answers (see below).
- **Bounds** (a request over one is a 422 naming it, never a truncation): at most 50,000 `client_ids`, 12 filter keys whose values are short
  text (64 characters), numbers or true/false, 12 `tax_years` and a `program_code` of 64 characters, because the scope and years are stored
  in bounded columns.

## What "skipped" means

An item is **`skipped_unchanged`** only when the latest successful manifest for that client and programme is for the same
year and the calculation fingerprint (`calculation_id`, which digests the year's payroll rows, the floors and the assumption
ids), both assumption-set hashes and the rule pack version are all recorded and all equal. If any value is missing on
either side, or the manifest is for a different year, the answer is "cannot tell", and the item **runs**. `code_commit` is
compared only with `include_code_commit`. The check runs when the item starts (it loads that client-year's rows, which costs
less than the engine and the Gold write). The preview can only state an **upper bound** on skips; it never promises one.

An item is **`skipped_no_payroll`** when the data or statute cannot support it: no payroll in the fiscal window, no authored
statute for the year. It is a statement with the reason, never a failure and never a zero.

Limit worth knowing: a run refreshes Gold for every year but records a manifest for one, so "unchanged" speaks for the year
the manifest names. A change to another year's payroll is picked up the next time that year is the one being run, or by
`force`.

## Watch, cancel, retry

| To do | Call |
|---|---|
| Status and counters, with a degraded `run_worker` entry when nothing is working the queue | `GET /api/v2/run-batches/{id}` |
| Items, filterable by status | `GET /api/v2/run-batches/{id}/items?status=failed` |
| Recent batches | `GET /api/v2/run-batches` |
| Cancel | `POST /api/v2/run-batches/{id}/cancel`: queued items are cancelled; an item already running finishes |
| Retry | `POST /api/v2/run-batches/{id}/retry-failed`: only `failed` items return to the queue |

Batch status: `queued`, `running`, then `succeeded` (including all-skipped), `partial` (some failed or were cancelled),
`failed`, or `cancelled`.

## Run the worker

```powershell
python -m bootstrap.run_worker          # from backend/, until stopped
python scripts/run-worker.py --once     # from the repo root: drain the queue and exit
```

- **Locally** the API starts a worker thread by itself (`RUN_WORKER_INLINE` defaults to true only when
  `ENVIRONMENT=local`). To use a separate local worker, set `RUN_MANIFEST_STORE=sqlite` so both processes share one queue
  file (`memory` is private to a process).
- **Deployed**, run the worker as its own process: any number may run. Leases keep two workers off one item, and a per-client
  rule keeps one client from running twice at once. Terraform can deploy it (default off, see below).
- `RUN_WORKER_INLINE=true` in a deployed API is for a **single-instance trial only**: when the API scales out every instance
  would run a worker. The process logs a warning when it is set.

## Sizing and concurrency

- `RUN_WORKER_CONCURRENCY` (default **1**, maximum 8) is items in flight per worker. It defaults to one because the per-client lock on a Warehouse is narrowed, not airtight, and concurrent Gold writes have not been measured live. Each run holds one client's payroll in memory and
  is CPU-bound, so raise it with care. On the Fabric Warehouse, two runs writing Gold at once can conflict (error 24556); the
  writer retries, and an item that still fails is retried by the job with backoff. To raise it, watch the retry counts for errors 24556, 3960 and 1205; if they climb, use 1. Azure SQL
  conflicts less. **This has not been measured on a live Warehouse** (see `live-checks.md` in the build analysis).
- Retries: `RUN_ITEM_MAX_ATTEMPTS` (default 3), only for transient failures, with capped exponential backoff and jitter.
- A worker that dies loses nothing: its leases lapse (`RUN_LEASE_SECONDS`, default 120) and the items return to the queue.

## A separate worker identity (optional)

By default the worker runs as the API's identity. To give it less, create a second user-assigned managed identity for the worker app and set
`RUN_WORKER_IDENTITY_CLIENT_ID` to its client id (the worker process then runs as it; Terraform defaults are unchanged and nothing here is
applied by the build). The worker calls the same commands as the API, so it needs exactly what a run needs and nothing the portal needs:

- **Read payroll:** the Fabric workspace role that lets it read the lakehouse (read through OneLake), and for the SQL path the `lakehouse` profile
  of `scripts/grant-warehouse-sql.py` (SELECT on the source tables).
- **Write Gold and Ops:** the `api` profile of the same script (read and write on `tcc_gold` and `tcc_ops`).
- **No draft or portal grants:** the `api` profile grants whole schemas, so deny the tables the worker never touches:
  `DENY SELECT, INSERT, UPDATE, DELETE ON OBJECT::<ops schema>.program_draft TO [<worker identity>];` and the same for `program_draft_document`,
  `program_draft_event` and `channel_audit`. A T-SQL DENY on an object overrides a schema GRANT.
- No Entra app role, no `TCC.User`, no Graph permission: the worker serves only `/healthz` and calls no user-facing API.

Check it: start the worker and drain one small batch (live checks 5 and 6), and confirm `SELECT ... FROM <ops schema>.program_draft` is refused
for the worker identity. This was not exercised against a live Warehouse in the build.

## Failure signatures

| You see | It means | Do |
|---|---|---|
| Degraded `run_worker` on a batch | Items are waiting and no worker holds a lease | Start a worker (above) |
| Item `failed`, dependency `operational_store`, `source_lakehouse` or `source_sql` | The store or source was unreachable and attempts ran out | Fix connectivity, then retry-failed |
| Item `failed`, dependency `gold_write` | The Gold write did not validate (section 9: for example more than one current run for a client and program) | The worker retries it once with no other worker on the client; a second failure stays failed. Run the client alone, then check section 9 (`python backend/tools/verify_gold_reads.py`) before trusting its figures |
| Item `failed`, dependency `conflict` | A Warehouse write conflict persisted | Lower `RUN_WORKER_CONCURRENCY`, then retry-failed |
| Item `failed`, dependency `lookup:<name>` | The client needs a lookup authored (pay codes, fiscal rules) | Author it; not retried automatically |
| Item `failed`, dependency `validation` | The request or the client is ambiguous (for example several programmes) | Name the `program_code` |
| Item `failed`, dependency `worker` | The worker died and attempts were spent | Retry-failed |
| Item `failed`, dependency `internal` | A bug; the log has the trace | Report it |

An item stores a typed cause (the dependency above) and a fixed remedy sentence, never the raw error text, which can echo a request value or a
host name. The raw message is in the worker's log (logger `tcc.runs`).

Settings are in [ENV-VARS.md](ENV-VARS.md) section 4a.

## Deploying the worker (Terraform, default off)

`enable_run_worker = true` (default `false`) adds one App Service on the same plan, `app-tcc-worker-<suffix>`, in the same integration
subnet, running **as the API's identity** with the API's settings plus `RUN_WORKER_INLINE=false` and `RUN_WORKER_CONCURRENCY`
(`run_worker_concurrency`, 1 to 8, default 1). It needs no new grants: it calls the same commands, so it needs the API's access. With it
off the plan is unchanged (a Terraform test proves it). `RUN_WORKER_APP_NAME` is the output that names it.

The build only validates and tests the module (`terraform validate`, `terraform test`); it never applies it. Deploying is yours:

```powershell
azd env set TCC_ENABLE_RUN_WORKER true      # then add enable_run_worker to infra/main.tfvars.json's mapping, or set TF_VAR_enable_run_worker=true
azd provision
python scripts/package-app.py backend worker.zip
az webapp deploy -g <resource group> -n <RUN_WORKER_APP_NAME output> --src-path worker.zip --type zip
```

The worker is not an azd service for the reason the channel gateway is not: azd cannot make a service conditional. It starts
`worker-startup.sh`, which runs `python -m bootstrap.run_worker --health-port $PORT`, so the platform's probe has something to ask.

A **single-instance trial** without a second app: set `RUN_WORKER_INLINE=true` on the API. It logs a warning, and it is unsafe the
moment the API scales out (every instance would work the queue; the leases keep correctness, but the load is multiplied).
