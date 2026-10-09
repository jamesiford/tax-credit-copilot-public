# Tax Credit Copilot

Continuous eligibility, discovery and audit-defensible calculation for US
job-creation tax credits, computed directly from payroll.

**This is a production build, not a prototype.** Read
[`docs/architecture/TARGET-ARCHITECTURE.md`](../docs/architecture/TARGET-ARCHITECTURE.md)
for where it is going and how far along it is. The ADRs in `docs/architecture/`
constrain the code; where this file and an ADR disagree, the ADR wins.

---

## The one rule that matters most

The reference dataset must always produce **10,236 employees · 539 Min-Max
eligible · 656 Pay Period eligible**. These are reconciled with the partner
(30 July – 24 August 2026).

```pwsh
cd backend ; $env:TCC_REQUIRE_PARITY=1 ; pytest tests/ -q
python backend/tools/verify_reference_independent.py       # 17/17, exits 2 if fixtures absent
```

- `tests/test_engine_parity_reference.py` is the gate. **Never edit the pinned
  constants to make it pass.** A change that moves them is either a genuine
  improvement needing re-reconciliation with the partner, or a bug.
- The figures are defined twice on purpose: `tests/certified.py` holds them as
  literals, `rules/methodology/certified-figures.json` is the production-readable
  copy the runtime equivalence gate needs.
  `tests/test_certified_figures_contract.py` fails if they drift.
- `verify_reference_independent.py` is **not redundant**. It was written without
  reference to the implementation and has caught two bugs the suite did not.
- `TCC_REQUIRE_PARITY=1` turns a missing-fixture SKIP into a collection
  ERROR, so the gate cannot report a false pass. Set it wherever the fixtures exist.

---

## Architecture rules

### Layering — enforced, not described

`tests/test_architecture.py` has seventeen rules that fail the build. Read it
before moving code. The essentials:

- **`presentation → application → domain`.** `infrastructure` implements ports
  the domain declares. Dependencies point inward only. [ADR-003]
- **The domain layer imports nothing but the stdlib and its own siblings.** No
  repository, connection, framework, or async. That purity is what keeps the
  parity gate a fast unit test rather than an integration test. It does not
  import `tools/` either — if the domain needs a type, the type belongs in the
  domain, which is why `StatutoryFloors` lives in `domain/calculation/floors.py`
  and `tools/credit_math.py` re-exports it.
- **`api/` routers are thin.** Parse, dispatch, shape the response. No statutory
  math, no row mutation, no multi-step business logic in a route.
- **`tools/` is deterministic compute.** Data in, data out, calculation-trail
  rows recorded. Never imports from `api/`. This is the audit boundary.
- **Composition lives in `application/wiring.py`.** Repository selection is
  there, not in a router. A use case that has to import `api.claims` to find its
  own store drags FastAPI into every caller. The one remaining exception,
  `api/_assess.py`, is allow-listed by name in the architecture test with the
  reason — it is an application service still filed under `api/` because it
  depends on `api/_payperiods.py`, a payroll reader that raises `HTTPException`.
  Moving both is tracked work; do not add a second exception.
- **Writes are commands, reads are queries.** Every write lands on a number on a
  filed return, so it goes through the mediator pipeline: **Validation →
  Handler → Audit**, timed. One use case per file, named for the use case.
  - **That is the whole pipeline.** Authorization and TenantScope are *not*
    stages — there is no identity to authorize and no employer binding to scope
    to. They are absent rather than stubbed because a stage that runs and
    always passes reads as a control, and an auditor would find a name where an
    enforcement should be. Gated on Entra; see [SECURITY.md](../SECURITY.md).
    `test_the_pipeline_does_not_claim_stages_it_does_not_have` fails if a no-op
    is added to satisfy a diagram.
  - **The audit trail records failed writes too.** "Somebody tried to resolve
    this finding and it errored" is a question that gets asked, and a trail of
    successes cannot answer it. `AuditLog` is bounded and in-memory — a support
    aid, not the destination; the durable trail is `tcc_ops.agent_action_audit`
    plus the run manifest.
  - **An unattributed write says so.** `actor` defaults to `system`, and a
    reader cannot tell that from a service account that genuinely made the
    change — so `AuditRecord.attributed` states it rather than leaving it to be
    inferred from a string.

### The API surface is a decided set, not an accumulation

`tests/route_inventory.json` pins all 67 routes. Adding one means updating the
inventory in the same commit; removing one means saying so out loud. The file
exists because a router split once dropped nine endpoints silently — the modules
still imported, the unit tests still passed, and only a client found the 404.

### Agents narrate. Tools calculate.

No figure is ever produced by a language model. Deterministic Python computes;
the orchestrator captures the result and hands the agent a JSON brief. Agents
hold no tools. [ADR-004]

**The honest limit:** this prevents an agent *computing* a number, not
*misstating* one — prose streams unvalidated. Anything shown to a customer must
render from canonical values.

### Statute is versioned by tax year

[ADR-005]. A rule pack is scoped to `(program, tax_year)` and **materialised** —
`rules/ga_jtc/2023.json` is a complete resolved file, not a base plus overlays
merged at run time. The question an authority asks is *"what rules did you apply
to my 2021 return?"* and the answer must be a file with a hash.

- **Resolution fails loudly.** `load_year_pack` returns that year or raises. It
  never falls back to a neighbour. A missing ruleset is a real gap in coverage.
- **EVERY statutory value follows the year, not just the floors.** The
  eligibility floors were always year-resolved; the BENEFIT was not —
  `_replay_unit_series` read `_year_benefit(program, years[-1])` once and priced
  a six-year series with it, so a TY2020 credit was valued at TY2025's rate.
  `compute_base_year_tranches` now takes `benefit_by_year`, and `TrancheYear`
  carries the rate that priced it. **A tranche holds the rate of the year it
  OPENED** — the rate attaches to the job at creation, so a later year must not
  reprice a window already running.
- **A per-year defect is invisible against the live packs.** Georgia has held
  $3,500 per job, a 2-job threshold and a 5-year tranche across every authored
  year, so nothing in `rules/` can catch a regression here. `test_baseyear.py`
  passes rates that differ ON PURPOSE; without those the engine could go back to
  reading one year's statute for a whole series and the suite would stay green.
- **A year absent from `benefit_by_year` falls back to the scalar, never to a
  neighbouring year.** Inheriting statute across years is the thing year packs
  exist to prevent.
- A negotiated designation is a CURRENT fact about a location and still
  overrides the pack threshold in every year. Prototype data (DISC-10).
- Migration is **per-program**: a program with a `rules/<program>/` directory is
  year-scoped and strict; the rest stay flat and return `year_resolved=False`.
- **`rules_ingestion` may FILL a value a pack lacks; it may never OVERRIDE a
  year-resolved one.** The ingested config is not year-aware.
- **Never invent statute.** An unauthored year is `_prototype_verify` with the
  source to verify against named explicitly. Placeholders must look like
  placeholders; a year's *basis* carries `null`, never a plausible guess.

### Four things freeze, and they are different artifacts

Program definition (statutory amendment) · eligibility parameters (annual,
administrative — DOL wage tables, DCA tier maps) · methodology (BA-01..BA-12,
the assumption set) · payroll (per client, per fiscal year).

A statutory value like the $636 TY2023 floor belongs in a **year pack**, never in
an assumption set — putting it there makes a new tax year look like a method
change and the version history becomes unreadable.

### Assumption sets are immutable, and freeze methodology only

`rules/methodology/reference-*-assumptions.v*.json`. Never edit a published set;
create the next one. Active: `GDS-STEP1-2026-08-25-v8` with
`GDS-ONEZERO-2026-08-24-v7`. A version moves when its artifact changes, not for
symmetry. v1–v7 are retired and **not runnable** — see `RETIRED_ASSUMPTION_SETS`;
there is deliberately no legacy read path. A superseded methodology can still be
exercised via `tests/assumption_variants.py`.

### Fiscal window and tax year are different quantities

- A **fiscal window** is a fact about a client: begin and end dates, read from
  `EntityFiscalYearRules`. `infrastructure/payroll/fiscal_source.py`.
- A **tax year** is a label an authority assigns. Georgia reg
  110-9-1-.02(1)(a) labels by the year a window **begins**; the business
  convention labels by the year it **ends**. They agree only for calendar filers.
- The convention is a **statutory fact**, authored per program in the rule pack's
  `tax_year_convention` block — not a client setting. `domain/calculation/fiscal.py`.
- `domain/calculation/onezero.py:fiscal_year_of` returns the **business** label
  and is not a statutory function. Nothing resolving a floor may call it.
- **PILOT-07 is open** — the convention is read from the regulation and not yet
  confirmed by the partner. Flagged `unconfirmed`, surfaced in the UI, and marked
  by an xfail in `tests/test_ga_wage_table.py`. Do not settle it unilaterally.

### Every figure carries its derivation

`{step, inputs, formula, output, citation}` plus a SHA-256 over the trail. See
`docs/architecture/CALCULATION-PROVENANCE.md`. `tools/trail.py` holds the
`ContextVar` recorder.

### A read READS. The engine runs at write time

Gold is the display layer, not a cache of it. A page load runs no engine.

- **The engine belongs in `run_client_calculation`.** `get_eligibility` and
  `get_onezero_matrix` used to replay both certified methods over the client's
  whole payroll on EVERY page load — 10,236 employees, GIL-bound, on a capacity
  where one statement costs ~300ms. Both now read `employee_eligibility` and
  `onezero_matrix`, which the run already wrote.
- **ClientPage ran THREE replays, and the claim above was false for a week.**
  `ProgressView` renders unconditionally, and `get_in_year_progress` replayed
  Min-Max for the cohort plus Pay Period twice inside `project_state_year_end`
  — 61 seconds for the reference client on the proximity call alone. All three
  are reads now: the cohort from `employee_eligibility`, the monthly series from
  `unit_month_summary`, the prior-year base from `run_method_summary`.
  **The forecast itself still computes**, because projecting to an arbitrary
  as-of date derives something no run holds. That is the line: re-deriving a
  certified figure is forbidden, deriving a new one is the feature.
- **A bounded fetch needs a NECESSARY condition, not a heuristic.** The cohort
  reads only `avg_weekly_hours >= min_hours - B`, which is safe because the
  lever is `max(hours_gap, wages_gap / rate)` and therefore never smaller than
  `hours_gap`. 61s → 6.2s, with every band identical.
  `test_the_hours_bound_never_drops_a_reachable_employee` is the proof; without
  it the read silently hides people who could qualify.
- **The reported denominator must be the one the average used.** The YTD figure
  moved to the run's real `month_ends` while `project_state_year_end` kept
  deriving `months_elapsed` from 1 January, so the reference client showed an
  average over EIGHT months beside a note claiming twelve. "Change the
  denominator from 12 months to 8 or 9" is the whole view; a wrong one there is
  not cosmetic. `months_elapsed` travels with `ytd_average_headcount`.
- **Bounding the ROWS must not bound the COUNTS.** "24 of 9,541 considered" is
  the sentence, and the denominator is the honest half. `near_miss_cohort` takes
  `population` for exactly this reason — a count quietly taken over a filtered
  set is the failure this parameter exists to prevent.
- **Recomputing a certified number is a second opinion about it.** `eligible` is
  READ from the run that decided it, under the rule pack that run recorded.
  `passed_hours` / `passed_wages` are derived for display only, because they
  decompose the stored verdict rather than replacing it.
- **`eligible` is NOT "cleared both floors".** `_eligibility_filter` sets
  `eligible = weight > 0`, and a part-time band carries a non-zero weight for
  someone who FAILED the hours floor — South Carolina, 20-32 hrs at 0.5.
  Deriving the verdict from the floors reported every SC part-timer as a near
  miss the run had already counted, then offered a lever to fix someone who was
  not broken. `assess_employee` prefers a recorded verdict wherever one travels
  with the row. Georgia has no band, so nothing on the reference client moves —
  which is why this survived so long.
- **Drift is detected from the ROWS, not from a version string.**
  `run_manifest.rule_pack_version` stores the pack's PATH, and re-authoring a
  materialised year pack changes its contents but not its filename; it is also
  stamped once per RUN while a run spans many years, so it reads `2025.json`
  beside a TY2023 answer. Absent a part-time band, `eligible` must equal
  "cleared both floors" — any row where it does not means the ruler moved.
  `statute_matches_run` reports that count on both reads.
- **An aggregate aliased to a name in `_BOOL_COLUMNS` is silently collapsed.**
  `SUM(...)` under the alias `eligible` came back `True`, and `int(True)` is 1 —
  539 eligible employees reported as one, on a screen where nothing else looked
  wrong. Mirror image of the `_MONEY_COLUMNS` trap.
  `test_no_aggregate_is_aliased_to_a_bit_column_name` guards both.
- **`record_token` is read, never re-minted on a read path.** The run minted it;
  re-deriving it is a second implementation of the one value that must not
  disagree.
- **The write path must cover every year the read path can select.** The replay
  computed `all_averages`, `total_hours_and_wages` and `employee_unit_matrix`
  for every year and persisted only the unit grain, so `unit_year_master` held
  six years while `employee_eligibility` held one — which is precisely why the
  read had to recompute. `employee_period_fact` is widened too: it is what
  places an employee at a worksite, so without it the near-threshold cohort is
  empty in every year but one. **Writes are allowed to be slow; a page that
  cannot answer is not.**
- **`tcc_gold.run_method_summary` holds what only the RUN knew** — annual
  average, eligible count, matrix rows, and `contested_months`. That last one
  cannot be recovered from any other table: the matrix is deduped before it is
  written, so a contest leaves no trace in the rows it produced. Candle Bottle
  TY2023 is 32 under Min-Max and 0 under Pay Period.
- **A client-year no run has reached is `not_calculated`, never zero.** Two more
  views can now reach that state; both render the statement rather than a page
  of zeroes.
- `tools/backfill_gold.py` reports the per-table year coverage and closes it.
  `tools/verify_gold_reads.py` proves the certified figures come back from Gold.
- **A read that answers from Gold uses `resolve_statute`, not
  `resolve_client_run`** — it needs the programme, floors and fiscal window to
  state them, and no payroll at all.

### Summing money is the warehouse's job

`domain/coverage.totals_by_program` exists because the account grid reduced
`opportunity_usd` across each row in the browser — the one dollar on that screen
that was re-derived instead of read, and re-derived as a float. Row totals are
summed as `Decimal` and returned as strings, like every other figure.

A row NEVER nets an opportunity against an exposure. Netted, both read zero and
the row looks like nothing to discuss.

### Deploying is `azd up`, and it is idempotent

Provision → package → deploy, then `postprovision`. `azd deploy` alone only
pushes code. `azure.yaml` uses the **Terraform** provider over `infra/`
(root plus `modules/`); `TCC_PROFILE` (`public` | `enterprise`) selects the
profile, `infra/main.tfvars.json` maps azd values into variables, and
`infra/locals.tf` holds the profile matrix. Both services are **App Service
(Linux)** apps on one plan, code-deployed — there is no container registry
and no image to pin.

- **`scripts/postprovision.ps1` runs after every provision, in order:**
  `apply-migrations.py` (the DDL bootstrap ONLY on a Warehouse Terraform just
  created, otherwise pending migrations), the synthetic source load (public
  profile only), `grant-warehouse-sql.py`, then `seed-operational-store.ps1`.
  A failed step fails the hook.
- **Idempotent means two checks, both zero.** `terraform plan
  -detailed-exitcode` returns 0 after an apply, and `apply-migrations.py`
  reports 0 pending on a re-run. The bootstrap is destructive and never
  re-runs on a Warehouse that already holds `tcc_ops.schema_migration`. [D22]
- **Every store is `warehouse` in every deployed environment** —
  `CLAIM_STORE`, `FINDING_STORE`, `RUN_MANIFEST_STORE`, `OVERRIDE_STORE` and
  `ARTIFACT_REPOSITORY`, with `ARTIFACT_STORE=blob`, all set by Terraform in
  `infra/main.tf`. They hold decisions that land on a filed return.
  `application/deployment.py` refuses to start a deployed process
  (`ENVIRONMENT` != `local`) on `sqlite`, `memory` or `local` rather than
  falling back: SQLite on App Service writes to a filesystem the platform may
  discard. Cosmos DB is gone. [ADR-007, superseding ADR-002]
- **Terraform never registers resource providers.**
  `resource_provider_registrations = "none"` in `infra/providers.tf`:
  registration is a subscription-wide change a customer subscription usually
  forbids. The operator registers them up front.
- **The Foundry role is assigned by GUID**, not by name
  (`53ca6127-db72-4b80-b1b0-d745d6d5456d`, `infra/modules/foundry`). Microsoft
  renamed *Azure AI User* to *Foundry User*, and a name lookup fails on a
  tenant that only carries the new name.
- **Foundry is purged on destroy.** A deleted AIServices account sits in
  soft-delete for 48 hours holding its subdomain, and azurerm's purge flag
  does not reach an azapi resource — so `azapi_resource_action.purge_on_destroy`
  does it explicitly. `azd down --purge` leaves nothing soft-deleted.
- **`.webappignore` keeps `.env` and payroll out of the package.**
  `backend/.webappignore` and `frontend/.webappignore`. Without them azd zips
  the whole folder, gitignored files included.
- **Set `GIT_COMMIT` in the azd env.** Terraform passes it to the API, which
  stamps it on every run; without it a run records `working-tree`.
- **Fabric Warehouse access is not Azure RBAC.** It is granted by a Fabric
  workspace role plus T-SQL grants on the Warehouse; Subscription Owner alone
  reads nothing.
- **Agent registration must stay idempotent.** Foundry agent versions are
  immutable, so `create_version` always creates, and registration runs on
  every startup — every restart, deploy and scale-out. `factory.py` reuses an
  identical definition and only publishes when the prompt changes.
- **Grants Terraform cannot always express**, and a deployed app needs all of
  them: the Fabric tenant setting allowing service principals to use Fabric
  APIs (Terraform cannot set it); the workspace role, which the `fabric`
  provider grants when `manage_fabric_access` is on (public default) and a
  script or the operator grants when it is off (enterprise default); and the
  T-SQL grants on `tcc_gold` / `tcc_ops`, from `scripts/grant-warehouse-sql.py`.
  Missing any fails every data path while `/api/health` stays 200.

---

## Stack

- **Hosting:** two **App Service (Linux)** apps on one plan. `api` runs Python
  3.12 under gunicorn with uvicorn workers (`backend/startup.sh`,
  `--timeout 600`); `/api/health` and `/api/ready`. `web` runs Node 24: an
  Express BFF in `frontend/server/` that serves the built SPA, proxies `/api`
  to the API and forwards the Easy Auth token as `Authorization: Bearer`.
- **Backend:** Python 3.12+, FastAPI, uvicorn, SSE for streaming.
- **Frontend:** React 18 + Vite + **JSX, not TypeScript**. Hand-rolled
  `index.css` design system. `npm install --legacy-peer-deps` —
  `react-simple-maps@1` peer-locks to React 16; `frontend/.npmrc` sets it.
- **Infrastructure:** Terraform in `infra/` — `azurerm`, `azapi` (Foundry) and
  `fabric` providers, deployed through `azd`. Profiles `public` | `enterprise`.
- **Agents:** `agent-framework-foundry`, `azure-ai-projects` (GA v2 SDK).
  Agents created with `project_client.agents.create_version(name,
  definition=PromptAgentDefinition(...))`. Invoke with
  `await agent.run(prompt, stream=True)` — there is no `.run_stream()`.
- **Auth:** `DefaultAzureCredential` everywhere. No keys in code or `.env`.
  User sign-in is `AUTH_MODE` `none` | `entra`: Easy Auth on `web`, bearer
  validation on `api`.
- **Data:** payroll from the Fabric **Lakehouse** (OneLake, Delta, read via
  `deltalake[pyarrow]`). Operational and Gold data in the Fabric **Warehouse**
  only, schemas `tcc_gold` and `tcc_ops`, over T-SQL (`pyodbc`). DDL is
  `docs/data/schema/tcc-schema.fabric.sql`; changes are forward-only
  migrations applied by `scripts/apply-migrations.py`. [ADR-007]
- **Artifacts:** Blob Storage (containers `artifacts` and `outputs`, private
  endpoint, shared key and public access off) behind the artifact service —
  `application/artifacts.py`, `api/artifacts.py`. The claim package is built
  by `application/claim_package.py`. Every download is audited in
  `tcc_ops.artifact_access`, and no SAS reaches a browser.

### Data sources — `DATA_SOURCE` in `backend/.env`

| Value | Reads | Scope |
| --- | --- | --- |
| `lakehouse` | Fabric lakehouse source schema (`SOURCE_SCHEMA`, default `tcc_source`) | **The default and the only shape the product ships against.** Five accounts, 564,931 rows, TY2020–TY2026. `flex` is a deprecated alias that resolves identically and logs a `DeprecationWarning` — the schema used to be named after the customer's internal shape |
| `fabric` | Flattened `dbo/employees` | An early slice, kept only because ingestion tests exercise it |
| `csv` | Local file | **A TEST FIXTURE, not a data source** |

**`csv` is a fixture and is deliberately not deployable.** Terraform sets
`DATA_SOURCE = "lakehouse"` as a literal API app setting in `infra/main.tf` —
there is no variable to change it — and the runtime default in
`tools/fabric_source.active_data_source` is `lakehouse`, so a misconfigured
environment fails rather than answering from a synthetic single-tenant file
that looks like a client result — which is what a `csv` default used to do
silently. `application/deployment.py` does not check `DATA_SOURCE`; do not
claim it refuses `csv`.

`tests/conftest.py` is the ONLY place that selects it, and it must stay: CI
(`ci.yml`) has no Fabric credential and no `azure/login` step, so without the
pin the certified figures could not be verified on a pull request. The parity
gate itself is
unaffected either way — `tools/reference_source.py` reads `One.csv`..`Four.csv`
directly and sits outside the `DATA_SOURCE` switch.

Pointing at the wrong source **does not raise** — the app starts and every
portfolio view is merely thin. `backend/.env.example` documents all three.

**An Active capacity is not a fast one.** OneLake here takes 13–38s to open the
tiny `Account` Delta log, while an unauthenticated GET of the same URL answers
401 in 0.7s — so the latency is in the storage path, not the network, and
neither DNS, proxy, VPN nor IPv6 is involved. `object_store` defaults to a **5s
connect timeout**, which abandons connections that are alive but slow, retries
them ten times, and exhausts the budget — surfacing as `client error (Connect)
-> operation timed out` on every read path at once while the capacity reports
Active throughout. `_TRANSPORT_OPTIONS` in `data/source/from_fabric.py` waits a
slow connect out rather than retrying it, because retrying adds load to the
thing already struggling. That converts the errors into successes; it does not
make the capacity fast, and the lever for the remaining tens of seconds is the
F2 SKU. `application/warmup.py` moves that cost to startup in a background
thread — every step guarded, skipped unless the source is `lakehouse`, and
`TCC_WARM_ON_START=0` opts out when you need to measure a cold request. Its third
step warms **the warehouse connection**, not an engine replay: the landing grid
reads Gold, so warming `GetUnitTrendQuery` would have paid for a path no screen
reads.

The reference client is codenamed **Candle Bottle** (account 1001), a restaurant and
store chain. Real client payroll, de-identified at source. Four synthetic clients
(2000+) carry six-year windows so the retroactive audit has something to work on.

---

## The portal

**One shell, four routed pages.** `frontend/src/App.jsx` is the shell — nav,
scope bar, chat, tour — and every route renders it; `/golden` redirects. Inside,
the URL selects a page:

```
/                       PortfolioPage   the book
/c/:clientId            ClientPage      one client
/c/:clientId/u/:unitId  UnitPage        one location
/c/:clientId/e/:token   EmployeePage    one calculation walk
```

The drill used to be overlays — a drawer inside the grid and a modal over
everything — so the thing a reviewer was actually reading had no URL.
`/c/:clientId/u/:unitId` was worse than that: it parsed the unit and **nothing
read it**, so the URL resolved, dropped the unit and rendered the client grid.
Query string carries `year`, `month` and `method`, so a pasted URL renders that
exact state cold. **An employee id never appears in a URL** — the route carries
the `record_token`.

Navigation is what is LEFT once the pages absorbed the rest:

```
What is it worth       Who qualifies · One/Zero detail
What needs a decision  Data ingestion · Agent activity
Prove it               Evidence pack* · Compare to Access* · Rules & statute · Methodology*
```

**An entry earns its place by answering a question no other entry answers.**
`NAV` is exported and pinned by `test_the_navigation_is_a_decided_set`, for the
same reason `tests/route_inventory.json` pins the 67 routes: an entry is cheap
to add and nothing forces anyone to justify it. Fifteen was a learning curve;
it is eight. `trend` survives as a ROUTE-ONLY id (`ROUTE_ONLY_VIEWS`) because
`/` and `/c/:id` still resolve to it — dropping it from `ALL_VIEW_IDS` makes
every client URL fall back to itself.

Four were absorbed rather than deleted, and every component still renders:

- **Position by location → ClientPage. Position → a SECTION of ClientPage.** The
  location grid shows where credit is EARNED; the variance grid shows how much
  of it was CLAIMED. Two halves of one client answer, and making somebody
  navigate between them is the thing this work exists to fix. `PositionView`
  takes an `embedded` prop rather than being copied.
- **How am I doing → ClientPage** and **What-if → split**: levers to ClientPage,
  the near-threshold list to PortfolioPage. Both REFUSED portfolio scope
  outright, so neither was ever really a destination. `PlanView` is now the
  LEVERS ONLY — `PlanLevers` + `planJurisdiction`. Its default export and
  `PlanProximity` are deleted; that question is a `PriorityBand` on the book.

**THE TWO PROXIMITY LISTS WERE DIFFERENT QUESTIONS, AND ONE OF THEM IS NOW A
BAND.** A brief once asserted they shared a code path; acting on it would have
deleted a live list.

| | Grain | Path |
| --- | --- | --- |
| `PriorityBand.ON_THE_LINE` on `/api/v2/portfolio` | **client**, in JOBS | ranks on `priority_rank`, then identified dollars. PortfolioPage. Replaced `/api/claims/proximity`, which is gone |
| `/api/proximity/{year}` → `handle_get_proximity` | **employee**, in WEEKLY HOURS | stays inside ProgressView on ClientPage |

The client-grain list used to be its own endpoint, its own component
(`PlanProximity`) and its own tab. It read the same claims as the matrix and
kept only cells within one job — so a reader had to know which tab held the
answer before they knew what the answer was, and a client sitting on a large
unclaimed credit was invisible in one while a client one hire short was
invisible in the other. It is a band now, ranked beside the clients it was
competing with for attention.

**One deliberate difference survived the move.** `portfolio_proximity` skipped
any CLAIMED cell — "a position, not a prospect" — which is right when the
question is "who might file this year". The band asks a wider one: a client who
scraped over the line and filed is fragile next year, and that is still a call.
`test_a_claimed_cell_barely_over_the_line_is_still_on_the_line` pins it.

ProgressView and ProximityView ARE one cohort — `get_in_year_progress.py` calls
`handle_get_proximity` outright — and that merge is done. Do not re-merge it,
and do not extend the reasoning to the client-grain band, which shares no code
with either.

### The book ranks by a NAMED reason, never by a score

`PriorityBand` in `domain/claims.py`, six values with an explicit `rank`:
`exposed` → `on_the_line` → `declining` → `unclaimed_at_scale` →
`not_assessed` → `settled`. Within a band, identified dollars descending.

- **Ordered by what INACTION costs, not by size.** `unclaimed_at_scale` sits
  below `on_the_line` despite being worth more, because an unclaimed credit is
  recoverable retroactively and a threshold missed at year end is not. For the
  same reason `declining` outranks it: money you are about to lose outranks
  money you have not collected.
- **`declining` is NOT `exposed`, and must not render like it.** Exposure is a
  finding against a return somebody has already filed; this is a forecast about
  a year nobody has filed yet, and rendering them alike turns a projection into
  an accusation. Both `exposed` and `on_the_line` still outrank it and neither
  can be displaced by it, so a client that is both says the thing that has
  already happened. Its chip is the only one drawn as a dashed OUTLINE rather
  than a fill. It is also not the per-employee `at_risk` read — `gold_reader.at_risk()`
  and `chat_jobs_at_risk()` are unit grain and stay that way.
- **A TREND IS NOT A CELL**, so no claim can carry it. `declining_reading()`
  takes the client's WHOLE history and is applied over the cell band; it returns
  `None` rather than `declining: false`, because an absent trend and a flat one
  are different and only one earns a band. It also requires that the client
  actually earned credit at the higher level — shrinking is only a credit
  problem if there is a credit to shrink out of.
  - **The year filter destroys it.** Every real page load sends `year`, and one
    year has no direction. `portfolio_v2` reads the trend from `history` (all
    years) and the cell from `grouped` (the filtered year). Reading both from
    `grouped` made Halloway — down 39.33 jobs since TY2022 and below the base
    year it earned $208,845 from — band as `settled`, "Nothing outstanding", on
    every screen anybody actually opens.
- **No composite score, deliberately.** Blending dollars and jobs needs
  coefficients nobody can justify, and this ranking exists to be read aloud on a
  call. "You are one hire from a credit you get nothing for" survives that;
  "priority 0.73" does not.
- **`jobs_margin` is the signed sibling of `jobs_to_threshold`**, which clamps
  at `max(0, ...)` — so one job over and fifty over both read `0.0` and "about
  to lose eligibility" could not be computed from it at all. `on_the_line` is
  `abs(margin) <= 1.0`: gaining and losing are one fact seen from two sides.
- **The band is computed SERVER-side** so sorting and paging cannot disagree
  with it. `frontend/src/lib/priority.js` only knows how to SAY it.
- **A row headlines in the unit its band moves in.** `on_the_line` renders in
  JOBS under its chip; rendering it in dollars reads as worthless, which is
  exactly what the ranking exists to stop. `declining` carries the credit
  ALREADY EARNED on its trend line, not `identified` — this year's cell is
  often `—` and would read as an opportunity.
- **THE BOOK HAS ONE MONEY COLUMN, AND IT IS `identified`.** Recoverable and
  exposure are both `identified − claimed`, and no client has a verified
  filing — `seed_claims.py` supplies three `CLIENT_ASSERTED` figures the
  enum itself labels UNVERIFIED. Both columns were arithmetic on an assertion,
  so both are gone, along with the `opportunity` sort key. The EXPANDED rows
  follow the same rule: `ExpandedCells` had no test and kept a Claimed column
  and an Outcome column reading `over claimed` / `unclaimed` / `correctly not
  claimed` long after the parent was cleaned up. `outcome` stays on the wire —
  it is a real filter, and the Position view exists to compare against an
  assertion — but the book does not render it as a finding.
- **A BAND IS NEVER DERIVED FROM AN UNVERIFIED CLAIM.** `priority_band` gates
  on `provenance.verified`: `exposed` needs a verified filing, and where the
  claimed side is unverified the outstanding test reads `identified_usd`
  rather than `opportunity_usd`. Gating exposure ALONE is not enough — netting
  Cascade's asserted $95,000 off its real $31k identified drove `opportunity`
  to zero and banded a client with found credit as "Nothing outstanding".
  `variance_usd` and `opportunity_usd` keep their meanings for the Position
  view, which exists to compare against an assertion and says so on screen;
  the band is a RANKING that puts a word next to a client's name, and that is
  a different standard of proof.
- **Sorting by dollars sets the ranking aside, and the page SAYS so.** The
  default stays `sort=priority&order=asc`; `ranksByValue()` in `lib/bookSort.js`
  drives the statement, and the answer band stops claiming a "top of the call
  list" it no longer has. The book sorts SERVER-side on one key under `bsort`,
  which is deliberately not the trend grid's `sort` — one name for two grammars
  renders one page right and the other silently unsorted. `SortHeader` is shared
  by both grids and takes `multi={false}` here, because offering a second key
  the endpoint will ignore is worse than not offering one.
- The `claimed` side of the book is seeded (three rows, all labelled
  illustrative), so `exposed` and `unclaimed_at_scale` both rest on an
  unverified assertion. Rank on `identified`, which is real, and let the row
  carry the marker. The band IDs keep their names — they are in URLs, filters
  and tests — but the copy does not assert what a filing would: the labels are
  **Identified** and **Nothing found**, not "Unclaimed" and "Settled".

### The map is a filter, not a picture

`FootprintMap` renders on the book and writes the SAME `state:` expression the
filter bar shows — never its own selection, or a chip cleared in the bar would
leave the map still looking selected. `/api/v2/portfolio` carries `states` and
`priceable_states` per row, from one `GROUP BY AccountId, state` rather than a
`payroll_scope` call per client, and unassessed clients carry them too: where a
client operates is a fact about payroll, not about having been run.

- **A cell holding several values is a property of the COLUMN, not a new
  operator.** `spec.multi` on an ENUM matches if any held value is selected, so
  the written grammar stays `col:a|b` and `tools/grid_filter.py` is unchanged.
- **Held and priceable are different claims.** Only GA has year-scoped packs,
  so NC, SC and TN are payroll we cannot price — a real gap in statutory
  coverage, and this is the one screen that shows it. Selection is drawn as an
  outline, never a fill, because filling it would overwrite that distinction.
- **The map sits BESIDE the state list, not above the grid.** On its own it was
  two thirds whitespace — we hold four states and the other forty-six are the
  picture — and it cost 546px before the first row. Beside the list it costs
  280px and every row fits. The list is also the keyboard path to the same
  filter; a map shape is not reachable by tab.
- **Clients per state, never dollars.** A claim is client-grain and a client
  operates in several states, so any per-state money figure would either
  double-count or attribute a credit to a state that did not earn it.

### Ask Copilot hands the agent a brief it cannot add to

`GET /api/v2/clients/{id}/situation` → `domain/coverage.situation()` ranks one
client's cells by band. Claims only: no payroll, no engine, so a per-row button
costs a query rather than a replay. `ClientSituationAgent` narrates it.

- **Not `ReportingAgent`.** That one is told to "lead with the dollar value" —
  the exact instinct the band ranking corrects. An agent arguing against the
  screen it sits on is worse than no agent.
- **A row-level ask carries its own scope.** `ask(prompt, scopeOverride)` →
  `ChatPanel` → `streamChat`, so asking about a row answers about THAT client
  without moving the user's selection.
- **The chat reads Gold, not payroll.** `_request_scope` resolves `resolve_statute`
  (it never read the payroll `resolve_client_run` loaded), and
  `chat_client_context` reads `run_method_summary`. It used to narrate
  `load_payroll_snapshot`, which reads a synthetic CSV and says so in its own
  citation — so the answer described 9,477 invented employees while the question
  was about a client with 10,236.

### The router picks tools; it never produces a figure

`_plan` asks `OrchestratorAgent` for JSON naming capabilities from
`CAPABILITIES`; `_dispatch` runs each one's deterministic brief and streams
them in order. That is compatible with [ADR-004] — choosing WHICH tool runs is
not computing, and the alternative cannot split a question.

- **ONE QUESTION IS ROUTINELY SEVERAL.** "Brief me on them and what else might
  they qualify for" is `situation` then `discovery`. Single-intent keyword
  matching returned the first hit and dropped the rest **silently**, so half the
  question went unanswered with nothing on screen to show it had been asked.
- **An intent the whitelist does not know is DROPPED, never dispatched.** Models
  invent plausible names — `trend_analysis`, `client_deep_dive` — and a made-up
  intent falling through to the default pipeline answers a question nobody
  asked. `_validate_plan` is the gate.
- **Keyword routing survives as the FALLBACK.** A router that errors, or returns
  nothing usable, must not take the feature down; it is also what answers when
  Foundry is unconfigured.
- **`done` is emitted ONCE.** Each pipeline yields its own, so `_dispatch`
  swallows all but the last — a `done` after the first intent stops the UI
  streaming while the rest of the answer is still coming.
- **A missing capability looks like a routing bug and is not.** "Are any of the
  counted jobs close to the threshold and may fall off" had nothing behind it,
  so the router sent it to `simulate`, which removed all nine counted jobs and
  reported no impact on a closed year. Adding keywords would not have helped;
  the answer did not exist. Check `CAPABILITIES` before tuning the router.
- **A capability's NAME is part of the routing.** `portfolio` was a rule-pack
  scan for ONE client, so the router picked it for "who should we reach out
  to?" and answered a different question convincingly. It is `multi_state` now,
  and `book` is the cross-client one.
- **Scope is refused PER CAPABILITY, not at the door.** Every question used to
  need a client and a tax year before it was even routed, which made the
  portfolio question unanswerable from the title bar — where no client is
  selected BY DESIGN. `_NEEDS_CLIENT` marks the eight that are about one
  client; `book` is the one that is not. A turn that asked for both answers the
  book half and NAMES the half it could not, rather than refusing whole.
- **The refusal must not depend on Foundry.** It is about answering for the
  wrong company, not about routing, so the pre-check in `chat()` uses keywords
  and needs no model. Scope integrity cannot hinge on whether a router is up.

### An open year's credit is a run-rate, and it says so

What-if leads with **Credit gained**. A closed year is priced by the engine. An
open year (TY2026) is not claimable, so its figure is the one labelled estimate
the product makes. `simulate_unit.run_rate_credit` prices the year as if it
closed at its pace so far, using `unit_trend`, the function that wrote the
grid. Earlier tranches therefore lapse when the jobs behind them are not
maintained.

- It returns `None` for any year that is not open. A closed year can never be
  rendered as an estimate.
- "Run-rate" appears in the card label, the table row and the method note,
  never only in a footnote.
- **There is no client-wide run-rate total.** How am I doing projects the
  client against its prior year, a different base, and two TY2026 totals would
  disagree on one screen. The stack's before → after covers only the
  locations it touches, and the card says so.

### Coming IN and falling OUT are different populations

Every proximity read in the product was about people OUTSIDE the credit. A
client asking "which of my net-new jobs might I lose" is asking about the people
already INSIDE it, and no near-miss cohort can answer that — that cohort is
precisely everybody else.

- **`assess_employee` is the way in; `fragility` is the way out**, and the
  arithmetic INVERTS. Qualifying needs both floors cleared, so the LARGER gap
  binds — `max`. Falling out needs only one breached, so the SMALLER cushion
  binds — `min`. Somebody at twice the hours floor and a dollar over the wage
  floor is one bad week from falling out, and the hours cushion alone calls them
  safe.
- **`fragile_cohort` ranks cushions; it never re-decides who qualified.** It is
  handed the eligible population and takes that verdict as given, the same rule
  `near_miss_cohort` follows.
- **It counts JOBS, not people.** A part-time band carries a fractional weight,
  so losing somebody does not always cost a whole job.
- The brief states this describes a COMPLETED year — what would have to change
  to lose these jobs, never a prediction that they will be.
- Live: Candle Bottle TY2023 has **290 of 539** eligible within five hours of
  falling out, 211 binding on hours and 79 on wages.

### A conversation is ABOUT something

- **The chat pins the scope an ask arrives with.** Asking from a row set the
  client for one message and then reverted to the shell scope, which at
  portfolio scope carries no client — so "what is their trend?" was refused one
  line after the client had been named. The pin holds until the scope bar
  changes under it, which is a deliberate act and outranks it.
- **History travels with the request** so "their" and "since then" resolve. It
  is context for ROUTING only; every figure still comes from a tool.
- **`eligible_every_year_since_base` is `None`, never `False`, when the run
  holds nothing after the base year.** `False` asserts "they have not been
  eligible since"; the truth is there is no year to judge. The reference client
  holds TY2023 and nothing else, so it takes that path on every read.

**Neither employee-grain view answers at portfolio scope, and that is the fix,
not the limitation.** A cohort is read from ONE client's run — its statute, its
fiscal window, its recorded verdicts — so `handle_get_proximity` and
`handle_get_in_year_progress` both require an `account_id`. They used to fall
back to `configured_account_id()`, which rendered account 1001's employees under
the heading "All accounts": the exact mislabelling ProximityView's own scope-key
guard exists to prevent, arriving through the back door. ProgressView already
declined; ProximityView now declines too, and stays silent when embedded so the
page carries one explanation rather than two.

**Every page opens with ONE quiet line, and lets the data do the talking.**
`InsightBar` is a small caption (the counts, from `lib/answers.js`), an ⓘ
holding the conditions on them — prototype designations, an open year, a
placeholder floor, the run from `run.produced_at`, `run.code_commit` and
`run.rule_pack_version` — and a collapsed **Copilot summary**. It replaced the
answer banners (29 Sep), which restated in large type what the grid beneath
already showed and singled out one data point.

- **Notes stay in the DOM.** Hover or click shows them; they are hidden, never
  unrendered, so a disclosure is never one render from gone.
- **The summary runs only when opened**, once per scope: ~5-15s and a Foundry
  call. `POST /api/summary` builds its brief from the SAME endpoint functions
  the page calls (`api/summary.py` → `tools/page_brief.py`), so it cannot
  describe a different answer from the one on screen, and `PageSummaryAgent`
  narrates it [ADR-004].
- **Every figure it states is checked.** `unsupported_figures` compares each
  number against the brief at the precision it was written to ("$549k" passes
  for 548,730; "TY2019" does not pass for TY2021), and the panel names any
  that fail. Without Foundry it shows the computed facts and says so.

**Provenance and Calculation walk → Evidence pack.** All three read the same
two singleton `/api/workspace/*` endpoints, and the pack already carried a
hashes panel repeating run identity value for value plus a table repeating
the walk. Full working sits behind a toggle so printing still produces a pack.

They were composed, not cut and pasted: `ProvenanceView` and
`CalculationWalkView` still exist and keep their tests, and take an `embedded`
prop that drops their page header. **The routing chain's fallback is now an
explicit warning**, because a bare `else` rendered Agent activity — so an entry
whose route was removed showed the findings queue under someone else's heading
instead of failing.

**`/` is the portfolio page.** Position by location is a CLIENT page and lives at
`/c/:clientId`. At portfolio scope the grid only ever rendered a client picker —
there is deliberately no portfolio view of it — so `/` renders the coverage
matrix, whose client column is that picker. `GET /api/v2/clients/{id}/units` +
`infrastructure/persistence/gold_reader.py` + `components/TrendGridView.jsx`. It
is the shape the partner already reads the credit in: a block per location, a row
per tax year, twelve monthly headcount columns, TOT, AVG, and the YR1..YRn
credit stream that location's base year opened. **Every figure is READ from
`tcc_gold`, including the sums** — the roll-up strip renders
`SUM(annual_credit_usd)` as SQL computed it rather than re-adding the rows on
screen. A page load runs no engine. The statutory mechanics are not
re-implemented: they ran once, at write time, through
`application/commands/run_client_calculation.py`, which replays both methods over
every authored year because a base year needs the whole series.

`GET /api/trend/units` is **gone** — the v2 read replaced it and nothing called
it. `application/queries/get_unit_trend.py` and `tools/unit_trend.py` both
remain, and are not dead: `run_client_calculation.py` imports
`_MIN_REACHABLE_MONTHS`, `_candidate_years`, `_designation_at` and `_year_benefit`
from the first and the whole series-building surface from the second. **The
engine moved from the read path to the write path; it did not go away.**

`handle_get_unit_trend` survives too, and only its 11 tests in
`test_api_trend.py` justify it. Nothing in the app sends `GetUnitTrendQuery` any
more, so the handler looks deletable — but no offline test drives
`run_client_calculation`, which makes those 11 the ONLY automated coverage of the
helpers the writer depends on. Delete the handler and you delete the coverage of
live code. Write write-path tests first, then revisit.

**The colour rule lives in one function.** `lib/trendGrid.js` — base year is
accent, above the minimum is green, below is red, a partial year is amber. The
source spreadsheet's yellow/green/red/cyan map onto the tones the product
already owns rather than being reproduced; two palettes doing the same job read
as two meanings.

**A month nothing reaches is a calendar fact, not a headcount.**
`domain/calculation/onezero.unreachable_months` names the positions no pay
period spans, and the grid hatches the ZERO ones instead of colouring them as a
decline. Both boundary months of the reference client are structurally empty:
nothing spans 2023-07-31, and nothing spans 2024-07-31 either — Month 12
produces a number only because `_adjusted_target_for_month` retargets to the
employee's last pay-period end when it falls after the 15th. That is the
agreed method, so a month the rule counted is coloured like any other (29 Sep);
only its title says how it was measured. A client whose final period ends on or
before the 15th gets no such rescue, so the hatching is what stops a confident
zero reading as a location that emptied out.

**Completeness is measured against the months that are REACHABLE, not against
twelve.** A calendar-year client has no measuring date in December at all, so
eleven months IS its complete year. Judging it against twelve rejected a
complete year and pushed the base a year later — on the Cascade fixture that
moved every base from TY2020 to TY2021 and the portfolio claim from $607,110 to
$229,285. The base year is the most leveraged input in the model; everything
downstream hangs off it. **The divisor stays 12**, because the partner's own
Access output divides by 12 with a zero month in it — see questions 23-25 in
`docs/data/REFERENCE-DATASET.md`.

**A year the payroll barely touches is declined, not priced at zero.**
`_MIN_REACHABLE_MONTHS` in `get_unit_trend.py`. Candle Bottle's payroll stops
2024-08-09 while TY2024's window runs to 2025-08-02, so one of twelve targets is
reachable; the year was being published at an average of 0.0 across 101
locations. `_client_run` declines only on ZERO rows, which is too weak a test.

**There is no portfolio view of the grid, deliberately.** A base year is a fact
about one client's payroll; measuring one company's locations against another's
baseline is arithmetic without a meaning. Portfolio scope renders a client
picker built from `/api/scope`, which costs no engine run.

**"We have not looked" and "we looked and found nothing" are different claims.**
`isCalculated(payload)` in `api.js` is the single place that distinction is made,
so a view cannot get it wrong by writing `!items.length`. A client with no
successful run gets `calculation_state: 'not_calculated'`, and the grid renders
the statement plus a **Run calculation** button — never an empty grid, never a
$0. A $0 is an assertion about that client's payroll.

The same rule holds on the portfolio matrix. `GET /api/claims/coverage` groups by
client FROM CLAIMS, so a client nobody has assessed is absent entirely and reads
as a client that does not exist. `lib/coverage.withUnassessedClients` merges the
book from `/api/scope` back in and appends the unassessed **without ranking them**
against the assessed — a real $0 opportunity has been looked at and an unassessed
one has not, and sorting them together puts both in the same bucket.

**Summed money is still money.** `_MONEY_COLUMNS` in `gold_reader.py` must carry
the SQL aggregate *aliases*, not only the base columns. `SUM(annual_credit_usd)`
returns a `Decimal` under the name `total_annual_credit_usd`, and a name that set
does not know falls through to the float branch — so every row feeding the total
was exact and the total was not. `final_high_water_mark` is deliberately NOT in
the set; it is a headcount.

**The drill stays on the page.** A month cell opens the people counted there from
`GET /api/v2/clients/{id}/units/{unit_id}?month=N`. The warehouse **narrows** to
the month rather than annotating it, so the drawer's count is the number of
people who actually contributed to that cell. `month` filters via `month_NN > 0`;
an earlier cut annotated the rows and returned everyone at the location, which
read as 29 people in a cell whose truth was 25.
`test_the_grid_and_the_drill_index_the_same_months` guards the month grid,
because the drill opens a month by POSITION.

**`onezero_matrix` holds ONLY employees who already qualified.** Any cusp count
taken from it is structurally zero — it was, at every unit on every client. The
people one shift short live in `employee_eligibility`, which has no worksite;
`employee_period_fact` places them. `unit_near_threshold` joins the two and is
returned as a SEPARATE `near_threshold` array, never merged into the qualified
list: a qualified employee and a near miss are different answers.

- The join to `employee_eligibility` is 1:1 on the full key and must not fan out
  — 29 stays 29. `SELECT DISTINCT` on the near-miss side is load-bearing because
  `employee_period_fact` is one row per pay period.
- **The BAND is applied by the page, not by SQL.** The reader returns every
  ineligible employee at the unit; how close counts as close is a presentation
  choice, and putting 35 in the query would bake Georgia's floor into everyone's
  warehouse read. `_unit_thresholds` returns `min_weekly_hours` as a NUMBER,
  because `rule_pack_version` is a version string and cannot draw a marker.
- Cascade TY2023: **50** ineligible across six units, **25** within five hours.
  GA_GA-001 is 7 and 4, closest 34.81; GA_GA-007 is 9 and 6; GA_GA-010 is 11
  and 8. The full-cohort and within-band counts are different numbers and a test
  asserting one against the other will look like an off-by-three.

**THE HOURS GAP IS NOT THE ANSWER TO "how many more hours would Sally work?"**
`api/trend._with_lever` CALLS `assess_employee` (never copies it) to attach
`additional_weekly_hours` to the near-threshold cohort.

- **The cohort includes people OVER the hours floor.** It is everybody
  ineligible at the unit, so somebody clearing 35 hours and failing on wages is
  in it — and `floor − hours` is NEGATIVE for them. The grid rendered
  "-1.33 hrs" in an amber pill under "Short by". At Candle Bottle `GA_1134481`
  that is **192 of 200** rows, the top one working 36.33 hrs and needing 5.44
  more; the hours gap told the worst-affected people they were fine. `Short by`
  reads `over` when the floor is met.
- **The wage-bound marker is derived from the COMPARISON, not `failure_mode`.**
  Somebody can fail both floors and still have the hours gap bind — 31.23 hrs at
  $620.90 needs 3.77 hours for the schedule and 0.76 for the pay.
- **No per-person dollar figure, ever.** A location's credit turns on its job
  count against a threshold, so the marginal employee is worth the whole tranche
  or nothing and neither can be attributed to a row. The one money field is a
  RATE — what to pay them. Say the hours, not the dollars.

**A `record_token` resolves only where the run that minted it is served.**
`tools/tokens.py` owns the one derivation, a SHA-256 over
`(account, programme, year, employee)`. It cannot be reversed — but it is a
STORED COLUMN on every employee-grain Gold table, so resolving it is a `WHERE`
clause, not a search. The sealed workspace re-mints over its population because
it has no Gold behind it; the per-client drill must not copy that.

- **Opening one employee used to cost two engine replays.** It loaded the
  client's whole payroll, ran BOTH certified methods over it, minted a token for
  all 10,236 employees to find the one clicked, then loaded the payroll AGAIN
  for the source rows. `employee_drill` is three statements in one round trip —
  `employee_eligibility`, `onezero_matrix`, `employee_period_fact` — and 1.3s.
- **Two things the drill genuinely cannot show, and both are NAMED.** Gold holds
  only the rows the run CONSUMED, so pay periods the fiscal window excluded are
  absent — and "why is this person short a month" was exactly what they
  answered. The matrix is deduped before it is written, so per-employee
  contested months leave no trace; only `run_method_summary.contested_months`
  survives. Both sit in `not_available` rather than appearing as a shorter list.
- **Gold records WHY a row was selected; the panel asks WHETHER it was.**
  `selection_decision` is `fiscal_window` in storage and `included` on the wire.
  Leaking the storage vocabulary would make the panel look like it had found a
  second category.

Every per-client view minted correct tokens that nothing served, so every
employee row opened a 404. `POST /api/employee/drill` +
`application/queries/get_employee_drill.py` now answers for whichever
client-year rendered the row; `EmployeeDrill` takes a `context` prop and falls
back to the sealed endpoint without one. The per-client drill **names what it
cannot show** — Access differences, source-file lineage, assumption-set hashes —
rather than rendering them empty, because an empty Access panel reads as "we
checked and found none".

**Data ingestion and Agent activity are work queues, not plumbing.** Ingestion
carries accept/drop/flag on every QC exception; findings carry resolve/reopen and
the code counts `requires_decision`. They were filed last under "How it runs" —
a heading left over from when Agent activity listed registered agents and their
status. Both were rebuilt into decision queues, so they sit where an analyst
actually reaches for them.

`*` = **sealed**: backed by the certified parity run rather than the client
selector. They deliberately do not follow the selector — their purpose is to be
the hash-stable artifact tied out against the partner. The shell banners them so
a viewer never has to assume.

Be honest about which is which. *Compare to Access* is legitimately singular —
there is one partner reconciliation. *Methodology* is client-agnostic: BA-01..BA-12
are global and the floors are year-scoped. *Evidence pack* is the one that is
sealed because the per-client path has not been built yet, which is a gap, not a
principle. **Who qualifies** and **One/Zero detail** were converted already:
`GET /api/eligibility/{tax_year}` and `GET /api/onezero/matrix/{tax_year}` run
the certified methods over whichever client is selected. Folding provenance and
the walk into the pack means that conversion is now one view, not three.

**Both per-client reads resolve through `application/queries/_client_run.py`.**
One resolver answers the four questions every per-client read needs — programme,
statute, fiscal window, payroll rows — so two views cannot disagree about the
denominator period for one client-year.
`test_the_matrix_and_the_population_agree_on_the_window` asserts exactly that.

**A fiscal year that opens mid-month opens on a stub, and the stub is not a
measuring month.** `engine_kwargs()` derives `analysis_start_month` from
`domain/calculation/onezero.first_measurable_month`, never from `window.begin`.
Candle Bottle's window opens 2023-07-28 but its earliest pay period starts
2023-08-01, so nothing spans 2023-07-31: starting there burned Month 1 on a date
no payroll could reach AND pushed the window's real final month off the end of
the twelve. It understated the Min-Max annual average by 35 jobs, 410.13 →
375.53. OZ-01 had already hit this and pinned the sealed run to August-July by
hand; the derivation reproduces that answer instead of hard-coding it.
The older `/api/onezero/{tax_year}` still buckets rows by a global fiscal-year
end month and is *not* window-consistent with these two; it is the legacy path.

**A per-client read must tie out to the certified figures for the reference
client.** `test_the_per_client_read_agrees_with_the_certified_figures` is the
join between the two halves of the system. The first cut of the eligibility
handler reported 539/656 correctly while counting **10,080** employees, because
it took its denominator from the union of the two methods' average rows instead
of from everyone with payroll in the window — 156 employees have totals but no
qualifying period. Matching eligible counts do not prove a matching population.

**A result must publish the matrix it counted.** `run_min_max_method` assigned
its deduped matrix to a local and then returned the *raw* one, so every roll-up
of `employee_unit_matrix` double-counted the 251 employee-months the tie-breaker
had already resolved — while `annual_average` on the same response was right.
Pay Period had always published its deduped matrix. Nothing failed, because no
test asserted the one-per-month rule on the shipped output; the engine's own
`dup_flags` recorded the candidates but nothing checked the resolution.

**A `record_token` must resolve in whatever serves the drill.** `tools/tokens.py`
owns the one derivation, from `(account, programme, year, employee)`. The sealed
workspace previously keyed it to its own `calculation_id`, so every row the
per-client views rendered opened a 404 — two internally consistent schemes and
no test crossing the boundary. `tests/test_record_tokens.py` crosses it.

**A screen reads one source.** `to_canonical` defaults to the local CSV, so the
ingestion view counted 384,433 Fabric rows and then ran the next three stages
over a 9,477-row synthetic file — reporting 0 for a tax year that file does not
cover. Pass `RowsAdapter(rows)` rather than letting a view mix sources. That
view also selects by the client's **fiscal window**, because that is the
selection the run made; the cash-basis calendar trim is display-only and
claiming it as the pipeline overstated 155,293 rows as the population.

**`PORTFOLIO` is the string `'portfolio'`, not an id.** Any view that forwards
`scope.clientId` to an `account_id` parameter must branch on it first, or the
request is a 422 the moment somebody selects All clients.

**A tax year is a fiscal window, not the calendar year of the same name.**
`/api/scope/client/{id}` counts payroll inside each year's resolved window.
Bucketing by calendar year split Candle Bottle's one 53-week year into
"TY2023 · 5mo" and "TY2024 · 8mo" — two partial years where the client has one
complete one. `tests/test_scope_tax_years.py` is live-Fabric because under `csv`
the window is an assumed calendar year and the bug is invisible.

**Per-client fiscal rules exist only in the `lakehouse` source.**
`client_fiscal_window` returns an assumed calendar window unless
`active_data_source() == "lakehouse"`. Without that guard a CSV run paired CSV
paychecks with Fabric calendars — a window matching neither source.

**Pay Period is NOT always ≥ Min-Max.** Cascade TY2023 is 134/133 and Ironbridge
TY2024 is 107/106, both Min-Max ahead; 14 of Candle Bottle's employees are
Min-Max-only. Min-Max divides by `(last PPE − first PPS + 1)/7` while Pay Period
sums `(PPE − PPS + 1)/7`, so for short tenure Min-Max's span is *smaller* and
its average higher. Never publish a single "eligible" count — it is a method
choice the statute has not made.

**Average Headcount is measured over the CLIENT's twelve months.**
`domain/calculation/headcount.py` takes an optional `window`; without one it
falls back to the calendar year, which is right only for a calendar filer.

- **The claim layer hardcoded Jan-Dec.** Candle Bottle's payroll runs
  2023-08-03 to 2024-08-09, so TY2023 kept 155,293 of 384,433 rows, scored the
  seven measuring dates before the first pay date as zero, still divided by
  twelve, and reported **226.76** against a certified Pay Period **494.25**.
  Halloway (a July-June filer) was out too; the three calendar filers agreed,
  which is why it survived.
- **It is the BASE YEAR the error lands on.** TY2023 is Candle Bottle's base, so
  `identified` was $0 either way and nothing wrong reached a screen — but the
  base is the most leveraged input in the model, and net-new would have been
  measured against a figure understated by ~268 jobs.
- **`first_measurable_month`, never `window.begin`.** Same derivation
  `ClientRun.engine_kwargs` uses. Taking `begin` directly reported 451.71,
  because a year opening mid-month opens on a stub no pay period spans.
- **ONE resolver: `fiscal_source.window_for_state_year`.** The assessment and
  both what-if simulators each had their own view of "the twelve months" once
  before, and Position quoted $0 for a client-year while Plan quoted $252,280.
- **A year the payroll barely touches is DECLINED, not priced at zero.**
  `_MIN_MONTHS_TO_ASSESS`, matching `_MIN_REACHABLE_MONTHS` in the unit trend.
  Candle Bottle's TY2024 window runs to Aug 2025 on about a week of data; the
  row-count guard passed it and it published as "assessed, no credit found".

**Scope is a persistent dimension, not a view.** `client × program × year` lives
in the shell and survives navigation. Jurisdiction is *derived* from the program
and never selected independently. `lib/scopeDimension.js`.

**THE BOOK HAS NO YEAR, and the scope bar is absent there rather than empty.**
`YEAR_FILTERS` is `unit` and `employee` only.

- **Without a client there is no payroll to narrow by**, so `calculableYears`
  falls through to the STATUTE years — every authored GA year, 2019-2025 — and
  opened on the newest. Candle Bottle holds one year of payroll and was pinned
  to TY2025, where it displayed a figure.
- **"Who do I call" is a question about a client across every year they hold.**
  An unclaimed year from four years ago is still recoverable retroactively, and
  a year filter buries it. The year is chosen after a client is, on that
  client's own grid, which IS the year dimension.
- **The year filter was also flattening the bands.** Scoped to TY2025 four of
  five clients read `unclaimed_at_scale`; unscoped the same five rows read
  `exposed`, `on_the_line`, `on_the_line`, `declining`, `settled`. A band column
  that looks redundant is worth checking for a filter upstream of it.
- `ExpandedCells` fetches every programme-year for the same reason.

**`gap_jobs` CLAMPS AT ZERO, so it cannot carry an answer either side of the
line.** The portfolio answer band said "Northwind is 0.0 jobs from qualifying"
about a client 0.58 jobs CLEAR — naming the one client with nothing to do as the
closest to needing something. `on_the_line` is `abs(margin) <= 1.0` and catches
both sides; anything describing it reads `jobs_margin`. Same defect class as the
unit grid's "Short by -1.33 hrs".

**A test that stubs the Gold writer is not isolated.** `run_client_calculation`
also dispatches `AssessClientCommand`, which writes a CLAIM — so
`test_run_client_calculation` recorded account 1001 at TY2024 and TY2025 from
the synthetic CSV on every run, and the book read them back as that client's
credit position: `avg=61`, `base=40`, 19 jobs x $3,500 = **$66,500** on screen
for a client whose Gold holds only TY2023. 964 rows had accumulated. Stub
`set_claim_repository` too; `tools/purge_test_claims.py` clears what leaked.

### Frontend rules

- **`src/lib/` is framework-free logic + constants**, unit-tested. Put new
  derivation, formatting or validation there, not inline in a component.
  `answers.js` is the page-opening sentence; `goldTrend.js` reshapes Gold rows.
- **`src/pages/` is the four routed drill pages.** A page owns its own read,
  its answer band and its breadcrumb; `src/components/` holds what pages compose.
- **`src/components/` are views and reusable components**, one `.test.jsx` each.
- **`src/api.js` is the only network layer.** Components never call `fetch`.
  A new endpoint gets a wrapper and an `api.test.js` case.
- **1024×768 is the acceptance target.** Desktop only; mobile is out of scope.
- **Blue reads, purple selects.** The two accents do different jobs and must
  not be swapped.
  - `--accent` / `--accent-strong` / `--accent-bg` — blue. Anything that
    encodes a *reading*: a figure, a status, a statutory verdict.
  - `--accent-2` / `--accent-2-strong` / `--accent-2-bg` — purple, aliasing
    `--exp-violet` / `--exp-purple`. Chrome *selection* only: the active nav
    entry, active tab, selected row, focus ring, open menu item.

  Never reach past these to `--exp-purple` / `--exp-violet` directly. The
  distinction is what stops a selected tab being mistaken for a verdict, and
  the brand guide is explicit that purple and magenta "should be used
  generously" — so purple is not decoration to be avoided, it is the
  selection language.
- **A reading is named for what it means, not what it looks like.** State
  tokens are `--state-base-year`, `--state-above-min`, `--state-below-min`,
  `--state-partial`, `--state-neutral`, each with `-ink` and `-line`. A name
  that describes the hue invites reuse where it means nothing.

  `--state-base-year` (blue) and `--state-below-min` (orange) mean different
  things — "we hold no prior year to measure against" versus "they did not
  grow enough". They must never converge.
- **State tokens alias, they do not restate.** `--state-below-min: var(--bad-bg)`,
  not a fresh literal. A literal is how a tint silently drifts during a
  migration.
- **Roboto, self-hosted.** The brand's specified web font, via `@fontsource`
  imports in `main.jsx`. Never hotlink Google Fonts — a demo on a network that
  cannot reach `fonts.gstatic.com` falls back silently.
- **Type is a scale of eight, named for the job.** `--text-micro`,
  `--text-caption`, `--text-small`, `--text-body`, `--text-strong`,
  `--text-subhead`, `--text-title`, `--text-display`. **A raw `px` in a
  `font-size` is a bug, and a half-pixel size is always a bug.** There were 23
  sizes across 321 uses, 105 of them at 9.5/10.5/11.5/12.5px — nobody designs a
  half-pixel step, that is one person nudging one screen until it looked right.
  A token named for its size invites the next 12.5px, which is why none of them
  are.
- **A half-pixel size is a density problem wearing a font-size.** Fix it with
  `line-height` or `letter-spacing`, which is what it was actually asking for.
  `.tcc-cell-btn` is the worked example: it bought its 28px row with 10px type
  until `line-height: 1` bought the same row at 12px.
- **12px is the floor for anything read AS DATA** — table cells, headers,
  figures, verbatim engine output. Chrome (eyebrows, chip captions, pills,
  superscripts) may go smaller; data may not, and anything below the floor
  needs a stated reason in a comment. IBM Carbon puts data-table row text at
  **14px**; we sit at 12 because the trend grid is 17 columns in a 1024px
  viewport. Nothing ever CHOSE 9px — 9px is what was left when nobody owned
  the scale. Check it with `frontend/tools/check_type_floor.py`, which reads
  COMPUTED sizes off the rendered page; a selector audit over-reports, because
  `.th-sort sup` is a superscript, not a table header.
- **Padding, margin and gap use `--space-1..10`; a raw `px` in one is a bug.**
  Two-pixel steps to 16, then 20 and 24. The previous five-step scale was used
  ELEVEN times against 381 raw declarations because the values people needed —
  2, 4, 8, 12, 14 — were not on it: a scale nobody can hit is a scale nobody
  uses. Odd values round DOWN, because rounding up costs rows.
- **Radius is `--radius-sm|--radius|--radius-lg|--radius-xl|--radius-pill`.**
  17 distinct radii were being written by hand; 4px beside 5px beside 6px is
  drift, not a decision. `50%` stays raw — a circle is a shape, not a step.
- **No `style={{ }}`.** It steps around every token above, which makes the
  whole system a suggestion. Use a class; `.u-mt-*` / `.u-mb-*` / `.u-ml-*` are
  the sanctioned spacing utilities and are token-valued so a component cannot
  invent a step. Two exceptions exist and both carry a comment: a width
  COMPUTED per render (the tour progress bar), and `react-simple-maps`, whose
  `style` is a library **prop** taking default/hover/pressed objects that no
  class can express. Its fills are read from `--map-*` so the legend and the
  map cannot disagree.
- **Compose the shared components; do not hand-roll their job.** `PageHeader`
  owns eyebrow/title/sub/actions, `StatCard` + `StatRow` the figure strip,
  `Breadcrumb` the trail, `MethodTabs` the Min-Max/Pay Period choice,
  `GridTabs` two peer grids over one scope, `InsightBar` the page-opening
  caption, notes and Copilot summary, `ColumnFilter` + `FilterBar` the per-column narrowing. A second
  `PageHeader` once lived in `ReferenceViews.jsx` with a different prop name and
  different classes, and eight call sites used it — two header treatments kept
  in step by hand. If a shared component genuinely cannot express what a view
  needs, say so and leave the duplicate: an abstraction bent to fit is worse
  than an honest one.
- **Two peer grids over one scope are TABS, and the tab carries its count.**
  `GridTabs` reuses the `MethodTabs` shape on purpose — a third tab style makes
  "which of these is a tab" something a reader works out — but takes the purple
  accent, because MethodTabs picks a statutory *reading* and this picks which
  *population* is on screen. "Who to call" does not tell you whether to click;
  "Who to call (4)" does. **Which tab opens first is a decision that gets
  stated**: the complete population opens, never a ranked subset of it.
- **If a sentence names a fact, the page must be able to show it.** The
  portfolio answer band names the client closest to qualifying and the evidence
  is in the other tab, so the name switches tab and lands on the row
  (`?ptab=call&focus=<id>`). Tabbing a claim away from its support is worse
  than the scroll it replaced.
- **One filter grammar, `col:expr;col:expr`, written once.**
  `lib/gridFilter.js` and `tools/grid_filter.py` agree on it; writing it twice
  is how a control means one thing on screen and another in the query. Types
  are `~text` contains · `>=n` / `n..m` numeric · `a|b` enum and year.
  - **Where the filtering happens is a function of ROW COUNT.** 5 clients and
    36 location-years filter in the browser; the unit grid's 10,236 employees
    filter in SQL. Both narrow through the same expression.
  - **The column name is never interpolated unless it matched a whitelist**,
    and every value is bound. `EMPLOYEE_FILTERS` / `NEAR_FILTERS` in
    `gold_reader.py` are that whitelist; the two alias the same column
    differently, so one shared map would emit an unknown alias.
  - **An enum offers the values PRESENT in the data.** A hardcoded list goes
    stale the first time a status is renamed and then offers a filter matching
    nothing, which reads as "no rows" rather than "no such value".
  - **An unparseable term is DROPPED, never passed through.** A predicate that
    silently matches everything is worse than no filter, because the page says
    it is filtering and the total says otherwise. It is dropped at parse so it
    cannot appear as an active chip, and the endpoint echoes `filters_applied`
    rather than the page assuming its own request took effect.
  - **A filtered grid states what it is hiding** — "12 of 37", a chip per
    filter, and a clear. A filter the reader forgot they set is how somebody
    reports a wrong total, so the statement outranks the layout.
  - **A filter narrows the LIST, never the answer.** Tab counts, stat cards and
    the answer band read the API's unfiltered total. Where a figure genuinely
    cannot be computed unfiltered — the within-band cusp count — it is
    WITHHELD and says why; a filtered cusp count is a different figure wearing
    the same words.
  - **Two cohorts filter independently.** `filter` and `near_filter` are
    separate, or narrowing the counted list silently moves the near-miss count
    under a tab nobody is looking at.
  - Sort and filter both live in the query string on the three page grids
    (book, client, location), so a driven view is shareable and survives a
    refresh.
  - **Every list table sorts and filters** (29 Sep). A table inside a page
    declares its columns and uses `useTableControls` + `SortHeader` +
    `FilterBar`, with the logic in `lib/tableSort.js` over the same
    `gridFilter.js` grammar; its state is the component's own, because several
    to a screen in the URL reads as noise. A SERVER-PAGED table (Eligibility,
    payroll source rows) sorts on the server before the page is cut — sorting
    one page in the browser presents 50 rows as the top of a list they are not
    the top of. Deliberately not sortable: before/after comparisons, the
    calculation walk, and the Position cross-tabs, whose row order is a
    statement.
- **A column earns its width or it does not ship.** `weeks_worked` is on the
  unit grid because 40 hrs/wk over 6 weeks and over 52 render identically
  without it. `weight` renders ONLY where it varies — it is 1.00 for almost
  everybody, and a constant column costs the same width as one that says
  something, which is the rule the client grid already applies to tier.
- **Rows are 28px and the fold is measured, never eyeballed.**
  `python frontend/tools/measure_ui.py` at 1024×768 reports visible rows and
  the first-row y per page. A layout change reports both before and after; the
  gate is that visible rows do not regress. `frontend/tools/design_metrics.py`
  counts the scale violations, and `check_brand.py` reads the computed font and
  the state colours off the rendered page.
- **28px rows diverge from Carbon ON PURPOSE; the type did not.** Carbon's
  data-table sizes are xs 24 / sm 32 / md 40; 28px was a measured decision for
  an operator who thinks in spreadsheets, and the visible-row gate defends it.
  Carbon's 16px column padding is halved to 8px for the same reason — at 16px
  the narrowest trend cell drops to 39px. Both numbers are measured, not
  preferred: `check_cell_fit.py` fails when a figure is wider than its cell.
- **A selector defined twice is drift, and the later one wins silently.**
  `.tbl-compact th, td` was declared 1100 lines apart with different sizes,
  which is how the trend grid ended up below the data floor while the file
  looked like it said 12px.
- Third-party UI: `lucide-react`, `react-simple-maps`, `react-markdown` +
  `remark-gfm`, `recharts`. Do not add more without asking.

---

## Tests

```pwsh
cd backend ; $env:TCC_REQUIRE_PARITY=1 ; pytest tests/ -q
cd frontend ; npm test ; npm run build
```

- Live-Fabric tests are opt-in: `TCC_FABRIC_TESTS=1`. They skip cleanly so CI
  never needs a lakehouse. `conftest.py` copies only `FABRIC_*` out of `.env` —
  never `DATA_SOURCE`, which stays pinned to `csv` for the suite.
- **Two parity gates, not one.** `tests/certified.py` pins the private
  reference figures (10,236/539/656) against `backend/data/payroll/`, which is
  gitignored — `test_engine_parity_reference.py` skips without it, and
  `TCC_REQUIRE_PARITY=1` turns that skip into an error. `tests/certified_synthetic.py`
  pins a second, smaller figure (81/51/49) against the **committed** synthetic
  `backend/data/payroll_pay_periods.csv` — `test_engine_parity_synthetic.py`
  never skips, so a clone of the public repo still proves the engine against
  *something* with no private extract and no flag. CI runs the synthetic gate
  on every push; the private one only where the fixtures exist. Neither file
  is ever edited to make a test pass [WL-11].
- New endpoint → backend endpoint test **and** an `api.test.js` case.
  New rule pack → `test_rule_packs.py` picks it up automatically.
  New pure helper → a unit test.
- **Behaviour-preserving refactors keep URLs and response shapes stable** and
  prove it by leaving the suite green with no test edits.

---

## Repository layout

```
backend/
  api/              FastAPI routers — thin, orchestrate only
  application/      Commands, queries, the mediator, and the composition root
  domain/           Entities, ports, and the pure calculation
  infrastructure/   Adapters behind those ports
  tools/            Services around the core: rule loading, runners, portfolio
  config.py         Runtime configuration the calculation reads
  rules/            rules/<program>/<year>.json per statute year
                    rules/methodology/ — assumption sets + certified figures
  data/             Source readers, synthetic generators, source-schema projection
  tests/            Parity gate, architecture rules, endpoint contracts
frontend/src/
  pages/            The four routed drill pages, one read each
  components/       One file per view, each with a .test.jsx
  lib/              Pure logic — scope, coverage, answers, derivation, tour
  api.js            Single network layer
frontend/server/    Express BFF (Node 24) — serves dist/, proxies /api
infra/              Terraform — root + modules/ (network, monitoring, identity,
                    app_service, storage, keyvault, foundry, fabric), profiles/, tests/
scripts/            postprovision, migrations, Warehouse grants, seed, packaging
docs/               ADRs, schema, calculation rules
                    docs/architecture/c4/ — the C4 model (model.json)
stakeholder-docs/   Partner methodology sources (read-only). `_*.md` is gitignored
```

---

## What not to do

- **No real PII in tracked files.** `backend/data/payroll/` is local-only and
  gitignored. Never commit, log, prompt, deploy, or screenshot it. Employee IDs
  may display after auth but must not enter URL paths, logs, telemetry, Foundry
  prompts, or exports.
- **Do not fabricate a value the system does not compute.** Label it or derive it.
- **The seeded `claimed` figures are invented and must say so.**
  `data/seed_claims.py` supplies them because no prior filing exists for any
  account. The identified side is real; claimed is not, and therefore neither is
  recoverable or exposure, which are `identified − claimed`. Every note reads
  *"Illustrative assertion — no prior filing supplied"*, `decided_by` names the
  script, and Position's Recoverable card says *"vs an unverified claim"*.
  `tests/test_seeded_claims_are_labelled.py` fails if a note starts implying a
  form number, a provider or a self-filing. Disclose this before showing any
  screen with a dollar sign on it.
- **Do not invent tax rules in prompts.** If it is not in a rule pack, the agent
  says so and stops. That is the audit-defensibility story.
- **Do not extrapolate in code** beyond an explicit, labelled run-rate. No ML.
- **Do not add infrastructure** (APIM, Service Bus) without an ask. **Key
  Vault exists only behind `enable_key_vault`** (default `false`): the stack
  holds no secrets, so the vault is off unless a deployment needs one.
- **Do not store secrets.** `DefaultAzureCredential` + `az login` locally,
  Managed Identity deployed. **Never put a secret in a `.tfvars` or
  `main.tfvars.json`** — every app setting Terraform writes is a non-secret.
- **Never let Terraform register resource providers.** Keep
  `resource_provider_registrations = "none"`; the operator registers them.
- **Entra authentication and employer binding are a hard gate** before deploying
  anything against private payroll. See [SECURITY.md](../SECURITY.md).
