# Source-to-target mapping — the partner's FlexSchema → Tax Credit Copilot

**Date** 2026-08-25 · **Source** `FlexSchema.txt` (the partner's `intranet` database,
scripted 20 Aug 2026) · **Status** Mapping proposed; six items need the partner's
confirmation

## 1. The headline

**The partner's production schema does not share the defects of the demo lakehouse.**
It is a properly normalised OLTP schema with correct types, a tenant key on every
table, and referential integrity. Most of what the
[lakehouse audit](LAKEHOUSE-SCHEMA-AUDIT.md) flagged was an artefact of a
flattened demo export, not of the partner's data estate.

| Audit finding | Demo lakehouse | Partner FlexSchema |
| --- | --- | --- |
| PII in the calculation source | SSN, name, DOB, address in the payroll table | **Resolved.** `Payroll` holds only foreign keys. Employee PII is column-encrypted at rest. |
| Currency as formatted strings | `'$2,061.19 '` | **Resolved.** `decimal(18,2)` |
| Dates as ambiguous strings | `'1/19/2024'` | **Resolved.** `[date]` |
| One table doing three jobs | 39 columns, everything repeated per row | **Resolved.** `Payroll` / `Employment` / `Location` / `Address` / `Entity` / `Account` |
| No tenant column | absent | **Resolved.** `AccountId` throughout — and `Payroll` is **physically partitioned** on it |
| Missing hire/term dates | absent | **Resolved.** `Employment.HireDate`, `.TerminationDate` |
| Missing county | absent | **Resolved.** `StateCountyZip.CountyName` |
| Missing per-client fiscal year | absent | **Present as an FK** — `Entity.FiscalYearRulesId` → `EntityFiscalYearRules` *(DDL not yet supplied)* |
| Postal code type | `integer` — corrupts leading zeros | **Resolved.** `ZipCodeOriginal nvarchar(50)`, `ZIPCode varchar(10)` |
| Thin pay-code reference | code + description only | **Partly.** `IsACA`, `isFUTA`, `PayCodeCategoryId` — but no state-JTC inclusion flag |

`Payroll` is clustered and partitioned on `PayrollRange_PS([Accountid])`. The partner
already treats the account as the physical partition boundary, which independently
validates the `/tenantId` partition-key decision in
[ADR-002](../architecture/ADR-002-production-persistence.md).

## 2. What the partner's export actually was

The partner's four CSVs are a flattened projection of this schema. The columns map
almost one to one:

| `One.csv` … `Four.csv` | FlexSchema origin |
| --- | --- |
| `TCCEmployeeId` | `Payroll.EmployeeId` |
| `Tax Year` | derived from `Payroll.PaycheckDate` |
| `JobTitle` | `Employment.JobTitle` |
| `TCCUnitId` | `Payroll.WorksiteLocationId` *(or `LocationId` — see Q3)* |
| `PayPeriodStart` | `Payroll.PayPeriodStart` |
| `PayPeriodEnd` | `Payroll.PayPeriodEnd` |
| `PaycheckDate` | `Payroll.PaycheckDate` |
| `PayFrequency` | **`Payroll.PayFrequencyId`** — a surrogate FK, not a label |
| `FEIN` | `Entity.FederalTaxId` |
| `Hours` | `Payroll.Hours` |
| `Wages` | `Payroll.Wages` |

### This re-explains BA-03

We spent real effort on the pay-frequency question and concluded *"the codes do
not behave as documented."* The truer statement is that **we never had the
documentation** — `PayFrequency` in the CSV is `PayFrequencyId`, a foreign key
into a `dbo.PayFrequency` lookup table we were never given.

Measured against actual period spans in the reference dataset:

| `PayFrequencyId` | Rows | Dominant span |
| --- | --- | --- |
| `1` | 374,535 | 7 days (372,285 of them) |
| `2` | 7,153 | 15 days, then 14 |
| `4` | 2,745 | 16 days — every single one |

Reading `4` as "every four weeks" was a guess at a surrogate key's meaning, and
it produced 447 eligible against the partner's 659.

**The v7 answer does not change.** BA-03 measures each period's actual span and
treats frequency as lineage only, which is right regardless of what the lookup
says — and the partner confirmed it against their own output. But requesting
`dbo.PayFrequency` closes the loop honestly, and the rule's stated rationale
should be corrected from "the codes are wrong" to "the codes are surrogate keys
whose lookup we lacked; actual span is authoritative in any case."

## 3. Mapping to the Silver Record Layout

The engine consumes the Silver Record Layout. The Silver transformation is this
projection:

| BCS field | Source | Transform |
| --- | --- | --- |
| `client_id` **(new)** | `Payroll.Accountid` | Direct. The tenant key ADR-002 needs. |
| `Tax_Year` | `Payroll.PaycheckDate` | Fiscal year per `EntityFiscalYearRules` (BA-01), **not** calendar year |
| `Employee_ID` | `Payroll.EmployeeId` | Tokenise at Bronze → Silver. Never `ClientEmployeeID`, which may be a natural key. |
| `Worksite_ID` | `Payroll.WorksiteLocationId` | Fall back to `LocationId` when null — **confirm (Q3)** |
| `Job_Title` | `Employment.JobTitle` | Join on `EmployeeId`, effective-dated by `HireDate` / `TerminationDate` |
| `Entity_FEIN` | `Entity.FederalTaxId` | Via `Payroll.EntityId` |
| `Pay_Period_Start` | `Payroll.PayPeriodStart` | Direct, already `date` |
| `Pay_Period_End` | `Payroll.PayPeriodEnd` | Direct, already `date` |
| `Pay_Date` | `Payroll.PaycheckDate` | Direct — **but nullable, see Q1** |
| `Pay_Frequency` | `Payroll.PayFrequencyId` → `PayFrequency` | Resolve to a label. **Lineage only** (BA-03). |
| `Pay_Code` | `Payroll.PayCodeId` → `PayCode.PayCode` | For BA-07 inclusion |
| `Hours_Worked` | `Payroll.Hours` | `decimal(18,2)`. Distinguish NULL from 0 — see Q2 |
| `Gross_Wages` | `Payroll.Wages` | `decimal(18,2)`. Same |

### Fields now available that the engine does not yet use

| Available | Would enable |
| --- | --- |
| `Employment.HireDate`, `.TerminationDate` | Tighter Min-Max spans; distinguishing "left the company" from "gap in payroll" |
| `Employment.CurrentLocationId`, `.HireLocationId` | Worksite transfer history — what Min-Max segments actually need |
| `Location.OpenDate`, `.CloseDate` | A site that opened mid-year is not a site with missing months |
| `StateCountyZip.CountyName` | **Georgia tier → credit value.** The single biggest gap between certified headcount and uncertified dollars. |
| `Entity.ParentEntityId` | Entity combination (CALC-06) against a real hierarchy rather than a flat FEIN list |
| `Account.IndustryTypeId` | Industry eligibility — a statutory GA JTC condition we cannot currently test |
| `Payroll.IsFullTime`, `.IsSalaried` | Part-time banding (SC pack), and a cross-check on the derived hours test |
| `Payroll.CreateDate` / `ModifyDate` / `CreatedBy` / `ModifiedBy` | Source-side audit lineage into our run manifest |

`CountyName` and `IndustryTypeId` are worth calling out: they are two of the four
inputs missing from the credit-value calculation. Their presence here means
dollar certification is a data-plumbing problem, not a data-availability one.

## 4. What is still missing

### Tables referenced by foreign keys but not supplied

`EntityFiscalYearRules` **(BA-01 — highest priority)**, `PayFrequency`
**(BA-03)**, `PayCodeCategory` **(BA-07)**, `Employee` (base table behind
`vw_Employee`), `IndustryType`, `EntityBusinessTypes`, `AccountStatus`,
`AccountTier`, `AccountType`, `LocationStatus`, `ScreeningStatus`,
`ReferralPartner`.

The first three are blocking; the rest are descriptive.

### Questions for the partner

**Q1 — `PaycheckDate` is nullable.** BA-02 trims the fiscal window on paycheck
date. What does a null mean, how often does it occur, and what should the trim do
with those rows? Today the engine would drop them silently.

**Q2 — `Hours` and `Wages` are nullable with `DEFAULT 0`.** BA-05 deliberately
retains zero-hour rows because a zero-hour wage row is a real payroll fact. Does
NULL mean the same as 0 here, or does it mean "not reported"? They should not be
treated alike.

**Q3 — `LocationId` versus `WorksiteLocationId`.** `Payroll` carries both, and
`WorksiteLocationId` is nullable. GA JTC counts jobs at a **worksite**. Which is
authoritative for the One/Zero unit, and what does a null `WorksiteLocationId`
mean — same as `LocationId`, or unknown?

**Q4 — `EntityFiscalYearRules` DDL.** BA-01 is per-client configuration that is
not derivable from payroll. The reference client runs 2023-07-28 → 2024-08-02, a
53-week calendar. How is that expressed here?

**Q5 — Pay-code inclusion for state JTC.** `PayCode` has `IsACA` and `isFUTA` but
no state-credit flag. Does `PayCodeCategoryId` carry it? This is the lookup
the partner already owes us, now with a concrete column to point at.

**Q6 — `Employment` grain.** Is there one row per employee, or one per employment
spell? `CurrentLocationId` alongside `HireLocationId` suggests the row is updated
in place, which would mean transfer history is lost. If so, worksite history has
to come from the `Payroll` rows themselves.

## 5. Security note

`vw_Employee` decrypts `LastName`, `DateOfBirth` and `Ssn` using
`DECRYPTBYKEY` with a **passphrase written literally into the view definition**,
which is therefore visible to anyone holding the schema script — including in
this file's source, which now sits in OneDrive.

Not our system and not our call, but worth raising with the partner: a hardcoded
key in a DDL script defeats the column encryption it implements. The passphrase
is deliberately not reproduced in this document.

For our purposes the mitigation is simpler: **the calculation never needs
decrypted PII.** `Payroll` carries only surrogate keys, and Silver should join
to the *encrypted* `Employee` table only for tokenisation, never through
`vw_Employee`.

## 6. What this changes

| Area | Change |
| --- | --- |
| [`LAKEHOUSE-SCHEMA-AUDIT.md`](LAKEHOUSE-SCHEMA-AUDIT.md) | Q3 answered. Defects D1–D6 and D8 are demo-fixture artefacts, not estate problems. |
| Bronze → Silver | **Materially smaller than estimated.** Mostly a projection and join, not a repair job. |
| [`OPERATIONAL-DATA-MODEL.md`](OPERATIONAL-DATA-MODEL.md) | `client_config` maps to `Account` + `EntityFiscalYearRules`; `source_snapshot` gains real source lineage columns |
| ADR-002 | `/tenantId` partitioning independently confirmed by the partner's own `PayrollRange_PS([Accountid])` |
| BA-03 rationale | Corrected: surrogate keys without a lookup, not codes that misbehave |
| Credit value | County and industry are **available**, so dollar certification becomes plumbing rather than a data gap |
| F2 multi-tenancy | `Accountid` is the tenant key, and it already partitions the source |
