# Lakehouse schema audit — 25 August 2026

**Scope** the Fabric demo workspace and lakehouse
**Verdict** Suitable as a demo fixture. **Not the target schema.** Do not model
the medallion layers on it.

> ## Resolved the same day — read this first
>
> This audit closed with one question: *does the partner's real payroll extract
> share these defects?* `FlexSchema.txt` arrived hours later and answers it.
>
> **It does not.** The partner's production schema is properly normalised, correctly
> typed, tenant-keyed on every table, and physically partitioned on the account.
> Defects **D1–D6 and D8 below are artefacts of a flattened demo export**, not
> problems in the partner's data estate.
>
> The audit stands as an accurate description of *this lakehouse*, which remains
> the demo fixture. It should no longer be read as a description of the source
> system, and the Bronze → Silver work is materially smaller than §"Actions"
> implies — mostly a projection and join rather than a repair job.
>
> See [`SOURCE-SCHEMA-MAPPING.md`](SOURCE-SCHEMA-MAPPING.md) for the real schema,
> the field-by-field mapping, and the six questions that remain open.

## Why this audit exists

The lakehouse was built as a demo fixture before the calculation was reconciled
with the partner, and before ADR-002 specified a medallion layout. It has since been
treated in places as if it were a schema decision. It is not one, and several of
its choices are actively wrong for a production build.

This document is the gap list, so the Silver layer is designed from the
certified calculation rather than from what happens to be sitting in Bronze.

---

## What is there

### `dbo/employees` — 9,477 rows, 39 columns, 305 distinct employees

One table doing three jobs at once: employee master, payroll transactions, and
worksite reference. Every employee attribute is repeated on every pay-period row.

```
identity      Social_Security_Number, Employee_ID, DOB, First_Name, MI,
              Last_Name, Suffix, Work_Email
address       Home_Address, City, State, Zip, Country
employment    Hire_Date, Rehire_Date, Term_Date, Last_Day_Worked, Term_Reason,
              Months_of_Service, Job_Title, Employment_Type, Status
org / place   Location_ID, FEIN, Worksite_ID, Work_State, SUI_Acct, Branch
payroll txn   Pay_Period_Start, Pay_Period_End, Check_Date, Pay_Frequency,
              Hours, Gross_Wages, Pay_Rate, Rate_Type, Currency, Earning_Code,
              Wage_Type
```

### Reference tables

| Table | Rows | Columns |
| --- | --- | --- |
| `dbo/locations` | 21 | `EmployerLocationID`, `FEIN`, `SEIN`, `EntityName`, `InternalLocationName`, `ExternalLocationName`, `LocationType`, `DateOpened`, `DateClosed`, `Street`, `City`, `State`, `PostalCode`, `CountryCode` |
| `dbo/paycode` | 6 | `Earning_Code`, `Description` |
| `dbo/termcode` | 5 | `Term_Reason`, `Description` |
| `dbo/wotc_paycode` | 6 | `Earning_Code`, `WOTC_Includable` |

`locations` is the best-shaped table here — it is close to a real dimension and
carries `DateOpened` / `DateClosed`, which the calculation needs and does not
currently use.

---

## Defects

### D1 — PII sits in the calculation source *(blocking)*

`Social_Security_Number` holds real-format values (`998-99-0476`), alongside
name, date of birth and home address.

The Silver Record Layout is explicit that the calculation boundary is anonymous, and
`COPILOT-SCOPE.md` states that PII columns are "omitted by design". They are not
omitted here. `tools/fabric_source.py` copies `Employee_ID` through without
tokenisation, so the invariant currently holds only because the demo data happens
to be synthetic.

ADR-002 puts tokenisation at the Bronze → Silver boundary. Silver must not carry
SSN, name, DOB or home address at all.

### D2 — Currency stored as formatted strings *(blocking)*

```
Gross_Wages  '$2,061.19 '     string, leading $, thousands comma, trailing space
Pay_Rate     '$28.31 '        same
```

Every consumer must strip and parse before arithmetic. On a $636 weekly wage
floor, a parse that silently yields 0.0 for a malformed value produces an
ineligible employee and nobody sees it.

Silver stores `decimal(18,2)`. Parsing happens once, at ingestion, where a
failure is a rejected row rather than a wrong number.

### D3 — Dates stored as ambiguous strings *(blocking)*

```
Check_Date        '1/19/2024'   M/D/YYYY, no zero padding
Pay_Period_Start  '1/1/2024'
```

Every date rule the calculation depends on — BA-01's fiscal window, BA-02's
paycheck-date trim, BA-11's exclusive-day span, BA-12's minimum period length —
is date arithmetic. String dates in a locale-ambiguous format are the wrong
substrate. `3/4/2024` is a different day in two locales.

Silver stores `date`.

### D4 — One table doing three jobs *(structural)*

Employee master, payroll transactions and worksite reference are one wide table,
so every employee attribute repeats on every pay row. Three consequences:

- **Update anomalies.** A corrected hire date must be written to every row for
  that employee.
- **No history.** An employee who transfers worksite mid-year has no clean way to
  express "at site A until March, site B after" — which is exactly what the
  Min-Max segment logic needs.
- **Wasted scale.** The partner's reference dataset is 488,968 raw rows for one
  client-year. Repeating 20 attribute columns across all of them is why an F2 will
  not carry the production book.

### D5 — No tenant column *(blocking for F2 multi-tenancy)*

There is no `client_id`, `employer_id` or `tenant_id` anywhere. The table is
implicitly single-client, which mirrors the same gap already identified in
`backend/tools/`.

Every Silver and Gold table needs a tenant key, and it needs to be a partition
column so cross-tenant reads are physically separated, not filtered.

### D6 — Missing fields the certified calculation needs

Present in the reference dataset and in `CALCULATION-RULES-V7.md`, absent here:

| Missing | Needed for |
| --- | --- |
| Per-client fiscal window | BA-01. The partner's reference client runs 2023-07-28 → 2024-08-02, a 53-week calendar. Not derivable from payroll. |
| County | Georgia tier determines credit *value*. `locations` has `PostalCode` but no county. |
| Tax year on the row | BA-02's trim currently infers it from `Check_Date` |
| Assumption set / rule pack version | Replay. A run must record the rules in force. |
| Source lineage | Which file and row a record came from — the reference path tracks this; Bronze does not. |

### D7 — Reference tables are thin

`paycode` has `Earning_Code` and `Description` and nothing else. BA-07 needs to
know, per code, whether it counts toward hours, toward wages, or neither — the
pay-code lookup still owed by the partner's team. `wotc_paycode` proves the pattern is
understood; `paycode` needs the same treatment for the state calculation.

### D8 — Type mismatches

`Zip` is an `integer`, so a leading-zero postal code (New England, Puerto Rico)
is corrupted — `01234` becomes `1234`. Postal codes are identifiers, not numbers.

`Pay_Frequency` is a free-text string. The reference dataset showed these codes do
not behave as documented — every code-4 period runs the 16th to the 31st — which
is why BA-03 makes frequency **lineage only, never a multiplier**. Silver should
carry it as a constrained code with that caveat recorded in the column comment.

---

## What the Silver layer needs instead

Not a schema proposal — that belongs in the operational data model, alongside the
16 tables already specified there. This is the shape the defects imply:

```
silver.employee            one row per employee per client. tokenised.
                           no SSN, name, DOB, home address.

silver.employment_period   employee × worksite × date range.
                           carries transfers as history rather than
                           overwriting. this is what Min-Max segments need.

silver.payroll_line        one row per employee per pay period per earning code.
                           typed: date, decimal(18,2).
                           carries source lineage.

silver.worksite            from locations. + county. DateOpened/DateClosed
                           retained — a site that opened mid-year matters.

silver.pay_code            earning code → counts toward hours / wages / neither.
                           BA-07. blocked on the partner's team.

silver.client              tenant registry incl. the per-client fiscal window.
                           BA-01.
```

Every table partitioned by client. Every date a `date`. Every currency a
`decimal(18,2)`. No PII past Bronze.

---

## What this does not change

**The certified calculation is unaffected.** It runs on the four reference CSVs
through `tools/reference_source.py`, not on this lakehouse.
`test_engine_parity_reference.py` still reproduces 10,236 employees, 539 Min-Max and
656 Pay Period. Nothing in this audit touches that.

**The demo still works.** `DATA_SOURCE=fabric` reads `dbo/employees` and returns
MeridianCore, 333 employees, 10 states. Keep it working while Silver is built
alongside; do not migrate the demo until Silver is proven.

---

## Actions

| | Action | Blocks |
| --- | --- | --- |
| 1 | Treat `dbo/employees` as **Bronze demo fixture**, not a schema. Say so in the workspace description. | — |
| 2 | Design Silver from `CALCULATION-RULES-V7.md`, `OPERATIONAL-DATA-MODEL.md` **and `SOURCE-SCHEMA-MAPPING.md`** — the real source schema is the shape to project from | ADR-002 Stage 4 |
| 3 | Enforce tokenisation at Bronze → Silver, and add a test that fails if a PII column reaches Silver | D1 |
| 4 | Get the pay-code lookup from the partner's team — now with a concrete column to point at: does `PayCode.PayCodeCategoryId` carry state-JTC inclusion? | D7, BA-07 |
| 5 | Get the `EntityFiscalYearRules` DDL | D6, BA-01, F2 |
| 6 | County is available via `StateCountyZip.CountyName` — plumb it through | Credit value, F0.4 |
| 7 | ~~Confirm whether the partner's real extract shares these defects~~ **Answered 25 Aug: it does not.** | — |

Action 7 is closed. `FlexSchema.txt` shows a normalised schema with `date` and
`decimal(18,2)` types, `AccountId` on every table, no PII in `Payroll`, and
hire/termination dates, county and industry all present. See
[`SOURCE-SCHEMA-MAPPING.md`](SOURCE-SCHEMA-MAPPING.md).
