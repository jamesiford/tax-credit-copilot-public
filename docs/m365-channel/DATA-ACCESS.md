# Governed data access

How the agent reached from Teams, Microsoft 365 Copilot and Cowork answers questions the fixed engine tools
cannot (the wage distribution at a location, which months drove a shortfall, who was counted under one method
and not the other), **without any model ever writing SQL or producing a figure**. Customer-neutral. The decision
is [ADR-009 §8](../architecture/ADR-009-m365-channel.md); the data itself is described in
[SEMANTIC-MODEL](../data/SEMANTIC-MODEL.md) (generated); settings are in [ENV-VARS](../architecture/ENV-VARS.md);
the network paths are R5a and CH10 in [CONNECTIVITY-MATRIX](../architecture/CONNECTIVITY-MATRIX.md).

## 1. The design in one page

```text
model (or a person)        API process                                             Fabric
 data_catalog   ─────►  semantic model ──────────────► what exists (no sample values)
 data_query     ─────►  QuerySpec ► validate ► build_sql ► executor ─────────────► Warehouse  (tcc_gold, tcc_ops)
 data_distinct_values ─►  (a structured spec, never SQL)        │ SELECT only, bound values, client first ► Lakehouse SQL endpoint (source tables)
                                                                 ▼
                              envelope: facts + blocks + provenance, split into two lanes
```

- **Semantic model** (`backend/application/data/`, rendered in [SEMANTIC-MODEL](../data/SEMANTIC-MODEL.md)): every
  queryable *dataset* (11 today: eight Gold and ops, three lakehouse source), its grain, its tenant column, and for
  every column a logical and physical name, type, meaning, **role**, **sensitivity** (`public_aggregate`,
  `employee_level`, `blocked`), allowed aggregations and allowed operators. Whatever is not in it cannot be asked.
- **Structured specification** (`QuerySpec`): `dataset`, `client_id`, `tax_years`, `select`, `measures`, `filters`,
  `group_by`, `order_by`, `limit`, `method`. There is **no field SQL could go in**. `validate()` rejects an unknown
  or blocked column, an operator or aggregation the column does not allow, a group-by of a measure, an `order_by`
  outside the selection, a limit over 500, a missing client, a year the client does not hold, a wrongly typed value,
  too many filters or measures, a list of more than 12 tax years, a client id outside a positive integer, and a value
  that reads as a statement (`;`, `--`, `/*`, a leading `select ...`, `xp_`, `@@`) or carries control characters.
  **Quotes are not screened:** a value is a bound parameter, so an apostrophe (O'Brien, Bakers' Group) is an ordinary
  name and cannot change the statement; `tests/test_data_query_abuse.py` proves it stays out of the SQL text. Each
  refusal is a typed code (`blocked_column`, `limit_too_high`, `sql_like_value`, …) the agent can say in words.
- **SQL building**: `build_sql` interpolates only whitelisted physical identifiers from the model. **Every value is a
  bound parameter.** The one SQL text the model carries is a derived column's expression (`pay_year`, `pay_month`);
  it must stay inside a closed grammar (`expression_grammar.py`: declared columns, `YEAR`, `MONTH`, `COALESCE`,
  `CAST ... AS INTEGER`, `strftime` with two formats, short integers, `+`, `*`) or the model cannot be built.
  Identifier and alias patterns end in `\Z`, not `$`, which would admit a trailing newline. The client scope is the
  first predicate, through the tenant helper (`tenant_sql.py`), so the
  architecture rules that govern every Warehouse adapter govern this one. T-SQL for the Warehouse and the lakehouse
  endpoint, SQLite for offline tests and local runs.
- **Execution**: a port (`DataQueryExecutor`) with three adapters. The Warehouse adapter and the lakehouse adapter
  share one T-SQL core and the API's managed identity. Only `SELECT` runs (the statement is checked; one statement,
  no `;`). Currency is part of the dataset: a Gold dataset is pinned to the client's live run (or `is_current`), so a
  superseded figure is never mixed with the filed one.
- **Three tools**, ordinary capabilities (registry, gateway catalog, MCP list, audit), all read-only:
  `data_catalog` (what exists, narrowed by `dataset` or `search`), `data_query` (the structured query),
  `data_distinct_values` (the values of one dimension, capped, so a filter such as a location name is not guessed).
  **The fixed tools stay authoritative** for the credit figure, eligibility and what the engine concluded;
  `data_query` returns exact rows and aggregates and does not interpret them. Where both can answer, an equivalence
  test holds them equal on the synthetic dataset (`test_data_equivalence.py`); a mismatch is a bug in the model.
- **Method is never chosen silently.** A method-dependent dataset (Min-Max, Pay Period) returns the method beside
  every answer; `both` returns both under the engine's labels.

## 2. The two lanes

| Lane | Holds | Who sees it |
| --- | --- | --- |
| **model-visible** (`audience: both`) | `facts` and blocks built from aggregates (a count by location, an average by month) | the narrating model, and the person |
| **person-only** (`audience: user`) | rows that carry an `employee_level` column (a record token, one person's hours or pay, a monthly One/Zero cell) and the `facts` derived from them (`user_only_facts`) | the person asking, in Teams or Copilot Chat; **never a model** |

The envelope itself carries the lane (`Block.audience`, default `both`; an audience word a consumer does not know is
read as `user`). The orchestrator's model-facing projection (`capabilities/lanes.py`: `model_facts`,
`model_blocks`) drops both, so a model is told the **count and the column names** and not the rows. The existing
egress rule (an employee identifier or record token never enters a prompt) is extended to the three tools by tests
(`test_data_lanes.py`, `test_orch_data_lanes.py`, `test_gw_data_lanes.py`).

**Copilot Cowork cannot honour the split**: its model composes from the text a tool returns, so a row shown to the
person is a row shown to the model. A result that lists individual employees is therefore **refused unless the caller
is positively first-party (Teams or Microsoft 365 Copilot Chat) or a writer** (RM-02: the test is positive, so it
fails closed), with a refusal that names Teams as the place to see rows. "Positively first-party" means the channel
gateway (holding the agent role) acting for a person whose Teams or Copilot Chat message it asserts
(`channel-asserted`); **everything else is treated like Cowork**: `cowork`, `api-test`, an unknown or missing
channel, and a person's own token sent straight to the API. It is enforced three times, each on its own evidence: the
API before anything is read, the API again on every finished result (`invoke`, so a capability that forgot the check
cannot leak), and the gateway on the way back; none rests on another. The channel an agent asserts is also bound to
the caller's registered app id (`CHANNEL_CALLER_CHANNELS`: a registered caller can claim only the channels it is
registered for; with none configured every registered caller keeps enum-level trust and the gateway says so at
startup). An aggregate over employee-level data carries no person and is allowed everywhere. The reasoning is in
[ADR-009 §8](../architecture/ADR-009-m365-channel.md).

**Small groups (RM-01).** An aggregate over an employee-level dataset (`employee_period_fact`,
`employee_eligibility`, `onezero_matrix`, `payroll`) shows only groups of at least **K distinct people**
(default **5**, `DATA_MIN_GROUP_SIZE`, never below **2**). The rule is applied in the data service, after the rows
are read and before any lane is projected, so the model lane and the person's lane obey it alike:

| Case | What happens |
| --- | --- |
| a group has fewer than K people | the group is **left out**, not merged, rounded or altered; the result says how many were (`facts.small_groups.suppressed_groups`, a note, the provenance) |
| an ungrouped aggregate over a filter that leaves fewer than K people | the single row is left out and counted the same way |
| every group in a group-by holds one person | refused, `groups_are_individuals`: it would list individuals |
| the caller is a writer | not applied; the result says `exempt: writer` (a writer may already read the client's employee rows; there is no per-client ownership beyond the API's client check) |
| the dataset is not employee-level (`unit_month_summary`, `unit_year_master`, `run_method_summary`, the credit and ops datasets, `location`, `pay_code`) | not applied: the grain is already a worksite or a year and no person key exists to count; the "both" lane for these is unchanged |
| raw rows with no aggregate | not applied: they are the person's lane (never a model's), and Cowork refuses them for a non-writer |

A group's size is counted in **people** (the dataset's declared `person_key`), not rows: twelve pay-period rows of
three people are a group of three. The count rides in the same statement as a hidden `_group_size` column that the
service removes, so the client scope stays the first predicate and no second query runs. When the row limit cuts a
result the count of groups left out covers only the groups fetched. Suppression does not stop differencing (two
queries differing by one person); see [KNOWN-LIMITATIONS](KNOWN-LIMITATIONS.md#data-queries).

## 3. Limits

| Limit | Value | Setting | On breach |
| --- | --- | --- | --- |
| Statement timeout | 20 s (1-120) | `DATA_QUERY_TIMEOUT_SECONDS` | typed `query_timeout`, never a partial result; the connection is discarded, which cancels the statement |
| Rows | spec `limit` ≤ 500, default 100; server cap 500 (1-500) | `DATA_QUERY_MAX_ROWS` | the result says it was capped; the cap can only lower a spec's limit |
| Per-person budget | 30 a minute (1-600), token bucket, per process | `DATA_QUERY_RATE_PER_MINUTE` | typed `query_budget_exceeded` (refused, not queued) |
| Concurrency | 4 in flight across all people (1-16) | `DATA_QUERY_MAX_CONCURRENCY` | typed `query_busy` after a 0.25 s wait |
| Smallest group | 5 people (2-1000; below 2 is read as 2) | `DATA_MIN_GROUP_SIZE` (not in Terraform: a privacy floor) | the group is left out and counted; every-group-a-singleton is `groups_are_individuals` |
| Spec size | 8 filters, 6 measures, 12 selected, 8 group-by, 4 order-by, 50 values in an `in`, 12 years, 100-char text | code (`spec.py`) | typed `too_many_items` |
| Reply table | the first 50 rows, with the number cut stated | code | the facts keep every row the cap allowed |

Every limit **refuses rather than queues**: a queued query is the load being avoided. Ceilings are per process; with
several workers the effective ceiling is the figure times the worker count.

## 4. Audit and provenance

- **Audit line.** `request_summary` records the dataset, selected dimensions, measures as `agg(column)`, group-by,
  years, method and limit, and each filter as `column op`. A filter **value** is written only where the model says
  the column is a public-aggregate dimension; on an employee-level, unknown or join column it is `<redacted>`.
  Names the model supplied are kept only if plain identifiers. `is_deterministic_path` is `true`; `run_id` and
  `trail_sha256` are recorded where the data has them.
- **Provenance on every result.** The dataset and physical table, the question as asked, the SHA-256 of the generated
  statement and, separately, of the parameters' *types and count* (never values), the rows returned, whether the cap
  cut the list (the blocks say so), the run id, rule pack and assumption set for Gold, the data's `as_of`, and a
  source line such as "Source: warehouse tcc_gold.unit_month_summary".

## 5. What is and is not queryable

**Queryable (11 datasets):** `employee_period_fact`, `employee_eligibility`, `onezero_matrix` (employee level),
`unit_month_summary`, `run_method_summary`, `run_manifest`, `unit_year_master`, `unit_credit_installment` (Warehouse),
and the lakehouse source `payroll` (employee level), `location`, `pay_code`. Grains, columns and what each measure
means are in [SEMANTIC-MODEL](../data/SEMANTIC-MODEL.md).

**Not queryable, each with a stated reason** (`model_excluded.py`): platform audit and security tables
(`channel_audit`, `agent_action_audit`, `artifact_access`, …), operational records, global registries with no client
key (rule-pack and assumption-set versions), seeded and unverified claims (the book tools own that reading), source
tables with no client key (`Employment`, `Address`, lookups), the client record itself, and legal entities.

**Never selectable, filterable or groupable** (`blocked`): any column that could identify a person. An employee
appears only as a **record token**; names, SSNs and emails do not exist in the model.

**Not offered at all:** joins other than the model's declared fixed joins (v1 is single-dataset plus those), free
text, subqueries, writes, cross-client queries (one client per call, the client being the first predicate), and a way
to see another client's data by naming it in a value.

## 6. Adding a dataset or a column

The drift test (`tests/test_semantic_model_drift.py`) is what forces a decision. **Adding a column to the DDL
(`docs/data/schema/tcc-schema.fabric.sql`) or a table to the lakehouse source schema without deciding about it fails
the build**; so does a Gold table with a client key that is neither modelled nor excluded with a reason, and a table
on both lists.

1. Decide: *model it* or *exclude it*. An exclusion needs a one-line reason in `model_excluded.py` (tables) or the
   dataset's `excluded_columns` (columns). A reason is mandatory; the test refuses an empty one.
2. To model it, add the dataset or column in the matching `model_*.py` with a logical name, type, **meaning in the
   customer's words**, role, **sensitivity** and the aggregations and operators it may take. Anything that could
   identify a person is `blocked`. Anything that is one person's pay or hours is `employee_level`. Money and hours
   carry a `unit`; every queryable column needs a description (tests enforce both).
3. State how live rows are identified (`live_run` or `is_current`) for a Gold dataset, and its method column if it
   holds both statutory readings. A derived column's expression is written for both dialects, names what it
   `depends_on`, and stays inside the grammar in `expression_grammar.py` (the model refuses to build otherwise;
   widening the grammar is a change to that file and `test_data_query_abuse.py`).
4. Regenerate the page: `python scripts/generate-semantic-model-doc.py` (a test fails if the committed
   [SEMANTIC-MODEL](../data/SEMANTIC-MODEL.md) and the model disagree).
5. **A new lakehouse dataset needs a grant**: `scripts/grant-warehouse-sql.py --profile lakehouse` reads its table
   list from the model, so the grant follows; a test asserts the two agree. Re-run postprovision (or the script).
6. If it overlaps an engine figure, add an equivalence test against the fixed tool, and say in
   [SEMANTIC-MODEL](../data/SEMANTIC-MODEL.md) which is authoritative.
7. Add golden questions for it (`tests/channel_orchestrator/golden/data_use.json`) so the planner is checked.

## 7. Operational notes

- **The Fabric capacity is shared and small (F2).** Every page load, calculation run and data query draws on it. The
  limits above exist to protect it, and they refuse rather than queue. A cold capacity can take tens of seconds to
  answer the first statement; the 20-second timeout will then fire, and the person is told to retry. The first live
  run (CH-17) measures this; widen `DATA_QUERY_TIMEOUT_SECONDS` only with evidence, to at most 120.
- **A timeout is an answer**, not an error to retry silently: no partial result is ever returned.
- **Counts are of rows.** A count over a pay-period dataset counts pay periods; `count_distinct` on `record_token`
  counts people. The catalog's notes say which.
- **The API identity can write the Warehouse; the data query cannot.** Read-only is enforced in code (a `SELECT`
  check, one statement, whitelisted identifiers, bound values), not by a read-only database principal, because the
  API's Warehouse grant is shared with the engine's writes. A separate read-only identity for data queries would add
  defence in depth and is not built.
- **Lakehouse source datasets are off until switched on**: `DATA_QUERY_SOURCE_ENABLED=true` (azd
  `TCC_DATA_QUERY_SOURCE_ENABLED`) and the read grant below. A disabled source is `data_source_disabled`, an
  unconfigured one `data_source_unavailable`; there is never a fallback to another store. Gold and ops datasets are
  not behind this flag.
- **Settings are all optional**, non-secret and API-only. The gateway never touches data directly.
- **Verified live (CH-17, 3 November 2026).** T-SQL execution on the Warehouse and the lakehouse SQL endpoint, the
  row cap, the pyodbc statement timeout (`HYT00` at the limit, classified `query_timeout`), the per-person budget and the
  concurrency bulkhead ran against Fabric, and every overlapping measure equalled the fixed tools and a direct read-only
  SQL ([evidence](../archive/evidence/live-final-2026-11-03.md)). Warm statements take well under a second; the first
  connection of a process about 3 s, so the 20-second default needs no widening. A genuine slow-statement timeout and
  the non-writer Cowork refusal are proven offline only.

## 8. Grants the lakehouse endpoint needs

The **API identity** already has the Fabric workspace role (default `Contributor`, Terraform `manage_fabric_access`)
and the T-SQL schema grants on `tcc_gold` and `tcc_ops`. The Gold and ops datasets need nothing more. The lakehouse
source datasets add exactly this, and nothing else:

| Where | Grant | Why |
| --- | --- | --- |
| Lakehouse SQL analytics endpoint database (`LAKEHOUSE_SQL_DATABASE`, default the lakehouse name) | `GRANT SELECT ON OBJECT::<SOURCE_SCHEMA>.Payroll TO [<API_IDENTITY_NAME>];` and the same for `Location` and `PayCode` | the three tables the semantic model reads. Object level: no schema grant, so a table added to the source later is **not** readable until the model names it and the grant is re-run |

- **Read-only.** Never `INSERT`, `UPDATE`, `DELETE`, `ALTER`, `CONTROL`, `db_owner` or `db_datawriter`, and no
  `DENY`/`REVOKE`. The generated statements are pinned by `tests/test_lakehouse_grants.py`.
- **The channel gateway identity gets none.** It has no path to the endpoint (CH10 in the connectivity matrix);
  the script refuses to grant it, and a test asserts postprovision never names it.
- **No new role, no new Azure RBAC, no Entra role, no resource provider.** The workspace role is unchanged. The
  explicit `SELECT` makes the read independent of that role, so it survives a later narrowing of the workspace role
  to Viewer; whether the role alone already suffices is confirmed on the live redeploy.
- **Idempotent.** `GRANT` repeats harmlessly. postprovision runs it after the schema grants, **only when
  `TCC_DATA_QUERY_SOURCE_ENABLED=true`**, through the target guard: the Warehouse is resolved and checked as for
  every SQL step, and the lakehouse endpoint must be on the **same host** (one host per Fabric workspace) or the
  script refuses (exit 3).
- **Who runs it.** Whoever runs `azd up` (it needs workspace Admin or Member, like every grant here). By hand:
  `python scripts/grant-warehouse-sql.py --target deployed --profile lakehouse` (add `--dry-run` to print).

## 9. Evaluation: a Microsoft Fabric Data Agent as an optional provider (not built)

**Recommendation: do not enable it for this channel; keep it off. Revisit only for a sandbox-only exploratory lane
under the conditions below.** This is an evaluation against Microsoft's documentation as of 3 November 2026; the
product is in preview and changing, so check the current documentation before acting.

**What it would add.** Free-form questions: a Fabric data agent turns a natural-language question into SQL, DAX or
KQL over the lakehouse, Warehouse or a semantic model, with no semantic-model authoring on our side. It would answer
questions the structured specification cannot express (arbitrary joins, ad hoc expressions) without a code change.

**Why it is off by default.**

1. **No per-user identity passthrough on this path.** Foundry's connector uses on-behalf-of with the *end user's*
   identity so the user sees only what they may. The hosted orchestrator here holds a **channel assertion** of the
   person, not a token of theirs ([ADR-009](../architecture/ADR-009-m365-channel.md): no on-behalf-of for Bot Service
   integrations). The agent would run as a **service identity** and read everything that identity can, and our
   per-client scoping is an application predicate that a model-written query can simply omit. Fabric row-level
   security needs a per-user identity to bite.
2. **Model-written queries break two invariants.** *Tools calculate*: the model chooses the SQL, so a figure is
   produced by a statement nobody reviewed, not by deterministic code. *Numeric exactness*: our guard checks that
   every numeral in a reply is a fact the engine supplied, and a free-form answer arrives as the data agent's prose,
   which the guard cannot bind to a fact. There is also no lane: person-level rows could reach a model.
3. **No model control.** The model the data agent uses for natural-language-to-SQL is Fabric's, not the one we
   choose; the model selected in the agent only orchestrates and words the reply. A bring-your-own model (the
   external gateway, [AI-GATEWAY](../architecture/AI-GATEWAY.md)) does not reach it, and the egress policy does not
   apply to what it sends.
4. **Audit and capacity.** The statement it runs is not our audit line (dataset, columns, operators), and it draws
   on the same shared F2 capacity without our budget, timeout or bulkhead.
5. **Moving ground.** Preview, a documented migration of the Foundry tool to a successor (the Fabric data agent tool
   is scheduled for deprecation on 6 November 2026 in favour of the Fabric IQ tool), a paid F2-or-higher capacity,
   and the data agent and its sources in one region.

**Conditions under which it could be enabled, for a sandbox-only exploratory lane.** All of them:

- synthetic data only (`DATA_CLASSIFICATION=synthetic`), never customer payroll;
- a separate, clearly labelled tool and agent that **cannot reach a figure that goes on a return**: its answers are
  marked "exploratory, not computed by the engine", it is never in the claim package, never offered a write, and
  the fixed tools remain the only source of any credit, eligibility or trend figure;
- it runs as a dedicated service identity with `SELECT` on a **copy or view set** that holds one synthetic client and
  no `employee_level` columns, so the absence of per-user passthrough and of the client predicate cannot expose
  another client;
- its answers are shown to the person as quoted text with the generated query, never passed through the numeric
  guard as facts, and never narrated further;
- a feature flag, default off, enabled per environment by the owner, with the statement it ran logged to the audit
  trail and the data agent's capacity use watched;
- the owner has decided that an unreviewed statement in a sandbox is acceptable, in writing (a DECISIONS entry).

Until a per-person token is carried end to end (the condition that also retires the channel assertion in
ADR-009), the structured path in this page is the way the agent reads data.

**Checked again on 2026-11-04 (RM-15).** The Foundry tool for a Fabric data agent is scheduled for deprecation on 6 November 2026 and replaced by the Fabric IQ
(OneLake Catalog) tool, which is preview; the ontology (preview) MCP server cannot currently be reached with a service principal and needs a paid F2 or higher
capacity. Neither changes the recommendation. The knowledge tier, which is about cited reference text and not tenant rows, is a separate design:
[KNOWLEDGE-AND-IQ.md](../architecture/KNOWLEDGE-AND-IQ.md) and [ADR-010](../architecture/ADR-010-knowledge-tier.md).
