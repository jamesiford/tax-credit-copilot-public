# Gold layer specification — the application's read schema

> **Schema v2.0 (Platform v2):** the Warehouse schemas are now `tcc_gold` and `tcc_ops` (were the v1 `flex_*` schemas), configurable via `GOLD_SCHEMA` / `OPS_SCHEMA`. See `docs/data/schema/tcc-schema.fabric.sql`.

**Version** 0.3 · **Date** 2026-09-07 · **Status** Draft for Sam Hameed
**Author** James Ford · **Scope** What the engine writes, and what every screen reads

> **Changed in 0.2 — Gold is now the read schema, not just an output.** 0.1
> described Gold as what the engine emits. The application now reads it and
> nothing else: no calculation runs on a page load. That promotion adds the
> whole credit layer to §4.5 and a new table in §4.6, because a table the app
> reads has to hold everything a screen shows — not just the calculation chain.

> **New in 0.1.** Group B was previously described inside
> [`OPERATIONAL-DATA-MODEL.md`](OPERATIONAL-DATA-MODEL.md) alongside the
> operational tables. That conflated two stores with different jobs. Calculation
> output is analytical, high-volume and read-mostly; it belongs in the Fabric
> medallion, not in the operational store. This document is the Gold layer
> (`tcc_gold`); the operational model is now `tcc_ops` only. Since
> [ADR-007](../architecture/ADR-007-warehouse-operational-store.md) both are
> schemas in the Fabric Warehouse, and the retired document store is gone.

---

## 0. Build status — read before planning against this

**This document specifies a target, and most of it is now built.** An
independent audit on 7 Sep found the schema deployed and completely empty; the
write and read paths were built on 8 Sep.

| | Status |
| --- | --- |
| The schema itself | **Deployed.** All 20 tables live in the Fabric Warehouse, verified against this spec |
| Rows in those tables | **Populated** for the clients that have been run |
| The write path (a run populates Gold) | **Built.** `application/commands/run_client_calculation.py` → `infrastructure/persistence/warehouse_gold.py` |
| The read path (screens read Gold) | **Built** for Position by location. `infrastructure/persistence/gold_reader.py` serves `GET /api/v2/clients/{id}/units`, and that page load runs no engine |

The reference client (account 1001, TY2023) was written on 8 Sep as run
`76348c5c3bcf411ca6b636cd1e23e3ec`: 384,418 `employee_period_fact` rows, 20,472
`employee_eligibility`, 20,041 `onezero_matrix`, 202 `unit_month_summary`, 202
`unit_year_master`. It has no `unit_credit_installment` rows because 1001 has
only a base year; Cascade (2001) carries 190 and proves that path. All 20 §9
validations return zero rows.

**The certified figures were re-derived from SQL, not asserted:**
`COUNT(DISTINCT employee_id)` over `employee_period_fact` returns **10,236**, and
`employee_eligibility` grouped by method returns **539** Min-Max and **656** Pay
Period. The calculation engine is unmodified.

**Still on the v1 engine-per-request path:** One/Zero detail
(`/api/onezero/matrix/{year}`), Who qualifies (`/api/eligibility/{year}`), and
the sealed workspace views. Those are read paths this document's contract has not
yet been applied to. `GET /api/trend/units` was removed once the v2 read replaced
it; the engine behind it now runs at write time instead.

---

## 1. Where this sits

```
Partner intranet DB   ──►  Bronze  ──►  Silver  ──►  [ENGINE]  ──►  Gold
   Payroll, Employment,     raw,      canonical BCS,   One/Zero      this
   Location, Entity,      immutable    tokenised,      statutory     document
   PayCode, Account                    QC-flagged      calculation
```

Bronze and Silver are specified in
[`SOURCE-SCHEMA-MAPPING.md`](SOURCE-SCHEMA-MAPPING.md) §3 — the Silver Record
Layout projection. **That mapping is current and needs no change.**

### The read/write contract

**A run is the only writer.** An operator triggers a recalculation for one
client; the engine executes and writes Gold. **Every screen then reads Gold and
nothing else.**

```
source payroll ──▶ [ENGINE, on demand, per client] ──▶ Gold
                                                        │
                                    every screen reads ─┘
```

There is deliberately **no bulk run** — a portfolio-wide sweep takes too long to
sit behind a button. Three consequences shape the tables below:

1. **Gold must hold everything a screen shows.** A grid showing headcount but
   computing its dollars at display time defeats the purpose. This is why §4.5
   gained thresholds, tiers, eligible jobs and `annual_credit_usd`, and why §4.6
   exists at all.

2. **Absence of a run is a state, not a zero.** Without a bulk run, most clients
   are unassessed most of the time. A screen must distinguish *"not yet
   calculated"* from *"calculated, and the answer is zero"*. Rendering the first
   as the second would look like a client with no payroll.

3. **Every row carries `run_id`**, and a rerun supersedes rather than overwrites.
   These figures land on a filed return and must be reproducible years later
   against the exact inputs and rules that produced them.

**Decision state:** persistence store is settled — Fabric medallion, per
[ADR-002](../architecture/ADR-002-production-persistence.md). Whether Gold
lives in its own lakehouse or a schema alongside Bronze/Silver is Sam's open
call; see §6.

---

## 1a. Which screen reads which table

| Screen | Reads |
| --- | --- |
| The book — who to call | `program_claim` + `program_engagement` *(`tcc_ops`)*, ranked by `PriorityBand` |
| Location grid | `unit_year_master` + `unit_month_summary` + `unit_credit_installment` |
| Who qualifies | `employee_eligibility`, pivoted across both methods |
| One/Zero detail | `onezero_matrix` + `run_method_summary` |
| Employees at a location | `onezero_matrix` + `employee_eligibility`, joined on `record_token` |
| Near the floor at a location | `employee_eligibility` + `employee_period_fact` — `onezero_matrix` holds only the qualified, so a cusp count taken from it is always zero |
| One employee's derivation | `employee_eligibility` + `onezero_matrix` + `employee_period_fact`, all keyed on `record_token` |
| In-year progress | `unit_month_summary` (the series) + `run_method_summary` (the prior-year base) |
| Who is near the line (chat) | `employee_eligibility`, bounded to `avg_weekly_hours >= min_hours - B` |
| Which counted jobs could fall out (chat) | `employee_eligibility` where `eligible = 1`, banded above either floor |
| How a client moved across years (chat) | `run_method_summary` + `unit_year_master`, one row per tax year |
| Run status and freshness | `run_manifest` *(ops)* |

**`record_token` is what makes the employee-grain reads a LOOKUP.** It is stored
on `employee_eligibility`, `onezero_matrix` and `employee_period_fact`, so
opening one employee is a `WHERE` clause across three tables in one round trip.
The sealed workspace resolves the same handle by re-minting one for its whole
population, because it has no Gold behind it; a per-client read that copied that
pays two engine replays to answer a question about one person.

Dimension attributes — client name, unit county, city, census tract — are **not**
duplicated into Gold. They stay in the source tables in the same lakehouse and
join at read time. Copying them would create a second version of a fact that
already has an owner.

**`record_token` is the drill key.** A deterministic SHA-256 of
`(client_id, program_code, tax_year, employee_id)`, first 24 hex characters. It
is stored rather than recomputed so a drill URL joins straight to a row, and
because it is derived identically everywhere, a token minted by one read always
resolves in another. Employee IDs may be displayed after authentication but must
never enter a URL, a log line, telemetry or a prompt.

### The employee grain covers every year, not just the requested one

Until 10 September 2026 a run wrote `unit_year_master` for every priceable year
but `employee_eligibility`, `onezero_matrix` and `employee_period_fact` for only
the year it was asked for. The consequence was invisible on the location grid
and fatal everywhere else: *who qualifies* could be answered for one year out of
six, so the read path replayed both certified methods over the client's whole
payroll on every page load to cover the rest.

The replay was already computing those rows for every year and discarding them.
It now persists them. **Writes are allowed to be slow; a page that cannot answer
is not** — see the volumetrics in §7 for what that costs on F2.

---

## 2. Why this is not the operational store

| Table | Rows per client-year | Access pattern |
| --- | --- | --- |
| `employee_period_fact` | ~201,000 | Analytical scan, columnar |
| `employee_eligibility` | 20,472 | Scan and filter |
| `onezero_matrix` | ~20,000 | Scan, pivot |
| `unit_month_summary` | ~200 | Aggregate read |
| `unit_year_master` | ~101 | Aggregate read, cross-year |
| `unit_credit_installment` | ~500 | Aggregate read, `GROUP BY` |

Roughly a quarter of a million rows per client-year, scaling linearly with
headcount, read by Power BI and by the portal's grid views. The retired document
store would have worked and would have been the wrong tool: no columnar
compression, a request cost on every scan, and no Direct Lake path to BI.

The `tcc_ops` tables are the opposite shape — small, written interactively by a
human, read by key. That is the split. Both now live in the Fabric Warehouse
([ADR-007](../architecture/ADR-007-warehouse-operational-store.md)), but as
separate schemas with separate jobs.

---

## 3. Grain and keys

Every table below carries the same four-part scope. **`client_id` is the
partition boundary** and matches the partner's own `PayrollRange_PS([Accountid])`.

| Column | Type | Note |
| --- | --- | --- |
| `client_id` | `int` | Tenant. `Payroll.Accountid` in the source. Partition key. |
| `tax_year` | `int` | Fiscal year per `EntityFiscalYearRules` (BA-01), **not** calendar year |
| `method` | `string` | `pay_period` or `min_max`. Both run; neither is authoritative alone. |
| `run_id` | `string` | The run that produced the row. Join key to the run manifest. |

`method` is a real dimension, not a variant. The engine computes both methods
for every client-year and reconciles them (BA-11); a row without `method` is
ambiguous.

---

## 4. The tables

### 4.1 `employee_period_fact` — the normalised denominator grain

One row per employee per pay period, after the Silver collapse. This is the
input the engine reduces, and the only table that scales with payroll volume.

> **It holds only the rows the run CONSUMED.** `included` is `1` everywhere and
> `selection_decision` is `fiscal_window`, because a row that fell outside the
> window never reaches the writer. That is a real gap, not a simplification:
> the employee drill used to re-read the payroll and mark the excluded
> paychecks, and *"why is this person short a month"* is usually one of them.
> The drill now names the absence rather than showing a silently shorter list.
> Closing it is a WRITE-path change — the column already exists to carry the
> answer.

| Column | Type | Source |
| --- | --- | --- |
| `client_id`, `tax_year`, `run_id` | | scope |
| `employee_id` | `string` | tokenised; never `ClientEmployeeID` |
| `worksite_id` | `string` | `Payroll.WorksiteLocationId` (Q3 open) |
| `entity_fein` | `string` | via `Payroll.EntityId` |
| `pay_period_start`, `pay_period_end` | `date` | |
| `pay_date` | `date` | nullable in source — Q1 open |
| `period_days` | `int` | actual span. Drives BA-03. |
| `hours` | `decimal(18,2)` | NULL ≠ 0 — Q2 open |
| `wages` | `decimal(18,2)` | same |
| `pay_code` | `string` | BA-07 inclusion |
| `included` | `bool` | survived the pay-code filter |
| `qc_flag` | `string` | null, `test_of_twos`, `short_period` |

Partition by `client_id`, `tax_year`. This is the one to get right.

### 4.2 `employee_eligibility`

One row per employee per method per year. Engine field names in brackets —
these are the actual keys emitted by `run_min_max_method` /
`run_pay_period_method`.

| Column | Type | Engine field |
| --- | --- | --- |
| `client_id`, `tax_year`, `method`, `run_id` | | scope |
| `employee_id` | `string` | `Employee_ID` |
| `total_hours` | `decimal` | `total_hours` |
| `total_wages` | `decimal` | `total_wages` |
| `first_start` | `date` | `first_start` |
| `last_end` | `date` | `last_end` |
| `days` | `int` | `days` |
| `weeks_worked` | `decimal(10,2)` | `weeks_worked` |
| `avg_weekly_hours` | `decimal(10,2)` | `avg_weekly_hours` |
| `avg_weekly_wages` | `decimal(10,2)` | `avg_weekly_wages` |
| `eligible` | `bool` | in `eligible_employees` |
| `weight` | `decimal(3,2)` | 1.0 full-time, `pt_weight` part-time (CALC-03) |

The engine emits `all_averages` including ineligible employees for drill-in;
persist all of them with the `eligible` flag rather than only the passes. A
near-miss is the most interesting row on the screen.

### 4.3 `onezero_matrix`

One row per eligible employee per unit per method. The twelve monthly cells are
the One/Zero decision itself.

| Column | Type | Engine field |
| --- | --- | --- |
| `client_id`, `tax_year`, `method`, `run_id` | | scope |
| `employee_id` | `string` | `Employee_ID` |
| `worksite_id` | `string` | `Worksite_ID` |
| `entity_fein` | `string` | `Entity_FEIN` |
| `first_pps` | `date` | `first_pps` |
| `last_ppe` | `date` | `last_ppe` |
| `weight` | `decimal(3,2)` | `weight` |
| `month_01` … `month_12` | `decimal(3,2)` | `months[0..11]` |

Store the twelve months as columns, not as an array. BI reads them as columns,
and a column is a filterable dimension where an array is not.

### 4.4 `unit_month_summary`

Per unit, per month, per method. Roll-up of 4.3.

| Column | Type | Engine field |
| --- | --- | --- |
| `client_id`, `tax_year`, `method`, `run_id` | | scope |
| `worksite_id` | `string` | `Worksite_ID` |
| `month_01` … `month_12` | `decimal(10,2)` | `month_totals[0..11]` |
| `total` | `decimal(10,2)` | `total` |
| `average_headcount` | `decimal(10,2)` | `average_headcount` — `total / 12` |
| `months_with_headcount` | `int` | count of non-zero months |
| `unreachable_months` | `VARCHAR(64)` | **new 2 Sep** — month positions no pay period spans. **Comma-separated, e.g. `'10,11'` — not JSON.** Written by `gold_projection.py`, parsed by `frontend/src/lib/goldTrend.js`. Empty/NULL when nothing is unreachable |

> **`average_headcount` divides by 12 always**, including months that scored
> zero. That matches the partner's own summary output and is question 24 on the
> outstanding list. Do not "fix" it to divide by months-with-data.

`unreachable_months` is new and load-bearing — see §5.

### 4.5 `unit_year_master`

Cross-year, per unit, **per method**. The base-year comparison that turns
headcount into credit. This is the table the partner maintains by hand today, and the
one the location grid opens on.

**Headcount and baseline**

| Column | Type | Note |
| --- | --- | --- |
| `client_id`, `worksite_id`, `program_code`, `method` | | scope |
| `tax_year` | `int` | one row per year |
| `average_headcount` | `decimal(10,2)` | from 4.4 |
| `is_base_year` | `bool` | inferred — see §5 |
| `base_average_headcount` | `decimal(10,2)` | the frozen baseline |
| `base_year_source` | `string` | `inferred` \| `override` |
| `net_new_vs_base` | `decimal(10,2)` | |

**Year completeness** *(added 2 Sep — see §5)*

| Column | Type | Note |
| --- | --- | --- |
| `months_reachable` | `int` | denominator for completeness |
| `year_complete` | `bool` | fills every *reachable* month |
| `declined` | `bool` | under half of monthly targets reachable |
| `decline_reason` | `string` | |

**Qualification and tier** *(added 0.2)*

| Column | Type | Note |
| --- | --- | --- |
| `threshold` | `decimal(10,2)` | statutory minimum new jobs |
| `threshold_source` | `string` | `designation` \| `rule_pack` |
| `qualified` | `bool` | |
| `status` | `string` | `base` \| `above_minimum` \| `below_minimum` \| `partial` \| `no_data` |
| `tier` | `string` | |
| `designation` | `string` | |
| `tier_source` | `string` | `prototype` \| `unassigned` |

`status` is decided in one place and must not be re-derived downstream.
`partial` means the client's payroll does not cover the year. A month whose
measuring date no pay period reaches is a **different fact** — the year is
complete and the calendar is the problem — and reporting that as a short year
would be wrong. `no_data` is neither: a unit with no headcount at all that year.

Unregistered units fall back to the rule pack's minimum and are marked
`unassigned` rather than silently defaulted to Tier 1.

**The stair-step and the credit** *(added 0.2)*

| Column | Type | Note |
| --- | --- | --- |
| `eligible_jobs` | `decimal(10,2)` | net-new above the **frozen base**; sizes the annual credit |
| `new_jobs_created` | `decimal(10,2)` | above the **running high-water mark**; opens a tranche |
| `high_water_mark` | `decimal(10,2)` | running max; never below base |
| `backfilled` | `bool` | re-qualified after a non-qualifying year |
| `per_job_usd` | `decimal(19,4)` | rule pack **as applied** |
| `tranche_years` | `int` | benefit window (GA = 5) |
| `annual_credit_usd` | `decimal(19,4)` | `eligible_jobs × per_job_usd` |
| `base_year_overridden` | `bool` | a human adjusted the base |
| `high_water_mark_overridden` | `bool` | a human adjusted the high-water mark |

**`eligible_jobs` and `new_jobs_created` are not the same number and both must be
stored.** The first is measured against the frozen base and sizes the annual
credit; the second is measured against the running high-water mark and sizes a
new tranche. In a recovery year the first is positive while the second is zero —
the jobs are claimable, but they are not fresh creation, so no new tranche opens.
This is Northwind's whole story. Storing only one makes the distinction
unrecoverable.

**`per_job_usd` and `tranche_years` are copied onto the row that used them.** A
statute amended between the run and the audit must not silently restate a filed
figure. With both factors present the arithmetic is checkable from the row alone.

The override *flags* live here; the override *itself* lives in
`tcc_ops.manual_override`. The flags exist so a screen can mark a figure as
adjusted without joining out to discover that nothing was adjusted.

Open question 4 from the operational model still stands: is this a Flex table
or does it belong in the canonical model the partner's team already maintains? It is a
cross-year business asset rather than app state.

---

### 4.55 `run_method_summary` *(new 10 Sep 2026)*

One row per `client_id × tax_year × method × run_id`. What a method concluded
about a client-year **as a whole** — properties of the run, which no other table
can carry.

| Column | Type | Note |
| --- | --- | --- |
| `client_id`, `tax_year`, `method`, `run_id`, `program_code` | | scope |
| `annual_average` | `decimal(12,2)` | the client-level One/Zero average |
| `eligible_employees` | `int` | this method's eligible count |
| `employees_evaluated` | `int` | everyone with payroll in the window |
| `matrix_rows` | `int` | employee × unit-segment rows produced |
| `unit_fein_rows` | `int` | summary grain |
| `contested_months` | `int` | see below |
| `month_ends` | `varchar(256)` | the twelve measuring dates, as measured |

**`contested_months` is why this table exists.** It counts employee-months where
one person appeared at more than one unit and the tie-breaker had to choose. The
matrix is **deduped before it is written**, so gold cannot show that a contest
happened — the evidence is destroyed by the very step that resolves it. The
One/Zero screen states the figure, so before this table the only way to recover
it was to re-run the engine over the whole client on every page load.

Candle Bottle TY2023: **32 under Min-Max, 0 under Pay Period.**

`month_ends` is derivable from the fiscal window, but deriving it on read means
the window logic runs twice and can disagree with itself. The run states what it
actually measured.

---

### 4.6 `unit_credit_installment` *(new in 0.2)*

Each qualifying year opens its own credit window, and a window pays an
installment in each of the following years. A given tax year's claimable figure
is the **sum of every live window's installment for it** — which is why this
cannot be a column on 4.5. One qualifying year in 2021 contributes to 2021
through 2026.

**Grain: `creation_year × claimable_year`, not claimable year alone.**

| Column | Type | Note |
| --- | --- | --- |
| `client_id`, `worksite_id`, `program_code`, `method` | | scope |
| `creation_year` | `int` | the year that opened the window |
| `tax_year` | `int` | the year the installment falls in |
| `tranche_jobs` | `decimal(10,2)` | window size at creation |
| `jobs_maintained` | `decimal(10,2)` | still above base this year |
| `per_job_usd` | `decimal(19,4)` | rule pack as applied |
| `claimable_usd` | `decimal(19,4)` | `jobs_maintained × per_job_usd` |
| `projected` | `bool` | no payroll yet; carry-forward assumption |

The screen wants one number per claimable year, which tempts you to store that
directly with a list of contributing creation years beside it. **Don't.** That
shape puts a multi-valued fact in one column and discards the per-window
arithmetic — you keep the total but lose which window paid what, so a figure that
looks wrong cannot be taken apart. The atomic row costs a `GROUP BY` on read:

```sql
SELECT tax_year, SUM(claimable_usd)
FROM   tcc_gold.unit_credit_installment
WHERE  is_current = 1 AND client_id = ? AND worksite_id = ? AND method = ?
GROUP  BY tax_year;
```

**`jobs_maintained` must sit beside the dollar.** A job is claimable in an
out-year only if that year's average headcount still sits above the frozen base
by at least the tranche size; where it doesn't, the installment is written down.
Without this column a reduced installment is indistinguishable from a rule
change.

**`projected` is load-bearing.** An installment in a year with *no payroll yet*
is a forecast on the carry-forward assumption that the job is maintained — not a
claim. That is a different statement from a measured installment that happens to
equal the full tranche, and the two must not render alike. Reported as
`claimable_usd` rather than `credit` for the same reason.

---

## 5. What changed on 2 September, and why it matters here

Commit `e11fb4b`, from the partner's feedback. Three of the columns above are new, and
one changed a published number.

**Year completeness is measured against reachable months, not twelve.** A month
scores only when a pay period spans its measuring date. A calendar-year client
has no period spanning 31 December, so **eleven months is that client's complete
year**. Judging against twelve rejected it as a base year and pushed the base a
year later — and the base year is the most leveraged input in the model.

Effect on the reference portfolio:

| | Before | After |
| --- | --- | --- |
| Cascade base year | TY2021 | **TY2020** |
| Portfolio claim | 229,285 | **607,110** |
| Certified figures (10,236 / 539 / 656) | — | **unmoved** |

**The divisor stays 12.** Only the completeness test changed.

**Years that reach under half their monthly targets are now declined** rather
than publishing an average of zero. Hence `declined` and `decline_reason`.

**Open — the Month-12 cliff.** Questions 23–25 in
[`REFERENCE-DATASET.md`](REFERENCE-DATASET.md). On Cascade, a final period
ending 12-15 scores Month 12 as **0**; ending 12-16 scores ~25. A one-day
difference in the pay calendar moves a location's annual average by roughly 8%,
and it affects two of six years on that client. This is unresolved and the model
should not be built as though it were settled.

---

## 5a. Target platforms — Fabric Warehouse *and* SQL Server

The partner's source payroll lives in SQL Server, so the fair question is whether
these tables have to be in Fabric at all. They don't. This was tested, not
assumed.

The DDL was executed against **SQL Server 2025**: every `CREATE TABLE`
succeeded, every data type was accepted, 41 of 52 statements ran unmodified.

**The direction of travel is the easy one.** Fabric Warehouse T-SQL is a
*subset* of SQL Server T-SQL, so Fabric → SQL Server *gains* capability. Writing
to the Fabric subset first is what makes both targets reachable from one file.

**The only incompatibility is `NOT ENFORCED`**, which is Fabric/Synapse syntax —
11 statements, a two-word deletion.

| Feature | Fabric Warehouse | SQL Server 2016+ |
| --- | --- | --- |
| 20 `CREATE TABLE` | yes | **yes, unmodified** |
| Data types | yes | yes |
| `DROP TABLE IF EXISTS` | yes | yes |
| `PRIMARY KEY` | `NONCLUSTERED NOT ENFORCED` only | **fully enforced** |
| Indexes | **not supported** | yes |
| CHECK constraints | **not supported** | yes |
| Filtered unique index | **not supported** | yes |

**The schema is strictly better on SQL Server.** The uniqueness Fabric cannot
enforce — one `is_current = 1` row per unit-year-method — becomes a filtered
unique index that rejects the duplicate at write time. On Fabric, §9's
validation queries are the *only* thing between you and a silently
double-counted credit. On SQL Server they become a backstop.

Two DDL files are generated from one source, so they cannot drift:

```
docs/data/schema/tcc-schema.fabric.sql       source of truth
docs/data/schema/generate_variants.py         the transform
docs/data/schema/tcc-schema.sqlserver.sql    generated — do not hand-edit
```

Both were run twice end to end: **Fabric 54/54, SQL Server 72/72**, idempotent.

### What actually determines portability is the application, not the DDL

Anything read over **T-SQL/ODBC** moves to SQL Server as a connection string and
an auth change — same driver, same SQL. Anything read over **OneLake**
(`abfss://` + the `deltalake` library) is Fabric-specific and does not move at
all.

The app currently reads source payroll over OneLake. Moving that read to T-SQL
is what keeps the platform a choice rather than a commitment — and it is cheap
today, because that path is still gated behind `DATA_SOURCE=fabric` and is not
exercised.

### A note on mirroring

If the partner mirrors SQL Server into Fabric, **the mirrored database is read-only
in Fabric** — `tcc_gold` and `tcc_ops` cannot live inside a mirror. Two
end-states work, both using this schema unchanged:

- source mirrored into Fabric, `tcc_gold`/`tcc_ops` in a Fabric Warehouse
- everything in SQL Server, Fabric used for BI only

---

## 6. Placement — Sam's call
Gold is Fabric per ADR-002. Two sub-decisions remain.

**Separate lakehouse, or a schema alongside Bronze/Silver?**

| | Separate lakehouse | Same lakehouse, own schema |
| --- | --- | --- |
| Security boundary | Clean — source PII never co-resident with output | Shared |
| Runtime identity | Needs permissions on **both**; two capacity conversations with Ali | One |
| Cross-layer joins | Cross-lakehouse | Native |
| Lifecycle | Independent | Coupled |

The app reads Flex source from OneLake today, so a separate Gold lakehouse means
the managed identity needs grants on both. The partner's team said on 27 August *"we can
create those schema within the lakehouse"* — worth deciding deliberately rather
than by default.

**Where do `run_manifest` and `source_snapshot` live?** **Resolved** by
[ADR-007](../architecture/ADR-007-warehouse-operational-store.md): both are
`tcc_ops` tables in the Fabric Warehouse. Every Gold row above carries `run_id`,
which makes the manifest an analytical join key, and with both schemas in one
Warehouse that join is native rather than cross-store. The earlier options — a
separate document store with a cross-store join, Gold only, or writing both —
no longer arise.

---

## 7. Volumetrics and retention

A quarter of a million rows per client-year, dominated by
`employee_period_fact`. Five clients across six years is roughly 7.5M rows —
small by Fabric standards, and the reason `employee_period_fact` should be
partitioned by `client_id` and `tax_year` from the start rather than retrofitted.

Georgia carries a **ten-year credit carry-forward**, so treat Gold as a ten-year
record at minimum. Confirm against the partner's statutory retention policy before
sizing. A filed figure must be reproducible years later against the exact inputs
and rules that produced it — that constraint is what forces `run_id` onto every
row.

### What a rebuild costs on F2 *(measured 10 September 2026)*

Widening the employee grain to every year turned a full rebuild into an hour-plus
operation on the shared F2 capacity:

| Client | Scope | Wall clock |
| --- | --- | --- |
| 1001 Candle Bottle | 10,236 employees, 1 priceable year | **68 min** |
| 2001 | 6 years | 8.5 min |
| 2002 | 6 years | 5.4 min |
| 2003 | 6 years | 10.6 min |
| 2004 | 6 years | 7.7 min |

CPU across the run sat near **3%** — it is write latency, not compute. That is
the SKU, not the code: a `TOP 1` against a 7-row table on this capacity costs
342ms, and no query engineering reaches below one statement's floor.

The trade was made deliberately and should be re-made the same way: a slow write
buys a page that can answer. But size production capacity against the 68-minute
figure, not against the synthetic clients.

---

## 8. What is certified, and what is not

The calculation reproduces the partner's methodology to the employee:

> **10,236 employees · 539 Min-Max eligible · 656 Pay Period eligible**

A CI gate reruns the reference dataset on every code change and fails if any of
those move. They did not move on 2 September.

**Headcount is certified. Credit value is not.** It needs county tier, industry
eligibility and the base-year comparison. County (`StateCountyZip.CountyName`)
and industry (`Account.IndustryTypeId`) are both present in the partner's schema, so
dollar certification is a plumbing problem rather than a data-availability one.

**This does not change when Gold becomes the read schema.** The engine stops
being the thing the app calls per request and becomes the thing that writes these
tables — but it is still the same engine, still under the same CI gate. That gate
is what proves the warehouse is right: it reruns the reference dataset against
the calculation directly, so it survives the migration unchanged and is the only
independent check that a stored figure matches a computed one.

---

## Document control

| | |
| --- | --- |
| Supersedes | Group B of `OPERATIONAL-DATA-MODEL.md` v0.2 §4 |
| Companion | `SOURCE-SCHEMA-MAPPING.md` (Bronze/Silver), `OPERATIONAL-DATA-MODEL.md` (`tcc_ops`), `Flex - Enrichment and Operational Schema DDL` (executable DDL) |
| Verified against | `backend/domain/calculation/onezero.py`, `backend/tools/unit_trend.py`, `backend/tools/baseyear.py` at commit `d1beefe` |

### Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.1 | 2026-09-02 | Split from `OPERATIONAL-DATA-MODEL.md`. Five tables. |
| 0.2 | 2026-09-07 | Gold promoted to the application's read schema. Added the read/write contract (§1), screen-to-table map (§1a), the qualification, tier and credit layers on `unit_year_master` (§4.5), and `unit_credit_installment` (§4.6). |
| 0.3 | 2026-09-07 | Added §5a target platforms. DDL verified on both Fabric Warehouse and SQL Server 2025; two variants now generated from one source. |
