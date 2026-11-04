# Semantic model

> Generated from `backend/application/data/` by `scripts/generate-semantic-model-doc.py`. Do not
> edit by hand: a test fails when this file and the model disagree.

The agent reached from Teams, Microsoft 365 Copilot and Cowork may ask questions of the
payroll and the enriched data, but it never writes SQL. It fills in a structured query; the
platform checks it against the model below, builds the statement from the model's own
physical names, binds every value and scopes it to one client before anything runs. This
page lists what exists, what one row means, and which tool is authoritative when more than
one can answer.

## How to read it

- **Grain** is what one row is. Counting rows counts that, which is not always people.
- **Sensitivity** describes the *raw* value. `employee_level` is one person's pay or hours:
  rows that carry it go to the person asking and are not shown to a model, while an aggregate
  over a group (a count by location, an average by month) can be narrated. `blocked` columns
  exist in the tables and can never be selected, filtered or grouped. People appear only as a
  record token.
- **Currency**: Gold keeps superseded runs. `live run` pins the client's current run and
  `is_current` takes the current row, so a restated figure is never mixed with the filed one.
- **Method**: where a dataset holds both statutory readings (`min_max` and `pay_period`), the
  method is always returned beside the answer and never chosen silently.
- **The fixed tools stay authoritative.** For the credit figure, eligibility or what the engine
  concluded, quote `client_eligibility`, `client_trend`, `client_at_risk` or `simulate`. A data
  query returns exact rows and aggregates; it does not interpret them, and where it can
  reproduce an engine figure it equals it (an equivalence test enforces that).
- **Small groups**: an aggregate over one or two people is close to a person's own figure.
  The privacy design is the delivery lane, not this model.

## Datasets

| Dataset | Source | Table | Employee level | Currency | One row is |
| --- | --- | --- | --- | --- | --- |
| `employee_period_fact` | warehouse | `gold.employee_period_fact` | yes | live_run | One row per employee per pay period, after the payroll was normalised. The only table that scales with payroll. |
| `employee_eligibility` | warehouse | `gold.employee_eligibility` | yes | live_run | One row per employee per method per tax year, eligible or not. |
| `onezero_matrix` | warehouse | `gold.onezero_matrix` | yes | live_run | One row per eligible employee per worksite per method per tax year; twelve monthly One/Zero cells. |
| `unit_month_summary` | warehouse | `gold.unit_month_summary` | no | live_run | One row per worksite per method per tax year; twelve monthly headcounts. |
| `run_method_summary` | warehouse | `gold.run_method_summary` | no | live_run | One row per client per tax year per method. |
| `run_manifest` | warehouse | `ops.run_manifest` | no | none | One row per calculation run, superseded runs included. |
| `unit_year_master` | warehouse | `gold.unit_year_master` | no | is_current | One current row per worksite per programme per method per tax year. |
| `unit_credit_installment` | warehouse | `gold.unit_credit_installment` | no | is_current | One current row per worksite per method per creation year per tax year. |
| `payroll` | lakehouse | `source.Payroll` | yes | none | One row per employee per pay period per pay code, exactly as received. |
| `location` | lakehouse | `source.Location` | no | none | One row per client worksite. |
| `pay_code` | lakehouse | `source.PayCode` | no | none | One row per client pay code. |

## Dataset reference

### `employee_period_fact`

The denominator grain: every pay period the run consumed, with its hours, wages and why it counted or not.

**Grain:** One row per employee per pay period, after the payroll was normalised. The only table that scales with payroll.

- Client key: `client_id` (applied for you, always the first predicate).
- Tax year: `tax_year`.
- Dates: `pay_period_start`, `pay_period_end`, `pay_date`.

| Column | Type | Role | Sensitivity | Unit | Meaning | Allowed |
| --- | --- | --- | --- | --- | --- | --- |
| `tax_year` | int | dimension | public_aggregate |  | The tax year the run assigned the row to. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `run_id` | text | identifier | public_aggregate |  | The calculation run that wrote the row. The live run is selected for you. | agg: count, count_distinct; filter: none |
| `record_token` | text | identifier | employee_level |  | The opaque handle for one employee in one client, programme and tax year. The only way a person appears. | agg: count, count_distinct; filter: eq, in |
| `worksite_id` | text | dimension | public_aggregate |  | The worksite the job is counted at (the payroll's worksite location). | agg: count, count_distinct; filter: eq, in |
| `entity_fein` | text | dimension | public_aggregate |  | The legal entity's federal tax id. | agg: count, count_distinct; filter: eq, in |
| `job_title` | text | dimension | public_aggregate |  | Job title on the payroll row. | agg: count, count_distinct; filter: contains, eq, in |
| `pay_period_start` | date | dimension | public_aggregate |  | First day of the pay period. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `pay_period_end` | date | dimension | public_aggregate |  | Last day of the pay period. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `pay_date` | date | dimension | public_aggregate |  | Date paid. Blank where the source carried none. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `period_days` | int | measure | public_aggregate | days | Inclusive length of the pay period. It drives the BA-12 week count. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `pay_frequency_code` | text | dimension | public_aggregate |  | The source's pay-frequency key, kept as lineage only and never used as a week multiplier. | agg: count, count_distinct; filter: eq, in |
| `hours` | decimal | measure | employee_level | hours | Hours on the payroll row. Blank is not zero. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `wages` | decimal | measure | employee_level | USD | Wages on the payroll row. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `pay_code` | text | dimension | public_aggregate |  | Payroll pay code of the row. | agg: count, count_distinct; filter: contains, eq, in |
| `included` | bool | flag | public_aggregate |  | True when the row survived the pay-code filter and counted (BA-07). | agg: count, sum; filter: eq |
| `selection_decision` | text | dimension | public_aggregate |  | Why the row did or did not count: inside the fiscal window, too short, filtered by pay code. | agg: count, count_distinct; filter: eq, in |
| `qc_flag` | text | dimension | public_aggregate |  | Quality-control mark: test_of_twos, short_period or none. | agg: count, count_distinct; filter: eq, in |

Never queryable: `employee_id`.

**Relation to the engine's tools**

- `hours, wages, included`: Inputs to the engine, not results. The engine's own totals are on employee_eligibility; use client_eligibility for the verdict.
- `row counts`: Counts pay periods, not people. Use count_distinct on record_token for people.

### `employee_eligibility`

The engine's verdict on every employee, with the hours and wages behind it. Near misses are rows too.

**Grain:** One row per employee per method per tax year, eligible or not.

- Client key: `client_id` (applied for you, always the first predicate).
- Tax year: `tax_year`.
- Method: `method` (`min_max` | `pay_period`; returned with every row).

| Column | Type | Role | Sensitivity | Unit | Meaning | Allowed |
| --- | --- | --- | --- | --- | --- | --- |
| `tax_year` | int | dimension | public_aggregate |  | The tax year of the verdict. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `method` | text | dimension | public_aggregate |  | Which statutory reading produced the row: min_max or pay_period. Never mixed silently. | agg: count, count_distinct; filter: eq, in |
| `run_id` | text | identifier | public_aggregate |  | The calculation run that wrote the row. The live run is selected for you. | agg: count, count_distinct; filter: none |
| `record_token` | text | identifier | employee_level |  | The opaque handle for one employee in one client, programme and tax year. The only way a person appears. | agg: count, count_distinct; filter: eq, in |
| `total_hours` | decimal | measure | employee_level | hours | Hours across the employee's counted pay periods. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `total_wages` | decimal | measure | employee_level | USD | Wages across the employee's counted pay periods. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `first_start` | date | dimension | public_aggregate |  | Start of the employee's first counted pay period. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `last_end` | date | dimension | public_aggregate |  | End of the employee's last counted pay period. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `days` | int | measure | public_aggregate | days | Days from first start to last end. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `weeks_worked` | decimal | measure | public_aggregate | weeks | Weeks in the span, as the engine measured them. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `avg_weekly_hours` | decimal | measure | employee_level | hours/week | Average weekly hours, rounded half-up to two places; the rounded value is what the floor tests. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `avg_weekly_wages` | decimal | measure | employee_level | USD/week | Average weekly wages, rounded half-up to two places. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `eligible` | bool | flag | public_aggregate |  | The engine's verdict. Equals 'cleared both floors' only where no part-time band applies. | agg: count, sum; filter: eq |
| `weight` | decimal | measure | public_aggregate | jobs | 1.00 for full-time, the part-time weight otherwise; the job count is the sum of weights. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |

Never queryable: `employee_id`.

**Relation to the engine's tools**

- `eligible`: client_eligibility reports the eligible count and annual average from the same run; it is authoritative. This dataset lets you break it down.
- `avg_weekly_hours, avg_weekly_wages`: client_at_risk ranks the employees close to a floor; use it for 'who could fall out'.

### `onezero_matrix`

The One/Zero decision for each employee who qualified: counted (1 or the part-time weight) or not (0) in each month.

**Grain:** One row per eligible employee per worksite per method per tax year; twelve monthly One/Zero cells.

- Client key: `client_id` (applied for you, always the first predicate).
- Tax year: `tax_year`.
- Method: `method` (`min_max` | `pay_period`; returned with every row).
- Months: `month_01` to `month_12` (fiscal months).
- Dates: `first_pps`, `last_ppe`.

| Column | Type | Role | Sensitivity | Unit | Meaning | Allowed |
| --- | --- | --- | --- | --- | --- | --- |
| `tax_year` | int | dimension | public_aggregate |  | The tax year of the matrix. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `method` | text | dimension | public_aggregate |  | Which statutory reading produced the row: min_max or pay_period. Never mixed silently. | agg: count, count_distinct; filter: eq, in |
| `run_id` | text | identifier | public_aggregate |  | The calculation run that wrote the row. The live run is selected for you. | agg: count, count_distinct; filter: none |
| `record_token` | text | identifier | employee_level |  | The opaque handle for one employee in one client, programme and tax year. The only way a person appears. | agg: count, count_distinct; filter: eq, in |
| `worksite_id` | text | dimension | public_aggregate |  | The worksite the employee is counted at. | agg: count, count_distinct; filter: eq, in |
| `entity_fein` | text | dimension | public_aggregate |  | The legal entity's federal tax id. | agg: count, count_distinct; filter: eq, in |
| `first_pps` | date | dimension | public_aggregate |  | First pay-period start in the employee's span. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `last_ppe` | date | dimension | public_aggregate |  | Last pay-period end in the employee's span. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `weight` | decimal | measure | public_aggregate | jobs | The employee's weight: 1.00 full-time, the part-time weight otherwise. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_01` | decimal | measure | employee_level | jobs | The One/Zero cell for fiscal month 1: counted or not. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_02` | decimal | measure | employee_level | jobs | The One/Zero cell for fiscal month 2: counted or not. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_03` | decimal | measure | employee_level | jobs | The One/Zero cell for fiscal month 3: counted or not. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_04` | decimal | measure | employee_level | jobs | The One/Zero cell for fiscal month 4: counted or not. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_05` | decimal | measure | employee_level | jobs | The One/Zero cell for fiscal month 5: counted or not. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_06` | decimal | measure | employee_level | jobs | The One/Zero cell for fiscal month 6: counted or not. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_07` | decimal | measure | employee_level | jobs | The One/Zero cell for fiscal month 7: counted or not. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_08` | decimal | measure | employee_level | jobs | The One/Zero cell for fiscal month 8: counted or not. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_09` | decimal | measure | employee_level | jobs | The One/Zero cell for fiscal month 9: counted or not. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_10` | decimal | measure | employee_level | jobs | The One/Zero cell for fiscal month 10: counted or not. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_11` | decimal | measure | employee_level | jobs | The One/Zero cell for fiscal month 11: counted or not. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_12` | decimal | measure | employee_level | jobs | The One/Zero cell for fiscal month 12: counted or not. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |

Never queryable: `employee_id`.

**Relation to the engine's tools**

- `month_NN`: Summed by worksite these are the monthly headcount on unit_month_summary. The matrix holds only people who already qualified, so it cannot show a near miss.

### `unit_month_summary`

The monthly headcount at each worksite, as the One/Zero method counted it. The shape the partner reads the credit in.

**Grain:** One row per worksite per method per tax year; twelve monthly headcounts.

- Client key: `client_id` (applied for you, always the first predicate).
- Tax year: `tax_year`.
- Method: `method` (`min_max` | `pay_period`; returned with every row).
- Months: `month_01` to `month_12` (fiscal months).

| Column | Type | Role | Sensitivity | Unit | Meaning | Allowed |
| --- | --- | --- | --- | --- | --- | --- |
| `tax_year` | int | dimension | public_aggregate |  | The tax year of the summary. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `method` | text | dimension | public_aggregate |  | Which statutory reading produced the row: min_max or pay_period. Never mixed silently. | agg: count, count_distinct; filter: eq, in |
| `run_id` | text | identifier | public_aggregate |  | The calculation run that wrote the row. The live run is selected for you. | agg: count, count_distinct; filter: none |
| `worksite_id` | text | dimension | public_aggregate |  | The worksite (unit) the headcount is for. | agg: count, count_distinct; filter: eq, in |
| `month_01` | decimal | measure | public_aggregate | headcount | Headcount at the fiscal month 1 measuring date. Zero can mean no pay period reaches that date. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_02` | decimal | measure | public_aggregate | headcount | Headcount at the fiscal month 2 measuring date. Zero can mean no pay period reaches that date. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_03` | decimal | measure | public_aggregate | headcount | Headcount at the fiscal month 3 measuring date. Zero can mean no pay period reaches that date. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_04` | decimal | measure | public_aggregate | headcount | Headcount at the fiscal month 4 measuring date. Zero can mean no pay period reaches that date. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_05` | decimal | measure | public_aggregate | headcount | Headcount at the fiscal month 5 measuring date. Zero can mean no pay period reaches that date. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_06` | decimal | measure | public_aggregate | headcount | Headcount at the fiscal month 6 measuring date. Zero can mean no pay period reaches that date. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_07` | decimal | measure | public_aggregate | headcount | Headcount at the fiscal month 7 measuring date. Zero can mean no pay period reaches that date. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_08` | decimal | measure | public_aggregate | headcount | Headcount at the fiscal month 8 measuring date. Zero can mean no pay period reaches that date. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_09` | decimal | measure | public_aggregate | headcount | Headcount at the fiscal month 9 measuring date. Zero can mean no pay period reaches that date. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_10` | decimal | measure | public_aggregate | headcount | Headcount at the fiscal month 10 measuring date. Zero can mean no pay period reaches that date. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_11` | decimal | measure | public_aggregate | headcount | Headcount at the fiscal month 11 measuring date. Zero can mean no pay period reaches that date. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_12` | decimal | measure | public_aggregate | headcount | Headcount at the fiscal month 12 measuring date. Zero can mean no pay period reaches that date. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `total` | decimal | measure | public_aggregate | headcount | Sum of the twelve monthly headcounts. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `average_headcount` | decimal | measure | public_aggregate | headcount | Total divided by twelve, always, including zero months, to match the partner's own summary. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `months_with_headcount` | int | measure | public_aggregate | months | How many of the twelve months held any headcount. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `unreachable_months` | text | dimension | public_aggregate |  | Comma-separated month numbers no pay period reaches (a calendar fact, not a decline). | agg: count, count_distinct; filter: none |

**Relation to the engine's tools**

- `average_headcount`: client_eligibility and client_trend report the credit-driving average from the same run. Those are authoritative; this dataset shows which months and worksites drove it.
- `total`: Never divide by months-with-data: the divisor is twelve by agreement with the partner.

### `run_method_summary`

What only the run knew: the annual average, how many employees each method found eligible, matrix size and contested months.

**Grain:** One row per client per tax year per method.

- Client key: `client_id` (applied for you, always the first predicate).
- Tax year: `tax_year`.
- Method: `method` (`min_max` | `pay_period`; returned with every row).

| Column | Type | Role | Sensitivity | Unit | Meaning | Allowed |
| --- | --- | --- | --- | --- | --- | --- |
| `tax_year` | int | dimension | public_aggregate |  | The tax year. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `method` | text | dimension | public_aggregate |  | Which statutory reading produced the row: min_max or pay_period. Never mixed silently. | agg: count, count_distinct; filter: eq, in |
| `run_id` | text | identifier | public_aggregate |  | The calculation run that wrote the row. The live run is selected for you. | agg: count, count_distinct; filter: none |
| `program_code` | text | dimension | public_aggregate |  | The programme the run priced, for example a state job-creation credit. | agg: count, count_distinct; filter: eq, in |
| `annual_average` | decimal | measure | public_aggregate | headcount | The method's annual average headcount for the client-year. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `eligible_employees` | int | measure | public_aggregate | employees | Employees the method found eligible. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `employees_evaluated` | int | measure | public_aggregate | employees | Employees with payroll in the window. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `matrix_rows` | int | measure | public_aggregate | rows | Rows in the One/Zero matrix. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `unit_fein_rows` | int | measure | public_aggregate | rows | Worksite-by-entity rows. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `contested_months` | int | measure | public_aggregate | employee-months | Employee-months where one person appeared at two worksites and the tie-breaker decided. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `month_ends` | text | dimension | public_aggregate |  | The twelve measuring dates the run used, as a JSON list. | agg: count, count_distinct; filter: none |
| `appended_at` | datetime | dimension | public_aggregate |  | When the row was written. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |

**Relation to the engine's tools**

- `annual_average, eligible_employees`: client_eligibility is authoritative for these. Quote the tool; use this dataset for the comparison across years or methods.

### `run_manifest`

Which runs exist for the client, under which assumptions and rule pack, and whether they succeeded.

**Grain:** One row per calculation run, superseded runs included.

- Client key: `client_id` (applied for you, always the first predicate).
- Tax year: `tax_year`.
- Dates: `fiscal_year_begin`, `fiscal_year_end`.

| Column | Type | Role | Sensitivity | Unit | Meaning | Allowed |
| --- | --- | --- | --- | --- | --- | --- |
| `run_id` | text | identifier | public_aggregate |  | The run's identifier. | agg: count, count_distinct; filter: eq, in |
| `tax_year` | int | dimension | public_aggregate |  | The year the run was commanded for; a run covers every year the payroll holds. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `program_code` | text | dimension | public_aggregate |  | The programme priced. | agg: count, count_distinct; filter: eq, in |
| `fiscal_year_begin` | date | dimension | public_aggregate |  | First day of the client's fiscal window. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `fiscal_year_end` | date | dimension | public_aggregate |  | Last day of the client's fiscal window. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `step1_assumption_set_id` | text | dimension | public_aggregate |  | The Min-Max methodology set the run used. | agg: count, count_distinct; filter: eq, in |
| `onezero_assumption_set_id` | text | dimension | public_aggregate |  | The One/Zero methodology set the run used. | agg: count, count_distinct; filter: eq, in |
| `rule_pack_version` | text | dimension | public_aggregate |  | The statute pack the run applied. | agg: count, count_distinct; filter: eq, in |
| `code_commit` | text | dimension | public_aggregate |  | The engine's git commit. | agg: count, count_distinct; filter: eq, in |
| `calculation_id` | text | dimension | public_aggregate |  | Deterministic hash of inputs and configuration; identical inputs give an identical hash. | agg: count, count_distinct; filter: eq, in |
| `run_started_at` | datetime | dimension | public_aggregate |  | When the run began. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `run_completed_at` | datetime | dimension | public_aggregate |  | When the run finished. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `run_status` | text | dimension | public_aggregate |  | running, success, failed or superseded. | agg: count, count_distinct; filter: eq, in |
| `superseded_by_run_id` | text | dimension | public_aggregate |  | The run that replaced this one, if any. | agg: count, count_distinct; filter: eq, in |

Never queryable: `triggered_by`.

**Relation to the engine's tools**

- `run_status`: calc_walkthrough explains one run's derivation; this dataset lists the runs.

### `unit_year_master`

The cross-year master per location: headcount, base year, qualification, tier and the annual credit. The portal's location grid reads this table.

**Grain:** One current row per worksite per programme per method per tax year.

- Client key: `client_id` (applied for you, always the first predicate).
- Tax year: `tax_year`.
- Method: `method` (`min_max` | `pay_period`; returned with every row).

| Column | Type | Role | Sensitivity | Unit | Meaning | Allowed |
| --- | --- | --- | --- | --- | --- | --- |
| `worksite_id` | text | dimension | public_aggregate |  | The worksite (unit) the row is for. | agg: count, count_distinct; filter: eq, in |
| `entity_fein` | text | dimension | public_aggregate |  | The legal entity's federal tax id. | agg: count, count_distinct; filter: eq, in |
| `program_code` | text | dimension | public_aggregate |  | The programme priced. | agg: count, count_distinct; filter: eq, in |
| `method` | text | dimension | public_aggregate |  | Which statutory reading produced the row: min_max or pay_period. Never mixed silently. | agg: count, count_distinct; filter: eq, in |
| `tax_year` | int | dimension | public_aggregate |  | The tax year. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `average_headcount` | decimal | measure | public_aggregate | headcount | Average headcount for the worksite-year (the monthly total divided by twelve). | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `is_base_year` | bool | flag | public_aggregate |  | True where this year is the worksite's base year. | agg: count, sum; filter: eq |
| `base_average_headcount` | decimal | measure | public_aggregate | headcount | The frozen baseline headcount the credit is measured against. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `base_year_source` | text | dimension | public_aggregate |  | inferred or override. | agg: count, count_distinct; filter: eq, in |
| `net_new_vs_base` | decimal | measure | public_aggregate | jobs | Average headcount above the frozen base. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `months_reachable` | int | measure | public_aggregate | months | Months whose measuring date a pay period reaches. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `year_complete` | bool | flag | public_aggregate |  | True when the year fills every reachable month. | agg: count, sum; filter: eq |
| `declined` | bool | flag | public_aggregate |  | True when under half the targets were reachable, so the year was declined rather than priced at zero. | agg: count, sum; filter: eq |
| `decline_reason` | text | dimension | public_aggregate |  | Why a year was declined. | agg: count, count_distinct; filter: contains, eq, in |
| `threshold` | decimal | measure | public_aggregate | jobs | The statutory minimum new jobs. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `threshold_source` | text | dimension | public_aggregate |  | designation or rule_pack: which applied. | agg: count, count_distinct; filter: eq, in |
| `qualified` | bool | flag | public_aggregate |  | True when the worksite met the threshold. | agg: count, sum; filter: eq |
| `status` | text | dimension | public_aggregate |  | The reading decided once for the grid. | agg: count, count_distinct; filter: eq, in |
| `tier` | text | dimension | public_aggregate |  | Geographic tier. | agg: count, count_distinct; filter: eq, in |
| `designation` | text | dimension | public_aggregate |  | Negotiated designation, where one exists. | agg: count, count_distinct; filter: contains, eq, in |
| `tier_source` | text | dimension | public_aggregate |  | prototype or unassigned. | agg: count, count_distinct; filter: eq, in |
| `eligible_jobs` | decimal | measure | public_aggregate | jobs | Net-new jobs above the frozen base; sizes the annual credit. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `new_jobs_created` | decimal | measure | public_aggregate | jobs | Increment above the running high-water mark; sizes a new tranche. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `high_water_mark` | decimal | measure | public_aggregate | headcount | Running maximum average through this year, never below base. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `backfilled` | bool | flag | public_aggregate |  | True for a year that re-qualified after a non-qualifying one. | agg: count, sum; filter: eq |
| `per_job_usd` | decimal | measure | public_aggregate | USD | Dollars per job as applied by the rule pack of that run. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `tranche_years` | int | measure | public_aggregate | years | Benefit window in years. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `annual_credit_usd` | decimal | measure | public_aggregate | USD | Eligible jobs times dollars per job: the credit for the worksite-year. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `base_year_overridden` | bool | flag | public_aggregate |  | True where a person set the base year. | agg: count, sum; filter: eq |
| `high_water_mark_overridden` | bool | flag | public_aggregate |  | True where a person set the high-water mark. | agg: count, sum; filter: eq |
| `run_id` | text | identifier | public_aggregate |  | The calculation run that wrote the row. | agg: count, count_distinct; filter: none |
| `appended_at` | datetime | dimension | public_aggregate |  | When the row was written. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |

**Relation to the engine's tools**

- `annual_credit_usd`: client_eligibility and client_trend report the client-year credit; they are authoritative. Summed over worksites this column equals them for the same method and year.
- `status, qualified`: Decided once in the engine and read back. Do not re-derive them from headcount.

### `unit_credit_installment`

The credit's tranche projection at its atomic grain: each qualifying year opens a window that pays an installment in each later year.

**Grain:** One current row per worksite per method per creation year per tax year.

- Client key: `client_id` (applied for you, always the first predicate).
- Tax year: `tax_year`.
- Method: `method` (`min_max` | `pay_period`; returned with every row).

| Column | Type | Role | Sensitivity | Unit | Meaning | Allowed |
| --- | --- | --- | --- | --- | --- | --- |
| `worksite_id` | text | dimension | public_aggregate |  | The worksite (unit). | agg: count, count_distinct; filter: eq, in |
| `program_code` | text | dimension | public_aggregate |  | The programme priced. | agg: count, count_distinct; filter: eq, in |
| `method` | text | dimension | public_aggregate |  | Which statutory reading produced the row: min_max or pay_period. Never mixed silently. | agg: count, count_distinct; filter: eq, in |
| `creation_year` | int | dimension | public_aggregate |  | The year that opened the window. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `tax_year` | int | dimension | public_aggregate |  | The year the installment falls in. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `tranche_jobs` | decimal | measure | public_aggregate | jobs | Window size at creation. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `jobs_maintained` | decimal | measure | public_aggregate | jobs | Jobs still above base this year. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `per_job_usd` | decimal | measure | public_aggregate | USD | Dollars per job as applied. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `claimable_usd` | decimal | measure | public_aggregate | USD | Jobs maintained times dollars per job. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `projected` | bool | flag | public_aggregate |  | True where no payroll exists yet and the installment assumes the job is maintained: a forecast, not a claim. | agg: count, sum; filter: eq |
| `run_id` | text | identifier | public_aggregate |  | The calculation run that wrote the row. | agg: count, count_distinct; filter: none |
| `appended_at` | datetime | dimension | public_aggregate |  | When the row was written. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |

**Relation to the engine's tools**

- `claimable_usd`: A tax year's claimable figure is the sum over creation years. Rows with projected = true are forecasts and must be labelled so.

### `payroll`

The payroll rows before any engine rule: hours, wages, rate, pay code and location for every pay period.

**Grain:** One row per employee per pay period per pay code, exactly as received.

- Client key: `AccountId` (applied for you, always the first predicate).
- Dates: `pay_period_start`, `pay_period_end`, `pay_date`.
- Join `location` -> `location` on `location_id` = `location.location_id` (many-to-one, left join).
- Join `worksite` -> `location` on `worksite_location_id` = `worksite.location_id` (many-to-one, left join).
- Join `pay_code_info` -> `pay_code` on `pay_code_id` = `pay_code_info.pay_code_id` (many-to-one, left join).

| Column | Type | Role | Sensitivity | Unit | Meaning | Allowed |
| --- | --- | --- | --- | --- | --- | --- |
| `entity_id` | int | dimension | public_aggregate |  | The legal entity the pay belongs to. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `location_id` | int | dimension | public_aggregate |  | The location on the payroll row; always present. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `worksite_location_id` | int | dimension | public_aggregate |  | The worksite, where the source supplies one. Jobs are counted at the worksite. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `pay_frequency_id` | int | dimension | public_aggregate |  | The source's pay-frequency key (lookup not supplied; lineage only). | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `pay_period_start` | date | dimension | public_aggregate |  | First day of the pay period. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `pay_period_end` | date | dimension | public_aggregate |  | Last day of the pay period. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `pay_date` | date | dimension | public_aggregate |  | Date paid. Blank in some rows. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `hours` | decimal | measure | employee_level | hours | Hours paid. Blank is not zero. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `wages` | decimal | measure | employee_level | USD | Wages paid. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `hourly_rate` | decimal | measure | employee_level | USD/hour | Hourly rate, where supplied. | agg: avg, count, count_distinct, max, min, sum; filter: between, eq, gte, in, lte |
| `is_full_time` | bool | flag | public_aggregate |  | Full-time marker from the source, where supplied. | agg: count, sum; filter: eq |
| `is_salaried` | bool | flag | public_aggregate |  | Salaried marker from the source, where supplied. | agg: count, sum; filter: eq |
| `pay_code_id` | int | dimension | public_aggregate |  | Key into the client's pay codes; join pay_code_info for the code and its description. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `pay_year` | int | dimension | public_aggregate |  | Calendar year of the pay date (the period end when there is none). NOT the tax year, which follows the client's fiscal window. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `pay_month` | int | dimension | public_aggregate |  | Calendar month of the pay date as YYYYMM. Not a fiscal month. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |

Never queryable: `employee_id`, `client_employee_id`.

**Relation to the engine's tools**

- `hours, wages`: Raw inputs. The engine applies the fiscal window, pay-code filter and BA rules before it counts, so sums here are not the engine's totals; employee_eligibility holds those.
- `pay_year`: A calendar year, not a tax year. For a tax-year answer use the engine tools or the Gold datasets.

### `location`

The client's locations: name, the client's own location code, status and open and close dates.

**Grain:** One row per client worksite.

- Client key: `AccountId` (applied for you, always the first predicate).
- Dates: `open_date`, `close_date`.

| Column | Type | Role | Sensitivity | Unit | Meaning | Allowed |
| --- | --- | --- | --- | --- | --- | --- |
| `location_id` | int | identifier | public_aggregate |  | The location key payroll rows carry. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `entity_id` | int | dimension | public_aggregate |  | The legal entity operating the location. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `location_name` | text | dimension | public_aggregate |  | The location's name, for example the town; use it to find the location key. | agg: count, count_distinct; filter: contains, eq, in |
| `client_location_id` | text | dimension | public_aggregate |  | The client's own code for the location. | agg: count, count_distinct; filter: eq, in |
| `dba` | text | dimension | public_aggregate |  | Trading name. | agg: count, count_distinct; filter: contains, eq, in |
| `open_date` | date | dimension | public_aggregate |  | When the location opened; a site opened mid-year is not a site with missing months. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `close_date` | date | dimension | public_aggregate |  | When the location closed, if it did. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `location_status_id` | int | dimension | public_aggregate |  | The source's location status key. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `screening_status_id` | int | dimension | public_aggregate |  | The source's screening status key. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |

**Relation to the engine's tools**

- `location_id`: Gold's worksite_id is the payroll's worksite location. Resolve a name here, then filter the Gold dataset on that id.

### `pay_code`

The client's pay codes, with whether each is ACA or FUTA wages and its category.

**Grain:** One row per client pay code.

- Client key: `AccountId` (applied for you, always the first predicate).

| Column | Type | Role | Sensitivity | Unit | Meaning | Allowed |
| --- | --- | --- | --- | --- | --- | --- |
| `pay_code_id` | int | identifier | public_aggregate |  | The pay-code key payroll rows carry. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |
| `pay_code` | text | dimension | public_aggregate |  | The pay code as the client writes it. | agg: count, count_distinct; filter: contains, eq, in |
| `description` | text | dimension | public_aggregate |  | What the pay code means. | agg: count, count_distinct; filter: contains, eq, in |
| `is_aca` | bool | flag | public_aggregate |  | Counts for ACA purposes. | agg: count, sum; filter: eq |
| `is_futa` | bool | flag | public_aggregate |  | Counts as FUTA wages. | agg: count, sum; filter: eq |
| `pay_code_category_id` | int | dimension | public_aggregate |  | Category key; the lookup was not supplied, so whether a code counts toward a state credit is an open question. | agg: count, count_distinct, max, min; filter: between, eq, gte, in, lte |

**Relation to the engine's tools**

- `pay_code`: The engine's pay-code filter (BA-07) is authoritative for what counts; this lists what exists.

## Deliberately not queryable

### Warehouse

| Table | Why it is not queryable |
| --- | --- |
| `tcc_ops.agent_action_audit` | Platform audit or security record. Never exposed to the agent; the audit trail has its own readers. |
| `tcc_ops.agent_finding_resolution` | Operational record written by the platform to run itself; not payroll or credit data. |
| `tcc_ops.artifact` | Operational record written by the platform to run itself; not payroll or credit data. |
| `tcc_ops.artifact_access` | Platform audit or security record. Never exposed to the agent; the audit trail has its own readers. |
| `tcc_ops.assumption_set_version` | Global methodology registry with no client key; the run manifest names the set used. |
| `tcc_ops.channel_audit` | Platform audit or security record. Never exposed to the agent; the audit trail has its own readers. |
| `tcc_ops.channel_confirmation` | Platform audit or security record. Never exposed to the agent; the audit trail has its own readers. |
| `tcc_ops.channel_user` | Platform audit or security record. Never exposed to the agent; the audit trail has its own readers. |
| `tcc_ops.client_config` | Per-client configuration the platform reads; not a question about payroll. |
| `tcc_ops.exception_report_item` | Ingestion quality-control exceptions that name employee rows. |
| `tcc_ops.excluded_record` | Employee-level audit rows with source employee ids; a later dataset behind the user lane if a question needs it. |
| `tcc_ops.manual_override` | Human overrides, with the person who made each; the engine tools report an overridden figure and say so. |
| `tcc_ops.program_claim` | Claims hold seeded, unverified assertions; client_situation and the book tools own that reading. |
| `tcc_ops.program_engagement` | Operational record written by the platform to run itself; not payroll or credit data. |
| `tcc_ops.rule_change_audit` | Platform audit or security record. Never exposed to the agent; the audit trail has its own readers. |
| `tcc_ops.rule_pack_version` | Global statute registry with no client key; the run manifest names the pack used. |
| `tcc_ops.schema_migration` | Schema bookkeeping with no client key. |
| `tcc_ops.source_file_manifest` | Per-file hashes and counts for a snapshot; carries no client key to scope by. |
| `tcc_ops.source_snapshot` | Lineage of the payroll a run consumed; reproducibility metadata, not an analytic dataset. |

### Lakehouse source

| Table | Why it is not queryable |
| --- | --- |
| `Account` | The client record itself, including its name; the client is selected by the platform, never queried. |
| `Address` | Shared lookup with no client key; reachable only through a declared join from Location. |
| `Employment` | Names the employee but carries no account key, so it cannot be scoped to one client. |
| `Entity` | Legal entities with tax ids; no question needs it yet. Add with a decision. |
| `EntityFiscalYearRules` | Fiscal calendars with no client key; the engine resolves the fiscal window. |
| `PayFrequency` | Shared lookup with no client key, inferred rather than supplied. |
| `StateCountyZip` | Shared geography lookup with no client key. |

## Changing the model

1. Add the column or table to the DDL (or the source schema) as usual.
2. `tests/test_semantic_model_drift.py` now fails. Model the column in the right
   `application/data/model_*.py` (mark anything that could identify a person `blocked`), or
   list it under `excluded_columns` / `model_excluded.py` with a reason.
3. Regenerate this page: `python scripts/generate-semantic-model-doc.py`.
