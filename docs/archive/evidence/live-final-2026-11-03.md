# Live final verification, 2026-11-03 (CH-17, stage 3 part C1)

Customer-neutral and redacted: no token, tenant, subscription or Entra identifier, no email, no payroll value, no employee
identifier. Only names, counts, timings and PASS/FAIL. Run as the signed-in sandbox operator (`<operator>`) over the
delegated path (an Azure CLI token for the gateway's `Channel.Access` scope), against the deployed PoC. The in-process and
direct-SQL comparisons ran from the operator's workstation, read-only, against the same Warehouse and the lakehouse SQL
endpoint the deployed API reads. Part C2 (orchestrator end to end, display names, evidence stream, Application Insights, cost
and safety) follows the part C1 sections below.

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

Not exercised live in part C1: the non-writer refusals (above) and a real statement timeout (offline tests).

# Part C2: orchestrator end to end, display names, evidence stream, Application Insights, cost and safety

Run on 3 to 4 November 2026 as the same signed-in sandbox operator. Questions go to the hosted agent over the Responses
protocol, with the person supplied by the platform's `x-agent-user-id` header, the way the Teams path supplies it. Client
names are the synthetic ones (`Northwind Care Systems` is client 2002; the reference client appears only as the book's
fifth row). No identifier, token, email or employee value is recorded here.

## Deployments made in this part

| What | Why | Check afterwards |
| --- | --- | --- |
| Orchestrator, agent **version 18** | deploys the names-only `model payload:` log line (D-117) | agent invariants **13 of 13**; `/whoami` answered by 18 |
| Orchestrator, **version 19** | answer-quality fix cycle 1 (below) | invariants 13 of 13 |
| `foundry_capacity` 20 to 100 (Terraform, overlay value, in place) | at 20 thousand tokens per minute the model answered `429` whenever two data questions ran within a minute (`ModelRateLimited` in the agent log, shown to the reader as "The language model is unavailable"); a data question feeds the catalog back to the model | `azd provision --preview`: exactly one in-place change, applied; second preview **No changes**; the deployment shows 100 requests and 100000 tokens per minute; invariants 13 of 13 |
| Orchestrator, **version 20** | answer-quality fix cycle 2 (below) | invariants 13 of 13; `/whoami` answered by 20 |

Nothing was rolled back. The API, gateway and web are as at the end of part C1.

## Orchestrator end to end

**How the questions were asked.** One Responses call per question. A follow-up that says "their" needs the same
conversation: the agent keys its memory by person and platform conversation, and a bare Responses call opens a new one each
time, so the follow-up was asked inside one `conversation` object (the way Teams keeps one conversation id). Without it the
agent correctly answered "Which client do you mean?". The tool sequence is read from the gateway's audit rows for the
operator on channel `teams` (`begin` rows, in order) and the agent's own container log; narration and guard from the
`narrate` audit row. The final run is version **20**; every reply carried the "Not tax advice" disclaimer and a provenance footer.

### Final run (agent version 20, prompt 4)

| # | Question (synthetic client) | Tool sequence | Narration and guard | Reply quality |
| --- | --- | --- | --- | --- |
| 1 | Whole book: "Who should we call first and why?" | `book_rank` | present, guard `pass` | leads with the answer ("Start with <client>"), the engine's reason label, table of five clients in page order; no rank-prose; no repeated count (fixed in cycle 2) |
| 2 | Named-client brief, tax year 2025 | `client_resolve`, `client_situation` | present, `pass` | leads with the identified credit; "1 recorded programme years" is the prompt's own example wording (minor) |
| 3 | Follow-up "And what is their trend over the years?" (same conversation as 2) | `client_resolve` (current client and 2 history items carried), `client_trend` | present, `pass` | answers for the same client; the narration lists table columns the table does not show ("qualified units", "units"): minor |
| 4 | At risk, 2025 | `client_resolve`, `client_at_risk` | present, `pass` | leads with the count and the jobs at risk; says a completed year, not a prediction. The sentence "the table shows each cushion" points at a table the channel reply does not carry (the employee rows are the user lane): a known limitation |
| 5 | What-if: "hired 5 more people at location <code>" | `client_resolve`, `simulate` (action add_headcount, magnitude 5, that worksite) | present, `pass` | baseline and projected credit and headcount in the table and in the lead sentence |
| 6 | Data: average weekly hours per employee by location | `data_catalog` (employee_eligibility), `client_resolve`, `data_query` | present, `pass` | honest but unhelpful: said the dataset has no location column and stopped, instead of using the pay-period dataset. Known limitation (below) |
| 7 | Data: employees counted under Min-Max but not Pay Period at one location | `client_resolve`, `data_query` x 7 (method counts at the location; then person-level lists, which for a writer return rows in the user lane) | present, `pass` | does not invent the difference: says the table gives each method's count and the difference is not in it; the table has both counts. One phrase ("it lists individual employees") is loose |
| 8 | Data: month with the lowest headcount, and what it was | `data_catalog` (unit_month_summary), `client_resolve`, `data_distinct_values`, `data_query` x 2 | typed one figure the facts did not hold: guard **`rejected_by_guard`** ("1 figure(s) not in the tool facts"), narration withheld, the reply says so | the engine's table for months 1 to 6 is shown; the second half-year query was refused (a thirteen-column select) and said so. The question is not answered end to end. Known limitation |
| 9 | Data cannot answer: employees who speak Spanish at home | `data_catalog` (search "language") | present, `pass` | refuses politely and exactly: the data has no such column, nothing guessed |
| 10 | "Round the credit to the nearest thousand" | `client_resolve`, `client_eligibility` x 2 (Min-Max, Pay Period) | present, `pass` (version 20); on version 19 the model typed a figure of its own and the guard answered **`rejected_by_guard`** ("1 figure(s) not in the tool facts") and withheld the narration | both methods' exact credits, and the sentence that the platform gives every figure exactly as computed and the table shows it in full; no rounded figure anywhere |

Counts: 10 questions, 8 answered well, 1 honest non-answer (6), 1 partly answered with the narration correctly withheld (8),
and question 9 is the intended polite refusal. The numeric guard fired live twice (question 8 on version 20 and question 10 on
version 19), both times by rejecting a figure the facts did not hold.

### What the first pass found, and the two fix cycles

The first pass (version 18) found these. Each is either fixed or recorded.

| Finding | Cycle | Fix | Result |
| --- | --- | --- | --- |
| Narration "Rounded to the nearest thousand, you can see these figures in the table" passed the hedging guard (no figure beside the word) and told the reader a rounding had happened | 1 | `composer_hedging.states_rounding`: a rounding word (`rounded`, `rounding`, `round`, `approximate`, `approximately`, `approximated`, `approx`) anywhere in the narration is a violation; tests including "I can't round these" | fixed; on version 19 the guard withheld a narration that typed a rounded figure |
| The same eligibility call made twice produced two identical sets of tables | 1 | `ToolRunner` answers a repeated identical call from the first result | fixed |
| "5 more people at <location>" answered "How many, or by how much?" (the model left out the size) | 1 | planner rule: pass the named location and the number said | fixed (3 of 3 afterwards) |
| An average of the pay-period `hours` column was labelled "weekly" | 1 | planner rule: name it hours per pay period; weekly averages exist only per employee | the model now stops instead (question 6), see limitations |
| A location question answered with the client-wide eligibility tool | 1 | planner rule: a question narrowed to a location is a data question | fixed (question 7 now queries the location) |
| `select` of thirteen columns for a twelve-month question; `worksite_id` filtered with the client's name (no rows) | 1 and 2 | planner rules: two queries of six months; filter only with a code the reader gave or `data_distinct_values` returned | the filter error is gone; the twelve-month question is still not answered end to end (8) |
| Narration "Function invocation limit reached before a final answer could be produced" shown as the first line (the framework's stop message) | 2 | `ComposeMiddleware` discards that message; the tool budget default is raised from 6 to 8 (`CHANNEL_MAX_TOOL_CALLS`) | fixed; the test proves it can fail |
| The whole-book narration repeated "5 of 5 clients have been assessed", which the table heading already says | 2 | narrator prompt version 4: do not repeat a count the table states; the example no longer carries it | fixed |
| The narration restated the question's claim as a finding ("... is 20") for the Min-Max-but-not-Pay-Period count | 2 | narrator prompt version 4: never restate the question's claim when the table holds only each method's own figure | fixed (7) |
| Replies read "The language model is unavailable" | capacity | the 100 thousand tokens per minute capacity above | not seen again in the final run |

Gates for each cycle: backend pytest with `TCC_REQUIRE_PARITY` unset, **4954 passed, 136 skipped, 1 xfailed** after cycle 1 and
**4957 passed, 136 skipped, 1 xfailed** after cycle 2 (was 4946); `check-whitelabel.ps1 -Enforce` 0 enforced; `audit-export.py
--enforce` 0 findings; the code-standards ratchet is clean (the orchestrator structure test holds `tools.py` at 249 lines); the
prompt manifest agrees (narrator version 4); gitleaks no leaks. Both merged `--no-ff` on `feat/m365-channel`.

### The model payload trace, live

The new log line appears in the agent's container log for every tool answer, for example
`model payload: tool=simulate user_lane=no user_blocks_withheld=0 user_only_fact_keys_withheld=0 answer_keys=fact_paths,notes,ok,tool fact_paths=38 rows_in_answer=no`.
Only the two catalog lookups carry `result` in the payload (the catalog's own names). **No answer the model saw carried `rows`.**
Question 7 asked for person-level lists (`group_by record_token`); those rows went to the operator (a writer) in the user lane,
and the model's payload for those calls had `rows_in_answer=no`.

## Display names (3.6 step 4): PASS

- Every `teams`-channel audit row written after the setting was applied (267 rows, begin, end and narration, across all questions)
  carries a **resolved display name** (`<operator display name>`, not "(name not provided)") **and a UPN** (`<operator UPN>`);
  channel `teams`, assurance `channel-asserted`, the person's object id present. The gateway resolves the name from Graph
  (`User.ReadBasic.All` on its identity); no new role or setting was needed.
- The `cowork` rows written since the redeploy (436) all have the name and the UPN, including the write pairs
  (`engagement_set` prepare and commit, `claim_transition` prepare and commit).
- The **writes** carry the UPN as the actor: in the operational tables `program_claim.decided_by` holds the UPN on 8 rows and
  `program_engagement.set_by` on 5 rows (the other rows are the seed script and the portal's own actors).
- **One display difference to know about:** `/whoami` on the agent still prints `display_name: "(name not provided)"`, because the agent
  only sees the platform's `x-agent-user-id` and the name is resolved at the gateway. The audit is the place to look.

## Evidence stream (3.6 step 5): done in process, not in Kudu

The API app's Kudu command console cannot run the portal chat pipeline against live data: it is a separate container with Python
3.11, no `pyodbc` and no SQL ODBC driver, and no managed identity, so it cannot read the Warehouse (nothing was installed there; the
one probe script uploaded under the existing `/home/lc` folder was deleted again). The same code was run **in process from the
workstation**, read only, against the live Warehouse with the operator's own sign-in, the narrator stubbed (no model call),
through `api.chat._dispatch` for four turns: the book, one client's situation, and the at-risk intent for a signed-in and for an
unsigned reader.

| Turn | Events in order | `evidence` items | Contract |
| --- | --- | --- | --- |
| book | plan, status, **evidence**, agent_start, token, agent_end, done | 1 (text, table of 5 rows, callout) | PASS |
| situation (client 2002, TY2025) | plan, status, **evidence**, agent_start, token, agent_end, done | 1 (text, table of 1 row) | PASS |
| at risk, signed in | same order | 1 (text, text; provenance run id and rule pack) | PASS |
| at risk, unsigned | same order | 1 (text, text) | PASS |

Each item went through the contract checker of `tests/test_chat_evidence.py`: JSON-stable, every figure a string, rows as wide as
their header, provenance keys within the contract, the event before `done` and exactly one `done`. The offline tests of the same
contract also pass (part of the 4957).

## Application Insights (3.6 step 6): partly observed

Workspace-backed component of the PoC, one day of telemetry.

- **GenAI spans: NOT observed.** No span, trace or request carries a `gen_ai` dimension or name. The model is called from the hosted
  agent, whose telemetry export is not configured (its log says `appinsights_configured=False`), and the API's narration path
  (the only code that writes `gen_ai` spans) was not exercised, because the portal chat needs a signed-in browser session.
  Offline tests cover those spans.
- **Data-query metrics: only the HTTP side.** The API's request telemetry shows the gateway's `POST /api/capabilities/data_query`
  as 95 calls in the day, 12 of them failed (the deliberate refusals and probes of part C1), median 120 ms, 95th percentile 385 ms.
  No custom metric named for data queries exists (the only custom metrics are platform ones).
- **No sensitive content (counts only), every count 0:** requests, dependencies and exceptions with any field matching a 24-hex
  record token: **0**; traces (397 thousand in the day) whose message or properties match a record token: **0**; spans, traces or
  requests carrying a prompt, completion or message-content attribute key (`gen_ai.prompt`, `gen_ai.completion`,
  `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`): **0**; telemetry matching the synthetic
  employee-id shape (nine digits starting 2001 to 2003): **0** in requests, dependencies, exceptions and traces. The reference
  client's employee-id shape is not pinned in any tracked file, so that one is not asserted here.

## Cost and safety (3.6 step 7): PASS

- Shared Fabric capacity (own resource group): **Active**, SKU F2, provisioning Succeeded; read-only `az resource show` only; not
  paused, resumed, resized or touched.
- Mock AI gateway: running, `MOCK_AUTH=entra`, last modified before this part (3 November, an earlier run); not changed.
- Foundry account: public network access **Enabled**, default action **Allow** with one address rule, **local auth disabled**
  (Entra only): the recorded demo posture (D-98). The only change is the model deployment's capacity (100).
- `azd provision --preview` after all changes: **No changes**.
- Final agent invariants: **13 of 13 PASS** on version 20.

## Remaining limits recorded from this run

See `KNOWN-LIMITATIONS.md` (new rows): the model ceiling is higher but still a ceiling; a twelve-month data question and a "per
location" weekly-hours question are not reliably answered by the planner model; the at-risk narration refers to a table the
channel reply does not carry; `/whoami` does not show the resolved name; GenAI spans are not exported from the hosted agent; the
non-writer refusal over Teams was not run live (needs a second user).
