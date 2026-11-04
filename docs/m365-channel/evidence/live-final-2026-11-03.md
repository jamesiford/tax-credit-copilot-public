# Live final verification, 2026-11-03 (CH-17, stage 3 part C1)

Customer-neutral and redacted: no token, tenant, subscription or Entra identifier, no email, no payroll value, no employee
identifier. Only names, counts, timings and PASS/FAIL. Run as the signed-in sandbox operator (`<operator>`) over the
delegated path (an Azure CLI token for the gateway's `Channel.Access` scope), against the deployed PoC. The in-process and
direct-SQL comparisons ran from the operator's workstation, read-only, against the same Warehouse and the lakehouse SQL
endpoint the deployed API reads. Later sections ("Orchestrator end to end", "Display names", "Evidence stream",
"Application Insights", "Cost/safety") are appended by the next part.

Code on the PoC for this run: the stage 3 part A deployment, plus **one API redeploy** during this part (see "A bug found
and fixed" under *Data tools live*). Gateway, web, agent (version 17) and the published 1.0.3 app are unchanged; the agent
invariants were re-checked at the end: **13 of 13 PASS**.

## Gateway smoke

`scripts/channel-live-smoke.py --only catalog,reads,writes,verify,audit --compare-local` (smoke id `27782a5c`):
**41 passed, 0 failed**, one honest SKIP (`finding_resolve`: client 2002 TY2025 has no open finding).
A second, read-only pass after the API redeploy (`--only catalog,reads,verify --compare-local`): **37 passed, 0 failed**.

| Check | Result |
| --- | --- |
| REST `tools/list` equals the catalog (plus the debug ping) | PASS, **32 tools**, nothing missing or extra (includes `data_catalog`, `data_query`, `data_distinct_values`) |
| MCP `tools/list` equals REST `tools/list` | PASS, 32 |
| No token is a 401; a wrong-audience token is a 401 | PASS, PASS |
| `book_rank` answers | PASS |
| Seven read tools (`client_resolve`, `client_situation`, `client_eligibility`, `client_trend`, `client_at_risk`, `client_discovery`, `calc_walkthrough`) on **two clients** (2001, 2002), each answering **and identical to the in-process engine** | 28 of 28 PASS (14 answer + 14 identical, both clients) |
| Write round trip: `engagement_set` prepare then commit | PASS (200/200) |
| Idempotent retry returns the first result (`replayed`) | PASS |
| `claim_transition` forward to `proposed`, then **restore to `assessed`** | PASS, PASS (the cell is back to its original status; history rows remain by design) |
| `verify_figures` accepts a figure from the returned facts; rejects a one-digit mutation | PASS (`pass`), PASS (`rejected`) |
| Audit: every request of the data-tool run (131 requests with a `final-` correlation id, all tools, for the operator) is `channel=cowork`, `identity_assurance=delegated` | PASS (131 of 131; 116 `ok`, 15 `error` = the deliberate refusals and probes) |
| Non-writer refused | **NOT RUN LIVE**, see below |
| 429 rate limit / 413 size cap | not re-run (proven offline and in the first live smoke) |

**Why the non-writer check was not run live.** `channel-live-smoke.py --only nonwriter` needs a delegated token of a person
who is neither on the writer allow-list nor in the writers group. The first live smoke obtained one by temporarily removing
the operator from the allow-list. This part is verification only and changes no infrastructure or directory state, and no
second tenant user's token is available on this workstation (the other signed-in account belongs to a different tenant),
so the check was left to the offline tests, which cover both halves of the rule: the API refuses before anything is read
(`test_data_capabilities.py`, the Cowork employee-level tests; the refusal costs no budget) and the gateway refuses on the
way back (`test_gw_data_lanes.py`, `channel/lane_guard.py`). A non-writer over the **Teams** path is the orchestrator end
to end part's business (identity through `x-agent-user-id`).

## Data tools live

Specifications are structured objects; the model never writes SQL. Every comparison is between three independent reads of
the same aggregate: the **gateway** (deployed API, Warehouse or lakehouse endpoint), the **fixed capability** where one
overlaps (`client_trend`, `client_eligibility`), and a **direct read-only SQL** statement run from the workstation
(`SELECT` only, counts and totals, never rows). Two clients: a synthetic one (2001, TY2025) and the reference client
(1001, TY2023). Final run: **99 passed, 0 failed, 99 checks**.

### Catalog and distinct values

| Check | Result |
| --- | --- |
| `data_catalog`: 11 datasets, sources `warehouse` and `lakehouse` | PASS |
| `data_catalog(dataset=payroll)`: 15 columns, blocked ones (`employee_id`, `client_employee_id`) not offered | PASS |
| `data_catalog(search=...)` narrows | PASS |
| `data_distinct_values` on `unit_year_master.worksite_id`, `unit_year_master.designation`, `location.location_name`, synthetic client | 6, 2 and 18 values, none cut |
| the same three, reference client | 100 (cut, there are 101), 1, 100 (cut) |
| a person-level column (`employee_eligibility.record_token`) | refused, `column_not_listable` (422), both clients |
| distinct worksite count against direct SQL | synthetic 6 = 6; reference 100 of 101 (capped, reported as cut) |

### `data_query`: nine specifications per client, each compared

| # | Specification | Gateway = direct SQL | Gateway = fixed tool | Notes (counts only) |
| --- | --- | --- | --- | --- |
| S1 | people (`count_distinct record_token`) by worksite, `onezero_matrix`, Min-Max | PASS both clients | n/a | 6 / 101 groups; provenance run id equals the manifest's live run |
| S1b | distinct people for the whole client, Pay Period | PASS both | PASS = `client_trend.eligible_employees` | |
| S2 | credit and eligible jobs by worksite, `unit_year_master`, Pay Period | PASS both (6/6, 101/101 groups) | PASS: summed credit = `client_trend.annual_credit_usd` | |
| S3 | headcount by month (`month_01`..`month_12` in two halves), by method, `unit_month_summary` | PASS both (2/2 methods) | PASS: summed `average_headcount` = `client_trend` (Pay Period) and `client_eligibility` (Min-Max) | |
| S4 | by designation: distinct sites and credit | PASS both (1/1 groups) | n/a | |
| S5 | **method comparison**, `run_method_summary`, `method=both` | PASS both | PASS: annual average both methods, Pay Period eligible count | both methods returned and labelled; reference client returns **539 Min-Max and 656 Pay Period** |
| S6 | **lakehouse source payroll**: rows, wages, hours by pay year | PASS both on the lakehouse SQL endpoint (7 and 2 groups; 84,718 and 384,433 payroll rows) | n/a | audience `both` (an aggregate carries no person) |
| S6b | source payroll rows by location name through the declared join | PASS both (top 20 location counts equal) | n/a | |
| S7 | **enriched Gold aggregate**: pay periods, hours, wages, distinct people by worksite, `employee_period_fact` | PASS both (6/6, 101/101 groups) | n/a | audience `both` |
| S8 | **capped**: `limit=7` and `limit=500` over worksite x pay period start | n/a | n/a | rows = 7 with `truncated=true` and the reply says it was cut; 500 rows, `truncated=true`, the reply table shows the first 50 |
| S9 | **employee_level**: `record_token`, `avg_weekly_hours` for eligible employees, `limit=5` | n/a | n/a | writer over the delegated path: 200, **1 of 7 blocks marked `user`**, `user_only_facts=[rows]`, 5 rows |

Refusals checked live, both clients: `limit=501` is refused (`invalid_arguments`, 422); a column name carrying SQL text is
refused (`unknown_column`, 422); a person-level column is not listable.

### The employee-level lane (S9)

- **Over the delegated path for a writer:** the user lane arrives (rows in a `user` block).
- **Model-facing projection of the live envelope** (`capabilities/lanes.py`: `model_facts`, `model_blocks`): the `rows` fact
  and the user block are dropped; of the 5 record tokens in the envelope **none** appears in the projection (17 fact keys and
  6 blocks remain, all aggregate or descriptive).
- **The orchestrator's model-facing answer** for the tool (`toolset.model_answer`, built on the same live envelope): keys
  `fact_paths`, `notes`, `ok`, `tool` only, 25 fact paths, no `result`, none of the 5 tokens anywhere in it.
- **Diagnostic line (new, names and counts only).** The orchestrator now logs one line per tool answer, for example
  `model payload: tool=data_query user_lane=yes user_blocks_withheld=1 user_only_fact_keys_withheld=1
  answer_keys=fact_paths,notes,ok,tool fact_paths=25 rows_in_answer=no`. It is covered by offline tests
  (`test_orch_data_lanes.py`) and was checked here against the live envelope. **It is in the repository and not yet in the
  deployed agent (version 17):** it appears in the agent's log from the next orchestrator deployment.
- **Refused for a non-writer over Cowork:** not run live (see the note under *Gateway smoke*); covered offline at both
  layers (API before reading, gateway on the way back).

### Timeouts, caps and the budget (small scale, no load)

| Behaviour | How it was exercised | Result |
| --- | --- | --- |
| Row cap | S8 above | 500 rows maximum, cut reported, reply table 50 rows |
| Statement timeout | the executor's own driver mechanism: a `WAITFOR` with a 1 s limit on the Warehouse connection | driver error `HYT00` after 1.1 s, which the executor classifies as `query_timeout`; no rows. The real queries finish in well under the 20 s default (a warm statement 0.3 s, the first connection 3.0 s, 1.5-2.8 s through the gateway), so a genuine statement timeout could not be provoked without load and was not forced |
| Per-person budget | in process with the budget lowered to **2 per minute**, tiny query on a synthetic client | calls 1 and 2 answered; calls 3 and 4 refused `query_budget_exceeded` with `retry_after` 27 s, 0.0 s each, nothing read |
| Concurrency bulkhead | in process with concurrency 1, three tiny simultaneous queries | one answered, two refused `query_busy` after 0.3 s (refuse, never queue) |

The 30 per minute default was not exceeded through the gateway (about 50 calls in two minutes across both clients, none refused).

### Audit of the data tools

262 audit events (begin and end of each request) carry this part's data-tool correlation ids: 134 `data_query`, 54
`data_distinct_values`, 22 `data_catalog`, the rest the other tools called for the comparisons. `request_summary` for the data tools is `dataset=..., select=..., measures=agg(column), limit=...`: longest 170
characters, and the 23 summaries that name `record_token` name the **column**, never a value. No filter values appear.

### A bug found and fixed (the one mismatch)

`data_distinct_values` on a dataset that holds both statutory readings lists each value once per reading, and the limit
counted **rows**. A limit of 100 therefore listed 50 worksites for the reference client and said the list was cut, so a client
with 101 worksites could not be enumerated past 50 (the first run of this check: gateway 50, direct SQL 101). The semantic
model was right; the capability was wrong. Fix (branch `wp/CH-17-distinct-values-cap`, merged `--no-ff`): fetch twice the
limit for a method-dependent dataset, merge, cut at the limit and report truncation from the merged list; three tests added
(`test_data_capabilities.py`). Backend suite: **4946 passed, 136 skipped, 1 xfailed** (was 4942 plus the 4 new); the
whitelabel, audit-export and ratchet gates are clean and gitleaks reports no leaks. **Redeployed: API only**
(`azd deploy api`); live re-run: 100 of 101 listed and reported cut. The `GIT_COMMIT` app setting still names the part A
commit, because stamping a new value needs `azd provision`, which this part does not run.

No other mismatch: every overlapping measure agrees across the gateway, the fixed tools and the direct SQL.

## Not covered by this part

Display names, the evidence stream, Application Insights and the cost/safety check are the next part's.
Not exercised live: the non-writer refusals (above) and a real statement timeout or 429 (offline tests).
