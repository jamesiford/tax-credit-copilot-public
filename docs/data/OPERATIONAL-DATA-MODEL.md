# Tax Credit Copilot — operational data model

**Version** 0.3 · **Date** 2026-09-02 · **Status** Draft for Sam Hameed and the partner's team
**Author** James Ford · **Scope** `tcc_ops` only — the decision and audit store in the Fabric Warehouse

> **v0.3 — split by store.** v0.2 described calculation results (Group B)
> alongside the decision and audit tables. Those are different stores with
> different jobs: calculation output is analytical and high-volume, decision
> state is small and written interactively. **Group B has moved to
> [`GOLD-LAYER-SPEC.md`](GOLD-LAYER-SPEC.md).** This document is now the
> operational store only, and every table carries a build status so it is clear
> what exists.
>
> **Platform v2 — one store.** The document store this model was first written
> against is retired. [ADR-007](../architecture/ADR-007-warehouse-operational-store.md)
> makes the Fabric Warehouse the only operational store: these tables live in
> the `tcc_ops` schema (configurable via `OPS_SCHEMA`), beside `tcc_gold`.
>
> The field-by-field source mapping remains in
> [`SOURCE-SCHEMA-MAPPING.md`](SOURCE-SCHEMA-MAPPING.md). Changes from v0.2 are
> listed in §10.

---

## 0. Build status — read this first

The tables below are a **design**. Most are not built. Five `tcc_ops` tables
exist; application code writes all five.

| Table | Status |
| --- | --- |
| `program_claim` | **Built** — `WarehouseClaimRepository`. Carries `is_base_year` |
| `program_engagement` | **Built** — `WarehouseClaimRepository`. Specified below as `client_program_engagement` |
| `agent_finding_resolution` | **Built** — `WarehouseFindingRepository`. §6.5, new in v0.3, specified below as `finding_resolution` |
| `run_manifest` | **Built** — run-manifest store |
| `source_snapshot` | **Built** — run-manifest store |
| `client_config`, MAF workflow state, decisions, proposals, scenarios | Not built. Specified for the retired document store, never written, dropped |
| `excluded_record`, `manual_override`, `exception_report_item` | Not built |
| `rule_change_audit`, `agent_action_audit` | Not built |
| `assumption_set_version`, `rule_pack_version` | JSON files on disk today |

Every statement against these tables goes through
`infrastructure/persistence/tenant_sql.py`, which binds `client_id` as the first
predicate; the portfolio read is the one explicit, logged `tenant_exempt(reason)`
exception. Close-then-insert writes run in one transaction and retry Fabric
snapshot-isolation write conflicts (error 24556), at most five attempts.

**For Sam:** if you are modelling *what the app produces today*, that is five
`tcc_ops` tables plus the Gold layer. Everything else here is target state.

---

## 1. What this covers, and what it does not

`DATA-REQUIREMENTS.md` describes the **inbound** data the calculation consumes — payroll,
worksites, rule packs, wage floors. That is the partner's side of the boundary and it is largely
settled: nine source tables, of which eight are already in the lakehouse, with the pay-code
lookup to follow.

**[v0.2]** `FlexSchema.txt` now gives us the actual inbound DDL:
`Payroll`, `Employment`, `Location`, `Address`, `StateCountyZip`, `Entity`,
`PayCode`, `Account` and the `vw_Employee` view. It is a properly normalised
schema — correct types, `AccountId` on every table, and `Payroll` physically
partitioned on the account. Three referenced lookups are still outstanding:
**`EntityFiscalYearRules`** (BA-01), **`PayFrequency`** (BA-03) and
**`PayCodeCategory`** (BA-07).

**[v0.3]** Calculation *output* — the employee, unit-month and unit-year grain —
is in [`GOLD-LAYER-SPEC.md`](GOLD-LAYER-SPEC.md). This document covers only what
the app writes to `tcc_ops`: decisions, overrides, audit and claim state.

This document describes the other half. On the 20 August call Shashi framed it precisely:

> "The new data that is required for Flex app and the **operational data that Flex app is
> going to generate**, because we are talking about auditing, observability, the whole
> nine yards that we need to capture. When somebody changes the rule in the Flex app, we
> need to know that. When somebody runs an agent and changes something, we need to
> capture that."

Nothing in this document exists in the partner's estate today. All of it currently lives
inside the application process and is lost when the process restarts.

**The governing constraint:** these numbers land on a filed tax return. Every figure must be
reproducible years later, on demand, against the exact inputs and rules that produced it.
That is what forces most of the design below.

---

## 2. The five things we must persist

| # | Group | Store | Why it cannot be derived later |
| --- | --- | --- | --- |
| **A** | **Run provenance** | `tcc_ops` | Which source snapshot, which rule version, which code build produced a given number |
| **B** | **Calculation results** | **Gold** | The per-employee and per-unit output, frozen at run time |
| **C** | **Exclusions and overrides** | `tcc_ops` | What the engine removed, and what a human put back |
| **D** | **Rule and configuration history** | `tcc_ops` | What the rules were on the day the return was filed |
| **E** | **Agent and user activity** | `tcc_ops` | Who or what changed something, and when |
| **F** | **Program coverage and claims** | `tcc_ops` | What a client claimed, and what we identified but they did not |

Groups A, C, D and E are audit substrate. **Group B is the product**, and it is
the one that lives in the lakehouse — see
[`GOLD-LAYER-SPEC.md`](GOLD-LAYER-SPEC.md).

---

## 3. Group A — run provenance

One row per calculation run. Immutable once written.

### 3.1 `run_manifest`

| Column | Type | Notes |
| --- | --- | --- |
| `run_id` | uniqueidentifier | PK |
| `client_id` | **bigint** | **[v0.2]** `Account.AccountId`. Confirmed as the tenant key — `Payroll` is physically partitioned on it (`PayrollRange_PS([Accountid])`), so the partner already treats it as the isolation boundary. |
| `entity_id` | **bigint** | **[v0.2]** `Entity.EntityId`. A run may scope to one legal entity; `Entity.ParentEntityId` gives the hierarchy for CALC-06 entity combination. |
| `program_code` | varchar | `GA_JTC` today; the model is multi-program |
| `tax_year` | int | |
| `fiscal_year_begin` / `fiscal_year_end` | date | Per-client, **not** derivable from payroll. **[v0.2]** Source is `Entity.FiscalYearRulesId` → `EntityFiscalYearRules` — **DDL still outstanding** |
| `source_snapshot_id` | uniqueidentifier | FK to `source_snapshot` |
| `step1_assumption_set_id` | varchar | e.g. `GDS-STEP1-2026-08-25-v8` |
| `step1_assumption_sha256` | char(64) | Content hash, not just the label |
| `onezero_assumption_set_id` | varchar | |
| `onezero_assumption_sha256` | char(64) | |
| `rule_pack_version` | varchar | Statutory pack, versioned separately from assumptions |
| `code_commit` | char(40) | Git SHA of the engine |
| `calculation_id` | char(64) | Deterministic hash of inputs + config; identical inputs must reproduce it |
| `run_started_at` / `run_completed_at` | datetime2 | |
| `run_status` | varchar | `running`, `success`, `failed`, `superseded` |
| `superseded_by_run_id` | uniqueidentifier | Null unless re-run |
| `triggered_by` | varchar | User UPN, schedule name, or agent identity |

`calculation_id` is the reproducibility guarantee. Re-running the same snapshot under the
same assumption set must yield the same hash; if it does not, something changed that we
failed to version.

### 3.2 `source_snapshot` and `source_file_manifest`

Payroll is a moving target — corrections and late files arrive. A run must pin the exact
bytes it consumed.

`source_snapshot`: `snapshot_id`, `client_id`, `extracted_at`, `extraction_query_version`,
`row_count`, `manifest_sha256`.

`source_file_manifest`: one row per file or partition — `snapshot_id`, `file_name`,
`sha256`, `byte_size`, `row_count`, `column_list`, `ordinal`.

**[v0.2] Source-side lineage.** `Payroll` carries `CreateDate`, `ModifyDate`,
`CreatedBy`, `ModifiedBy` and `InloadPayrollId`. A snapshot should record the
`max(ModifyDate)` it observed, so a later correction to a row already consumed is
detectable rather than silent. Add to `source_snapshot`:

| Column | Type | Notes |
| --- | --- | --- |
| `source_max_modify_date` | datetime2 | Highest `Payroll.ModifyDate` in the snapshot |
| `source_inload_batch_ids` | varchar | Distinct `InloadPayrollId` values, for tracing back to the load |

> The partner, 20 August: *"there is a missing pay period in this data, and that does happen to us.
> Sometimes we get a file transmitted that has nothing in it."*

That is precisely why the manifest records row counts and hashes per file rather than only
in aggregate.

---

## 4. Group B — calculation results

**[v0.3] Moved to [`GOLD-LAYER-SPEC.md`](GOLD-LAYER-SPEC.md).**

`employee_period_fact`, `employee_eligibility`, `onezero_matrix`,
`unit_month_summary` and `unit_year_master` are analytical tables at roughly a
quarter of a million rows per client-year. They belong in the Fabric medallion
Gold layer (`tcc_gold`), not in `tcc_ops` — columnar storage, Direct Lake for
BI, and scans sized for the analytical shape.

The split follows [ADR-007](../architecture/ADR-007-warehouse-operational-store.md),
which supersedes ADR-002 §1: the Fabric Warehouse holds both, `tcc_ops` for the
operational and decision store and `tcc_gold` for calculation output, with
payroll in the Fabric medallion.

Group B is the bulk of the value and it is **not persisted anywhere today** —
the engine computes it per request and discards it. Two of its columns changed
on 2 September following the partner's feedback; see the Gold spec §5.

## 5. Group C — exclusions and overrides

This is the group the partner asked for most insistently, and it does not exist anywhere today.

### 5.1 `excluded_record` — soft delete

> *"Maybe you capture the ineligibles and then give the user the ability to review the
> ineligibles and say, well, wait a minute, that one should be eligible. Let's put it back
> over there."*

`run_id`, `employee_id`, `pay_period_start`, `pay_period_end`, `period_days`, `hours`,
`wages`, `exclusion_rule` (e.g. `BA-12_short_pay_period`), `numerator_treatment`
(`retained` | `removed`), `source_refs`, `is_reinstated`, `reinstated_by`,
`reinstated_at`, `reinstatement_note`.

Current volumetrics from the v7 run, to size it: **1,705 excluded rows** carrying
**7,726.49 hours** and **$1,859,776.29**, touching **998 employees**, of whom **156** are
left with no valid pay period at all. Distribution by period length: 1 day 951, 2 days 549,
3 days 82, 4 days 57, 5 days 53, 6 days 13.

`numerator_treatment` is not decoration. Under v7 the hours and wages of an excluded period
still count toward the numerator; only the denominator loses it. Anyone reading this table
later needs to know that without reading the code.

### 5.2 `manual_override`

> *"We should have that manual adjustment function where we can shove them from one side to
> the other."*

`override_id`, `run_id`, `scope` (`employee` | `record` | `unit`), `target_key`,
`field_changed`, `value_before`, `value_after`, `reason_code`, `justification_text`,
`created_by`, `created_at`, `approved_by`, `approved_at`.

Overrides must be **additive**, never destructive. The engine output stays as computed; the
override is a separate layer applied on top, so the machine result and the human result are
both always visible. For a filed return you need to show both.

### 5.3 `exception_report_item`

> *"We should have some sort of an exception report or some sort of an analytical report
> that says, yes, this client had this weird thing going on or that weird thing going on."*

`run_id`, `severity`, `rule_code`, `entity_type`, `entity_key`, `message`,
`disposition` (`open` | `accepted` | `corrected`), `dispositioned_by`, `dispositioned_at`.

Seed the catalogue with what the engine already detects: missing pay periods in a cadence,
denominators above 52/53 weeks, Pay Period weeks exceeding Min-Max weeks, test-of-twos
overlaps, abnormal period lengths (the 13- and 15-day cases the partner flagged but we chose not to
exclude automatically), and unmapped pay codes.

---

## 6. Groups D and E — rule history and activity

### 6.1 `assumption_set_version` and `rule_pack_version`

`assumption_set_id`, `schema_version`, `status`, `supersedes`, `content_json`, `sha256`,
`authored_by`, `approved_by`, `approved_at`, `effective_from`, `effective_to`.

Immutable. We already run this discipline in the repo — v1 through v7, each retained and
replayable — and it needs to survive the move into the partner's estate rather than being
flattened to "current rules".

### 6.2 `rule_change_audit`

Shashi's requirement verbatim: *"When somebody changes the rule in the Flex app, we need to
know that."*

`change_id`, `assumption_set_id_before`, `assumption_set_id_after`, `assumption_code`
(e.g. `BA-12`), `field_path`, `value_before`, `value_after`, `rationale`,
`source_citation`, `changed_by`, `changed_at`, `runs_invalidated` (JSON array).

`source_citation` is the field that would have carried *"the partner, 2026-08-20 call"*
for the change we made today. Without it, in eighteen months nobody knows why the numerator
rule flipped.

### 6.3 `agent_action_audit`

*"When somebody runs an agent and changes something, we need to capture that."*

`action_id`, `run_id`, `agent_name`, `agent_version`, `model_deployment`, `prompt_hash`,
`tool_calls` (JSON), `input_summary`, `output_summary`, `user_upn`, `occurred_at`,
`is_deterministic_path`.

`is_deterministic_path` matters for defensibility. Our architecture holds that agents narrate
and tools calculate — this column is the evidence that no number on a return came from a
model. It should be `true` for every row touching a figure.

### 6.4 `client_config`
`client_id`, `fiscal_year_begin_rule`, `fiscal_year_end_rule`, `is_staffing_client`,
`programs_enrolled`, `effective_from`, `effective_to`.

> **[v0.2] This table may already exist on the partner's side.** `Entity` carries
> `FiscalYearRulesId` → `EntityFiscalYearRules`, which is presumably the "this is
> the client, this is the fiscal year" table the partner described. **We need that DDL
> (Q4).** If it expresses rules like "the Saturday nearest 31 July", `client_config`
> should reference it rather than duplicate it — a second copy of a fiscal-year
> rule is a second thing to get out of step.
>
> Note the grain difference: `FiscalYearRulesId` hangs off **`Entity`**, not
> `Account`. A client with several legal entities could in principle have
> different fiscal years per entity, which the reference dataset's single 53-week
> window would not have revealed. Worth confirming (Q4).
>
> Other fields now have concrete sources: `is_staffing_client` likely maps to
> `Account.IndustryTypeId` or `AccountTypeId`, and `Account.Status` /
> `AccountStatusId` carry engagement state.

Fiscal year is per-client and cannot be inferred. The partner:

> *"We'll have to build you a table with 'this is the client, this is the fiscal year'...
> because we can't just run it across every client and say, oh, they're all calendar year."*

Public filers come from the 10-K; many private flow-throughs are calendar year; some are
rule-based, such as "the Saturday nearest 31 July". Today the partner's team hand-edits the dates at the
top of a query, which is exactly the fragility this table removes.

`is_staffing_client` drives a second data path — staffing payroll carries a branch ID that
does not indicate where the employee actually worked, so those clients supply a separate
worksite file. Worth noting the partner's commercial view: *"staffing is the least of our concerns...
they're not eligible for many credits. Ironically, they are eligible for Georgia."*

### 6.5 [v0.3] `finding_resolution` — **built, and previously undocumented**

A human answer to something an agent found. This table was missing from v0.2
entirely, yet the application writes it on every resolution. Table
`tcc_ops.agent_finding_resolution`, no expiry.

| Column | Type | Notes |
| --- | --- | --- |
| `finding_id` | varchar | What was found |
| `client_id` | bigint | Tenant key; bound first on every statement |
| `tax_year` | int | |
| `resolution` | varchar | The disposition: `accept`, `assign`, `drop` or `flag` |
| `detail` | varchar | |
| `note` | varchar | Free text |
| `decided_by` | varchar | |
| `decided_at` | datetime2 | The decision instant; superseded rows coexist with the live one |
| `superseded_at` | datetime2 | Null on the live row |

**Append-only.** A resolution that changes a filed figure has to survive a
container recycle, which is what the SQLite adapter could not promise inside a
container. Reopening writes a new row and stamps `superseded_at` on the prior
one rather than mutating it.

Query note: `live()` filters on `superseded_at IS NULL`. Closing the prior row
and inserting the new one happen in one transaction, so there is at most one
live resolution per `(client_id, finding_id)`.

This overlaps conceptually with `manual_override` (§5.2) and
`exception_report_item` (§5.3), neither of which is built. Worth deciding
whether those are distinct tables or whether `finding_resolution` already is the
general shape.

---

## 6A. [v0.2] Group F — program coverage and claim outcomes

### 6A.1 Why this is ours, not the partner's

The application needs to know, for every client × program × tax year, **what is
being claimed** — otherwise the coverage view can only ever say "we computed
$X is available" and never "…and nothing is being claimed against it."

That fact is **not in the source schema, and it should not be.** `FlexSchema.txt`
describes payroll: who worked, where, for how much. What a client *claims* is a
commercial and filing outcome, and it arrives from two directions:

**Generated by us.** We calculate, identify an opportunity, propose it, someone
approves, it is filed, the state certifies it. Every step is a decision this
product produces.

**Asserted at onboarding.** A new client arrives already claiming Georgia JTC
through a prior provider or in-house. Nothing computed it; somebody told us. It
still has to be recorded, or their coverage looks empty and we propose something
they already have.

Both land in the operational store ([ADR-007](../architecture/ADR-007-warehouse-operational-store.md)),
bound to `client_id` like everything else in Group A–E. Neither belongs on the
inbound ask list.

### 6A.2 `program_claim`

The grain is **client × program × tax year**. One row per cell of the coverage
matrix.

| Column | Type | Notes |
| --- | --- | --- |
| `claim_id` | uniqueidentifier | PK |
| `client_id` | bigint | `Account.AccountId` |
| `entity_id` | bigint | Nullable — some programs are claimed per legal entity |
| `program_code` | varchar(20) | `GA_JTC`, `FED_WOTC`, … matches the rule pack |
| `tax_year` | int | |
| `status` | varchar(20) | see lifecycle below |
| `provenance` | varchar(20) | **how we know** — see below. Drives how confidently it renders. |
| `identified_usd` | money | What the engine computed as available |
| `claimed_usd` | money | What was actually claimed |
| `certified_usd` | money | What the authority approved |
| `identified_run_id` | uniqueidentifier | FK `run_manifest` — which run produced `identified_usd` |
| `assumption_set_id` | varchar(40) | Rules in force when identified |
| `rule_pack_version` | varchar(40) | |
| `filed_on` | date | Null until filed |
| `filing_reference` | nvarchar(100) | Form / confirmation number |
| `decided_by` | nvarchar(200) | User UPN, or the agent identity that proposed it |
| `decided_at` | datetime2 | |
| `decline_reason` | nvarchar(400) | **Required when status is `declined`** — see below |
| `effective_from` / `effective_to` | datetime2 | Status history; never update in place |

### 6A.3 Lifecycle

```
not_assessed  ──▶ assessed ──▶ proposed ──┬─▶ claimed ──▶ certified
                                          │                   │
                                          └─▶ declined        └─▶ amended
```

| Status | Meaning |
| --- | --- |
| `not_assessed` | Program applies to this client's footprint; we have not run it |
| `assessed` | Calculated. `identified_usd` populated, nothing decided |
| `proposed` | Recommended to the client |
| `declined` | Client chose not to claim. **`decline_reason` is mandatory** |
| `claimed` | Filed |
| `certified` | Approved by the authority |
| `amended` | Restated after filing |

`declined` deserves the mandatory reason. A client saying *"we are not claiming
WOTC, we take the R&D credit instead"* is durable knowledge — without it, every
subsequent run re-proposes the same thing and the consultant looks like they are
not listening.

### 6A.4 Provenance drives confidence

This is the column that stops the coverage matrix lying.

| Provenance | Meaning | Render as |
| --- | --- | --- |
| `computed` | Our engine identified it | Full confidence, drillable to the run |
| `filed_by_us` | We prepared and filed it | Full confidence, evidence pack attached |
| `client_asserted` | The client told us at onboarding | **Unverified** — visibly distinct |
| `inherited` | Carried in from a prior provider's records | **Unverified** |
| `authority_confirmed` | Confirmed by the state or IRS | Highest |

A client's unverified assertion and a certified filing must not look alike on
the same grid. It is the same two-tier principle the ranked candidate list needs
between computed and estimated figures.

### 6A.5 `client_program_engagement` — commercial scope

Separate and smaller: **which programs are we engaged to handle at all?**

`client_id`, `program_code`, `scope` (`in_scope` | `out_of_scope` |
`prospective`), `effective_from`, `effective_to`.

Without it the coverage matrix cannot distinguish *"unclaimed — an opportunity"*
from *"unclaimed — not our mandate"*. Both render as a gap, and one of them is
noise that erodes trust in the other.

### 6A.6 The cell is a variance, not a status

Claimed-versus-unclaimed is too thin. The retroactive audit — a client asking
*"could we have claimed more?"* — turns every cell into a **comparison** between
what was claimed and what we compute they were entitled to.

| Claimed | Computed | Outcome | Commercial meaning |
| --- | --- | --- | --- |
| $0 | $0 | Correctly not claimed | Nothing to do |
| $0 | $Y | **Unclaimed** | New opportunity |
| $X | ≈ $X | Confirmed | Reassurance; the audit still had value |
| $X | $Y > X | **Under-claimed** | **Recoverable — this is the retroactive product** |
| $X | $Y < X | **Over-claimed** | **Exposure** |

Two of these deserve comment.

**Under-claimed is the product.** *"You left $340,000 on the table in 2021"* is
the entire proposition of a retroactive audit, and it only exists because we
recalculate history rather than only forecasting forward.

**Over-claimed must surface.** If an audit finds a client claimed more than they
were entitled to, that is an exposure we have now discovered — and we cannot
un-know it. The interface must not present only the upside. A product that
surfaces recoverable dollars while quietly suppressing over-claims would be
indefensible the first time an authority found one.

`variance_usd` (`identified_usd − claimed_usd`) and its sign are therefore the
primary reading of a cell, not `status`.

### 6A.7 Six years, not one — the grain is a cube

The retroactive window makes this **client × program × tax year**.

| Scope | Rendering |
| --- | --- |
| Portfolio | client × program, years rolled up — total recoverable across the window |
| Account | **program × year** — this grid *is* the audit deliverable |

The account-scope grid is the artifact a consultant puts in front of a client:
six years across their applicable programs, what was claimed, what was owed, and
the variance.

Three consequences:

1. **Each year must be calculated under its own statute.**
   See [ADR-005](../architecture/ADR-005-year-versioned-rules.md). Applying 2026
   rules to 2021 payroll is not an approximation, it is a wrong answer.
2. **`program_claim` already carries `tax_year`**, so the grain is right — but
   `identified_run_id`, `assumption_set_id` and `rule_pack_version` become
   essential rather than nice to have. A six-year audit is six runs under six
   rulesets, and each figure must be traceable to its own.
3. **Six years of payroll per client**, not one. The volumetrics in §7 assumed
   five years, so the sizing holds — but the *source* conversation changes:
   the partner must supply the full window, and the current reference dataset is a
   single year.

### 6A.8 What this unlocks

> **Built on 26 Aug 2026** (`a0e6161`, `2da5793`). `backend/domain/claims.py` holds
> the entity and the `ClaimRepository` port; `infrastructure/persistence/`
> the SQLite adapter; `api/claims.py` the routes. `POST /api/claims/assess` runs
> the engine and records `identified_usd` per programme-year, and the B4 Position
> view renders the result.

- The coverage matrix reads real status per cell rather than "unknown"
- `identified_usd − claimed_usd` is the opportunity, computed not estimated
- `claimed_usd > certified_usd` is an **audit risk signal** worth surfacing
- Declines are remembered, so proposals stop repeating
- A prospect converting keeps its estimate as history (`inherited`) while the
  recalculated figure lands as `computed` — the variance between them is a
  credibility moment, not a discrepancy to hide
- **Six years of variance per client × program becomes the retroactive audit
  deliverable** — the single largest commercial use case, and one that cannot be
  expressed at all without this table

### 6A.9 Group placement

Groups A–E cover provenance, results, exclusions, rules and activity. This is
none of them: it is the **commercial outcome** of the calculation rather than the
calculation itself. Proposed as **Group F — coverage and outcomes**, sitting
beside `client_config`.

Open for Sam: whether `program_claim` belongs in the operational store (our
position, per ADR-002) or in the partner's canonical model, given it is arguably a
client-relationship fact rather than app state. Our view is that it is generated
by this product and should live where the product's decisions live — but it is a
reasonable thing to disagree about.

---

**Retention.** Georgia carries a ten-year credit carry-forward, so run provenance, results,
overrides and rule history should be treated as ten-year records at minimum. Confirm against
the partner's statutory retention policy before sizing.

**Volumetrics**, from the current reference dataset — one client, one year:

| Table | Rows | Note |
| --- | --- | --- |
| `employee_period_fact` | ~201,000 | collapsed from 384,418 source rows |
| `employee_eligibility` | 20,472 | 10,236 employees × 2 methods |
| `onezero_matrix` | ~20,000 | both methods |
| `unit_month_summary` | ~200 | 101 units × 2 methods |
| `excluded_record` | 1,705 | |
| `unit_year_master` | ~101 | per year, appended |

Roughly a quarter of a million rows per client-year. At five years and a meaningful client
portfolio this is small by Fabric standards — but `employee_period_fact` is the one that
scales linearly with headcount and should be partitioned by `client_id` and `tax_year`.

**Placement** is Sam's call and was left open on the call. The constraint the partner's team raised:

> *"In the Fabric world... there is a limitation on the SQL endpoint to write to the
> lakehouse."*

These tables are **write-heavy and transactional** — overrides, dispositions and audit rows
are written interactively by users, not batch-loaded. That argues for a Fabric SQL database
or warehouse for Groups C, D and E, with the bulk result tables (Group B) in the lakehouse
alongside the source data. Worth Sam confirming, since Shashi noted this will become the
pattern for future app modernisations.

---


## 7. Retention, volumetrics and placement

**Retention.** Georgia carries a ten-year credit carry-forward, so run provenance, results,
overrides and rule history should be treated as ten-year records at minimum. Confirm against
the partner's statutory retention policy before sizing.

**Volumetrics** — `tcc_ops` tables only. Group B volumetrics moved to the
[Gold spec](GOLD-LAYER-SPEC.md) §7.

| Table | Rows per client-year | Note |
| --- | --- | --- |
| `program_claim` | ~6 | one per program-year, append-only on change |
| `client_program_engagement` | ~2 | commercial scope |
| `finding_resolution` | tens | human dispositions |
| `excluded_record` | 1,705 | if built |
| `run_manifest` | one per run | |
| `agent_action_audit` | tens per run | |

These are small. The operational tables are shaped by interactive, keyed
writes, not by volume — which is the opposite of the Gold layer, and is why they
are a different schema with a different job.

**[v0.3] Placement is decided.**
[ADR-007](../architecture/ADR-007-warehouse-operational-store.md) is the record,
superseding ADR-002 §1: **the Fabric Warehouse is the only operational store**
(`tcc_ops`), beside `tcc_gold` for calculation output, with payroll in the
Fabric medallion. Everything in this document is `tcc_ops`.

The v0.2 text here proposed Fabric SQL or a warehouse for Groups C, D and E,
citing the partner's constraint:

> *"In the Fabric world... there is a limitation on the SQL endpoint to write to the
> lakehouse."*

That constraint is real and it is exactly why these tables are **not** in the
lakehouse — they are written interactively by users, not batch-loaded. v0.3
resolved it by putting them in a separate document store; Platform v2 retired
that store and puts them in the Fabric Warehouse, whose T-SQL endpoint does
accept transactional writes. The v0.2 proposal is, in effect, what shipped.

**The run-manifest question is closed.** `run_manifest` and `source_snapshot`
are `tcc_ops` tables, so the `run_id` every Gold row carries joins to its
manifest inside one Warehouse rather than across stores. See Gold spec §6.

---

## 8. Open questions

1. **Placement** — **Closed**, including run manifests and source snapshots;
   see §7. The decision is
   [ADR-007](../architecture/ADR-007-warehouse-operational-store.md): the Fabric
   Warehouse (`tcc_ops`) for this operational store, `tcc_gold` and the Fabric
   medallion for payroll and calculation output.
2. **Retention** — is ten years right, and does anything need to be immutable-by-storage
   rather than immutable-by-convention?
3. **Identity** — which identity writes the audit rows: the app's managed identity, or the
   end user's? For a filed return an attributable human is preferable where one exists.
4. **Where does `unit_year_master` live** — is it a Flex app table, or does it belong in the
   canonical model the partner's team already maintains, given it is a cross-year business asset rather
   than app state?
5. **Restatement policy** — when a re-run changes a prior year that has already been filed,
   what is the approval path?
6. **PII boundary** — the current prototype uses tokenised employee IDs. Production will
   carry real ones, which changes the classification of `employee_period_fact` and
   `employee_eligibility`.
   **[v0.2]** Less severe than feared: `Payroll` holds no PII, only surrogate
   keys, and `Employee` is column-encrypted. Silver should tokenise from the
   encrypted table and never join through `vw_Employee`.

### [v0.2] New questions raised by `FlexSchema.txt`

7. **`PaycheckDate` is nullable.** BA-02 trims the fiscal window on paycheck date.
   What does a null mean, how often does it occur, and what should the trim do?
   The engine would currently drop those rows silently.
8. **`Hours` and `Wages` are nullable with `DEFAULT 0`.** BA-05 deliberately keeps
   zero-hour rows. Does NULL mean 0, or "not reported"? They must not be treated
   alike.
9. **`LocationId` versus `WorksiteLocationId`** on `Payroll`. GA JTC counts jobs at
   a worksite, and `WorksiteLocationId` is nullable. Which is authoritative for the
   One/Zero unit?
10. **`EntityFiscalYearRules` DDL** — BA-01. Note it hangs off `Entity`, not
    `Account`, so fiscal year may vary by legal entity within one client.
11. **`PayCodeCategoryId`** — does it carry state-JTC inclusion? `PayCode` has
    `IsACA` and `isFUTA` but no state-credit flag. This is the lookup already
    owed, now with a concrete column to confirm against.
12. **`Employment` grain** — one row per employee, or one per employment spell?
    `CurrentLocationId` alongside `HireLocationId` suggests in-place update, which
    would mean worksite transfer history is lost and must come from `Payroll`.

---

## 9. What we owe each other

| Item | Owner | Status |
| --- | --- | --- |
| DDL for the source tables | The partner | **[v0.2] Largely delivered** — `FlexSchema.txt`, 20 Aug. Outstanding: `EntityFiscalYearRules`, `PayFrequency`, `PayCodeCategory` |
| Pay-code inclusion for state JTC | The partner | Open — does `PayCode.PayCodeCategoryId` carry it? |
| Answers to §8 items 7–12 | The partner's team | **[v0.2] New** — nullable `PaycheckDate`, NULL-versus-zero hours, `LocationId` vs `WorksiteLocationId`, `Employment` grain |
| Placement proposal across Fabric options | Sam | Open — our position is in [ADR-002](../architecture/ADR-002-production-persistence.md) |
| This model refined to DDL once placement is agreed | James | Open |
| Confirmation of retention and restatement policy | Page / the partner | Open |

---

## 10. [v0.2] What changed, and why

`FlexSchema.txt` (the partner's `intranet`, scripted 20 Aug) arrived on 25 August. Full
field-by-field mapping in [`SOURCE-SCHEMA-MAPPING.md`](SOURCE-SCHEMA-MAPPING.md).

| Change | Detail |
| --- | --- |
| `client_id` typed and confirmed | `bigint`, = `Account.AccountId`. `Payroll` is physically partitioned on it, so the partner already treats it as the isolation boundary. |
| `entity_id` added to `run_manifest` | `Entity.EntityId`, with `ParentEntityId` giving the hierarchy CALC-06 needs |
| `source_snapshot` gains lineage | `source_max_modify_date` and `source_inload_batch_ids`, so a late correction to an already-consumed row is detectable |
| `client_config` may be redundant | `Entity.FiscalYearRulesId` → `EntityFiscalYearRules` is probably the partner's fiscal-year table. Reference it; do not duplicate it. |
| PII risk downgraded | `Payroll` carries only surrogate keys; `Employee` is column-encrypted |
| County and industry now reachable | `StateCountyZip.CountyName` and `Account.IndustryTypeId` — two of the four inputs missing from **credit value**. Dollar certification becomes plumbing, not a data gap. |
| Six new questions | §8 items 7–12 |

**One correction to the record.** BA-03's stated rationale — *"the frequency codes
do not behave as documented"* — was not quite right. `PayFrequency` in the partner's CSV
is `PayFrequencyId`, a **surrogate foreign key** into a `dbo.PayFrequency` lookup
we were never given. We were guessing at the meaning of a key, not observing codes
misbehave.

The v7 rule does not change: BA-03 measures each period's actual span and treats
frequency as lineage only, which is correct regardless of what the lookup says,
and the partner confirmed it against their own output. But the reasoning in
`CALCULATION-RULES-V7.md` should be corrected, and `dbo.PayFrequency` requested to
close the loop.

---

## 11. [v0.3] What changed on 2 September

| Change | Detail |
| --- | --- |
| **Group B moved out** | `employee_period_fact`, `employee_eligibility`, `onezero_matrix`, `unit_month_summary`, `unit_year_master` are now in [`GOLD-LAYER-SPEC.md`](GOLD-LAYER-SPEC.md). They are analytical and high-volume; this document is the operational store only. |
| **Build status added** | §0. At v0.3 the retired document store provisioned ten stores and code wrote three; under Platform v2 five `tcc_ops` tables exist and all are written. The rest of this document is target state, and says so. |
| **`finding_resolution` documented** | §6.5. Built and in production use, absent from v0.2 entirely — one of only three operational stores the app wrote at the time. |
| **§7 placement corrected** | The v0.2 proposal of Fabric SQL or a warehouse for Groups C/D/E is superseded by ADR-002, itself superseded in part by ADR-007. Run manifests and source snapshots are now `tcc_ops` tables too. |
| **§2 gains a store column** | Each group now names its store, and Group F is listed rather than implied. |

Nothing in the calculation changed here. The 2 September engine change — year
completeness measured against reachable months, which moved the reference
portfolio claim from 229,285 to 607,110 — is recorded in the
[Gold spec §5](GOLD-LAYER-SPEC.md) because it affects output columns, not
operational state. Certified figures are unmoved.

---

## Document control

Derived from the Workforce Consulting Prototype Session and the partner's Flex payroll data
discussion, both 2026-08-20. Companion to `DATA-REQUIREMENTS.md` (inbound data),
[`GOLD-LAYER-SPEC.md`](GOLD-LAYER-SPEC.md) (calculation output) and
`SOURCE-SCHEMA-MAPPING.md` (Bronze/Silver).

Build status in §0 verified against `infra/main.bicep`,
`backend/application/wiring.py` and `backend/infrastructure/persistence/` at
commit `d1beefe`.

