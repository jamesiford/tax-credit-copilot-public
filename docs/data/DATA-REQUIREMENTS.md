# Tax Credit Copilot — data requirements and data dictionary

**Version** 1.0 · **Date** 2026-08-06 · **Status** Draft for internal validation
**Audience** Data SE, SSP, solution architecture — prior to issuing a data request to the partner
**Repository** `tax-credit-copilot`

---

## 1. Purpose

This document defines the complete dataset required to run the Tax Credit Copilot calculation
chain end to end, and separates it into three tiers:

- **Tier 0 — minimum viable.** The smallest field set that lets the One/Zero engine produce an
  Average Headcount. Below this the engine does not run at all.
- **Tier 1 — defensible.** Everything additionally required to turn an Average Headcount into a
  credit dollar figure that survives a state audit.
- **Tier 2 — full product.** Everything required for the remaining product surfaces: multi-state
  expansion, WOTC, forecasting, retroactive scans, and filing.

The core insight for the data conversation: **payroll alone never produces a credit number.**
Payroll produces an Average Headcount. Converting that to a dollar figure requires four further
reference datasets that do not come from the client's payroll system — statutory program rules,
annual state wage/hour floor tables, annual county designation tables, and the client's own base-year
and claim history.

Everything below is grounded in the current codebase: the Silver Record Layout in
`backend/data/generate_pay_periods.py`, the live engine in `backend/tools/onezero.py`, the ten rule
packs in `backend/rules/`, the cited-config schema in `backend/data/rules_ingested/ga_jtc.json`, the
Fabric seed schema in `backend/data/fabric_seed/`, and assumption set `GDS-STEP1-2026-08-05-v5`.

---

## 2. How to read this document

| Symbol | Meaning |
| --- | --- |
| **R** | Required. Calculation cannot run, or produces an undefensible result, without it. |
| **C** | Conditionally required. Required for specific programs or specific features — the per-program matrix in section 7 says which. |
| **O** | Optional. Improves quality, precision, or explainability. |
| **P** | Contains PII. Subject to the boundary rules in section 10. Shown as `O (PII)` or `R (PII)`. |

"Grain" means the level at which one row is unique. Getting grain wrong is the single most common
cause of a wrong Average Headcount, because the denominator of every average depends on it.

---

## 3. The calculation chain

Every data requirement below exists because a specific calculation stage consumes it. This is the
chain, in order.

| # | Stage | Consumes | Produces | Fails without |
| --- | --- | --- | --- | --- |
| 0 | Source acquisition and manifest | Raw payroll files, file hashes | Immutable, hashed, ordered source manifest | Reproducibility, audit defensibility |
| 1 | Fiscal-window trim | `Pay_Date`, client fiscal calendar | Rows in the analysis window (cash basis — wages count in the year **paid**, not earned) | Fiscal calendar; wrong year attribution |
| 2 | Duplicate collapse | Employee, unit, FEIN, PPS, PPE, pay date, frequency | One fact row per dimensional key, signed hours/wages summed | Any key component; double-counted totals |
| 3 | Pay-code classification | `Pay_Code` + pay-code master | Includable wage base per the program's wage basis | Pay code; wage base is wrong for every program that is not "all remuneration" |
| 4 | Common employee totals | Includable hours and wages | `TotalHours`, `TotalWages` per employee | — |
| 5a | Denominator — Pay Period method | `PPS`, `PPE` per included period | Weeks = Σ (PPE − PPS + 1) / 7 | Period start/end dates |
| 5b | Denominator — Min-Max method | Earliest PPS, latest PPE, hire/term dates | Weeks = (LastEnd − FirstStart) / 7 | Hire/term dates to cap the span correctly |
| 6 | Eligibility test | Averages vs. `min_weekly_hours` and `min_weekly_wages` for the tax year | Per-employee eligible / not eligible | Annual wage floor table |
| 7 | One/Zero matrix | Eligible employees × unit × 12 month-end measuring dates | 1 or 0 per employee-unit-month | Unit ID; program `measuring_date` |
| 8 | Unit summary | Monthly unit totals | Average Headcount per unit = Σ months / included month count | — |
| 9 | Net-new vs. base | Current Average Headcount, frozen base-year headcount, high-water mark, tranche history | Qualifying jobs | **Client claim history** — not in payroll |
| 10 | Geographic qualification | Worksite county/FIPS, NAICS, annual designation table | Tier, zone, minimum-new-jobs threshold, per-job value | County designation table |
| 11 | Credit valuation | Qualifying jobs × per-job value × benefit period | Annual and lifetime credit | Program rule pack |
| 12 | Carryforward and filing | Prior claims, carryforward balances, form metadata | Claimable amount, filing package | Claim history; filing rules |
| 13 | Evidence and trail | Every stage's inputs, formula, output, citation | Audit-defensible provenance record | Source manifest; rule-pack provenance |

Stages 0–8 are payroll-driven. Stages 9–13 are **not**. That is the whole argument for the
supporting datasets.

---

## 4. Data domains at a glance

| ID | Domain | Grain | Typical source | Refresh | Tier |
| --- | --- | --- | --- | --- | --- |
| D1 | Payroll fact | Employee × pay period × unit × pay code | Client payroll / HCM (ADP, UKG, Workday, Paycom) | Per payroll run; annual bulk for retro | 0 |
| D2 | Employee master | Employee | Client HCM | Daily / with payroll | 1 |
| D3 | Worksite master | Worksite / unit | Client HCM or facilities | On change | 1 |
| D4 | Legal entity master | FEIN | Client tax / corporate | On change | 1 |
| D5 | Pay code master | Earning code | Client payroll config | On change | 1 |
| D6 | Program rule pack | Program × version | Statute, DOR/DCA guidance, the partner's SME | Annual + on statute change | 1 |
| D7 | Geographic designation | State × county × tax year | State agency annual memo (e.g. GA DCA) | Annual | 1 |
| D8 | Annual wage/hour floor | Program × tax year | State annual publication (e.g. GA JTC historical wage table) | Annual | 1 |
| D9 | Client configuration | Client × program × tax year | The partner's engagement setup | Per engagement | 1 |
| D10 | Claim and base-year history | Client × program × site × tax year | Client tax returns / the partner's own claim-tracking system | Annual | 1 |
| D11 | WOTC certification | Employee × hire event | DOL ETA 9061/9062, SWA certification | Per hire | 2 |
| D12 | Run manifest and provenance | Run | Generated by the platform | Per run | 0 |

---

## 5. Minimum viable payroll dataset

### 5.1 Tier 0 — the eight fields the engine cannot run without

This is the answer to "what is the absolute minimum payroll dataset." It produces an Average
Headcount and nothing more.

| # | Field | Type | Why it is load-bearing |
| --- | --- | --- | --- |
| 1 | `Employee_ID` | string | Surrogate key. Grain of every total, average, and eligibility test. Must be stable across the whole analysis window and across files. |
| 2 | `Worksite_ID` | string | The headcount unit. GA and SC test headcount at unit/county grain; the One/Zero matrix is employee × **unit** × month. |
| 3 | `Entity_FEIN` | string | Taxpayer identity. Some programs prohibit entity combination, so each FEIN is a separate calculation. |
| 4 | `Pay_Period_Start` | date | Denominator numerator for both methods. |
| 5 | `Pay_Period_End` | date | Denominator and the One/Zero month-coverage test. |
| 6 | `Pay_Date` | date | Cash-basis fiscal-year anchor. Wages count in the year **paid**. Also the pay-period dedupe key. |
| 7 | `Hours` | decimal | Numerator of the weekly-hours average. Signed — negative corrections must be preserved. |
| 8 | `Wages` | decimal | Numerator of the weekly-wages average. Signed. |

`Tax_Year` is a ninth column in practice but is derivable from `Pay_Date` plus the client's fiscal
calendar. Ship it anyway as a control, but never trust it over `Pay_Date` — in the current partner
extract the source `Tax Year` column does not agree with the fiscal window that reproduces the partner's
control totals.

### 5.2 What Tier 0 cannot do

State this explicitly to the partner, because it is the reason the request is larger than eight fields.

| Cannot do | Because it is missing |
| --- | --- |
| Apply the correct wage basis | `Pay_Code`. GA uses all remuneration; NC, OH, CO, VA, TN, FL use base pay only. Without a pay code the same wage figure is used for both, which is wrong for six of the ten programs. |
| Cap the Min-Max span correctly | `Hire_Date`, `Term_Date`. Today `hire_term_caps_available` is `false` in every reference run, so a mid-year hire's denominator is inferred from payroll activity rather than employment dates. |
| Apply part-time and seasonal weighting | `Employment_Type`, `Rate_Type`. SC counts 20–32 hrs as 0.5 of a head; TN counts PT ≥20 hrs and seasonal ≥26 weeks as 0.5 job; GA admits seasonal only if the job is otherwise full-time. |
| Resolve county tier, wage floor, or zone | Worksite county / FIPS. The GA wage floor is the average weekly wage of the **lowest-wage county**, and the tier drives both the minimum-new-jobs threshold and the per-job dollar value. |
| Apply the GA eligible-industry test | Worksite NAICS. Tier 1 requires an eligible industry (manufacturing, warehousing, distribution, telecom, R&D) unless the site is Tier-1-bottom-40, a Military Zone, an Opportunity Zone, or a Less Developed Census Tract — in which case retail also qualifies. |
| Produce a credit dollar figure | Base-year Average Headcount and prior claim history. Net-new is measured against a **frozen base year with a high-water mark**, not against the prior year. |
| Reconcile the two methods with confidence | Pay-cycle group definition. `PayFrequency` in the current extract is mislabelled (see section 11). |

### 5.3 Tier 1 — defensible calculation

Tier 0 plus:

- **Payroll fact:** `Pay_Code`, `Job_Title`, `Pay_Frequency`
- **Employee master:** `Hire_Date`, `Rehire_Date`, `Term_Date`, `Last_Day_Worked`, `Term_Reason`,
  `Employment_Type`, `Wage_Type`, `Status`, `Work_State`
- **Worksite master:** address, city, county, county FIPS, state, postal code, NAICS,
  `Date_Opened`, `Date_Closed`, `Location_Type`
- **Legal entity master:** FEIN, SEIN, legal entity name, parent/subsidiary relationship
- **Pay code master:** code, description, includable flags per wage basis
- **All reference domains:** D6 rule packs, D7 designations, D8 wage floors, D9 client config,
  D10 claim and base-year history

### 5.4 Tier 2 — full product surface

- WOTC certification data (D11), which requires PII and a 28-day-from-hire workflow
- Pay rate and rate type, for forecasting and "additional hours needed to qualify" coaching
- Health-benefit eligibility flags (TN requires minimum health care coverage for a qualified job)
- Capital investment / fixed-asset additions by site (TN requires $500,000; several negotiated
  programs have investment commitments)
- Union, apprenticeship, and training-hours data for programs that layer training credits
- Prior-year payroll for at least the base year plus every year in an open 5-year tranche

---

## 6. Data dictionary

### 6.1 D1 — Payroll fact

**Grain:** one row per employee, per pay period, per worksite, per FEIN, per pay code.
**Do not pre-aggregate.** The engine's dedupe, wage-basis filter, and denominator logic all require
transaction grain.

| Field | Type | Req | Description and calculation use |
| --- | --- | --- | --- |
| `Employee_ID` | string(50) | R | Stable surrogate employee key. Must not be an SSN. Must be consistent across all files and all tax years in the request. |
| `Tax_Year` | int | R | Source system's tax-year label. Control field only — the engine derives the fiscal year from `Pay_Date`. |
| `Worksite_ID` | string(50) | R | Unit / location key. Joins to D3. This is the headcount unit for unit-grain programs. |
| `Entity_FEIN` | string(10) | R | Employer FEIN, digits only or `NN-NNNNNNN`. Joins to D4. |
| `Pay_Period_Start` | date | R | Inclusive. Denominator basis for the Pay Period method. |
| `Pay_Period_End` | date | R | Inclusive. Denominator basis and month-coverage test for the One/Zero matrix. |
| `Pay_Date` | date | R | Paycheck / check date. Cash-basis fiscal anchor and the fiscal-window trim key. |
| `Pay_Frequency` | string(20) | R | Weekly / Biweekly / Semimonthly / Monthly. **Send the label, not a numeric code.** Retained as lineage; used to identify major pay cycles. |
| `Hours` | decimal(10,2) | R | Actual hours for the period and pay code. Signed — preserve negative corrections. Not overtime-weighted. |
| `Wages` | decimal(14,2) | R | Gross wages for the period and pay code. Signed. Unformatted numeric — no `$`, no thousands separators. |
| `Pay_Code` | string(30) | R | Earning code. Joins to D5. Drives the wage-basis filter. **Absent from the current partner extract.** |
| `Job_Title` | string(100) | C | Required for programs with occupation-based tests and for the eligible-industry narrative. |
| `Pay_Rate` | decimal(10,4) | O | Enables forecasting and the "hours needed to qualify" coaching surface. |
| `Rate_Type` | string(20) | O | Hourly / Salary. Disambiguates zero-hour salaried periods. |
| `Currency` | string(3) | O | ISO 4217. Default USD. Required if any entity pays in a non-USD currency. |
| `Source_File` | string(255) | R | Populated by the platform, not the client. Lineage for the manifest. |
| `Source_Row` | int | R | Populated by the platform. Lineage for the manifest. |

**Notes on grain and correctness**

- If the client's payroll system emits multiple lines per employee per period per earning code, send
  them all. The engine collapses on `(Employee_ID, Worksite_ID, Entity_FEIN, PPS, PPE, Pay_Date,
  Pay_Frequency)` and sums signed hours and wages, per assumption BA-04.
- Zero-hour rows are **retained** in the denominator under assumption BA-05 v5. Do not filter them
  out at source; that decision belongs to the engine and is a versioned assumption.
- Negative rows are corrections and must be preserved. The current reference extract contains 247
  negative-hour rows and 417 negative-wage rows.
- A `Pay_Date` earlier than `Pay_Period_End` is legitimate in some systems (2,981 such rows in the
  reference extract). Do not "fix" these at source; flag them.

### 6.2 D2 — Employee master

**Grain:** one row per employee (or per employee per effective-dated change).

| Field | Type | Req | Description and calculation use |
| --- | --- | --- | --- |
| `Employee_ID` | string(50) | R | Joins to D1. |
| `Hire_Date` | date | R | Caps the start of the Min-Max span. Without it the span is inferred from payroll activity. |
| `Rehire_Date` | date | C | Required where rehires are common. Determines whether a rehire is a net-new job or a replacement hire — most programs exclude replacement hires. |
| `Term_Date` | date | R | Caps the end of the Min-Max span. |
| `Last_Day_Worked` | date | C | Distinguishes the last worked day from the payroll termination date; affects the final month's One/Zero cell. |
| `Term_Reason` | string(50) | C | Joins to a term-code master. Voluntary vs. involuntary matters for maintenance/clawback tests in negotiated programs. |
| `Employment_Type` | string(20) | R | Full-Time / Part-Time / Seasonal / Temporary / Intern. Drives SC and TN fractional weighting and the GA seasonal condition. |
| `Wage_Type` | string(20) | C | Hourly / Salary / Commission. Explains zero-hour salaried periods. |
| `Status` | string(20) | C | Active / Terminated / Leave. Leave handling affects continuity tests. |
| `Job_Title` | string(100) | C | Occupation tests and industry narrative. |
| `Work_State` | string(2) | R | State of work, which may differ from the residence state and from the worksite's state for remote workers. |
| `Location_ID` / `Worksite_ID` | string(50) | R | Primary assignment. Joins to D3. |
| `Months_of_Service` | int | O | Convenience field; derivable. |
| `SUI_Acct` | string(30) | C | State unemployment account. Ties the employee to a state registration for multi-state filing. |
| `Is_Staffing_Placement` | bool | C | GA: staffing-entity employees qualify only when working full-time at a client in an eligible industry; the staffing entity's own internal employees are excluded. |
| `Client_NAICS` | string(6) | C | For staffing placements, the NAICS of the *client* worksite, not the staffing agency. |
| `Health_Benefit_Eligible` | bool | C | TN requires minimum health care coverage for a qualified job. |
| `First_Name`, `Last_Name`, `MI`, `Suffix` | string | O (PII) | Not required for the calculation. Required only for WOTC certification and for filing packages that name employees. |
| `SSN` | string(11) | O (PII) | Required only for WOTC certification. Never required for state jobs credits. |
| `DOB` | date | O (PII) | WOTC target-group age tests only. |
| `Home_Address`, `City`, `State`, `Zip`, `Country` | string | O (PII) | WOTC designated-community-resident and empowerment-zone tests only. |

### 6.3 D3 — Worksite / location master

**Grain:** one row per worksite per effective-dated period.

| Field | Type | Req | Description and calculation use |
| --- | --- | --- | --- |
| `Worksite_ID` | string(50) | R | Joins to D1 and D2. |
| `Employer_Location_ID` | string(50) | C | Client's own location key where it differs from the worksite key. |
| `FEIN` | string(10) | R | Owning legal entity. Joins to D4. |
| `SEIN` | string(30) | C | State employer identification number. Required for state filing. |
| `Entity_Name` | string(200) | R | Legal entity name for the filing package. |
| `Internal_Location_Name` | string(200) | O | Display name. |
| `External_Location_Name` | string(200) | O | Public / DBA name. |
| `Location_Type` | string(50) | C | Distribution, Manufacturing, Office, Retail, R&D. Feeds the eligible-industry test. |
| `NAICS_Code` | string(6) | R | **Site-level**, not corporate-level. Drives GA Tier 1 eligible-industry qualification and FL/NY targeted-industry tests. |
| `Street`, `City`, `State`, `Postal_Code`, `Country_Code` | string | R | Full physical address. Needed to resolve county, census tract, and zone overlays. A city name alone is not sufficient. |
| `County` | string(60) | R | County name. Drives the GA/SC/NC county-grain headcount test and the designation lookup. |
| `County_FIPS` | string(5) | R | Five-digit state+county FIPS. The reliable join key to D7; county *names* are ambiguous across states. |
| `Census_Tract_GEOID` | string(11) | C | Required for Less Developed Census Tract, Opportunity Zone, and Enterprise Zone overlays. A street address is not enough — the tract must be resolved. |
| `Date_Opened` | date | R | Establishes greenfield vs. expansion, and the base year for a new site. |
| `Date_Closed` | date | C | Site closure affects maintenance tests and clawback exposure. |
| `Latitude`, `Longitude` | decimal(9,6) | O | Map surfaces only. |
| `Is_Leased` / `Is_Owned` | bool | O | Some negotiated programs test facility control. |

### 6.4 D4 — Legal entity master

**Grain:** one row per FEIN.

| Field | Type | Req | Description and calculation use |
| --- | --- | --- | --- |
| `FEIN` | string(10) | R | Primary key. |
| `Legal_Entity_Name` | string(200) | R | Filing identity. |
| `Entity_Type` | string(30) | R | C-corp / S-corp / Partnership / LLC / Disregarded. Determines the GA return form (600, 600S, 700). |
| `Parent_FEIN` | string(10) | C | Controlled-group structure. Required to evaluate whether entity combination is permitted, required, or prohibited. |
| `State_Registrations` | list | C | States where the entity is registered, with SEIN per state. |
| `Fiscal_Year_End_Month` | int | R | 1–12. Drives the fiscal-window calculation. Calendar-year clients are 12; the engine supports non-calendar year-ends. |
| `Consolidated_Filing_Group` | string(50) | C | Groups entities that file together. |

Programs differ on entity combination: GA permits it, federal WOTC prohibits it (each employer files
its own), and several packs are still pending confirmation. This is why the parent/subsidiary
structure is a data requirement rather than a nicety.

### 6.5 D5 — Pay code / earning code master

**Grain:** one row per earning code.

| Field | Type | Req | Description and calculation use |
| --- | --- | --- | --- |
| `Pay_Code` | string(30) | R | Joins to D1. |
| `Description` | string(200) | R | Human-readable meaning. Required so the wage-basis mapping can be reviewed and signed off. |
| `Category` | string(30) | R | Base / Overtime / Premium / Bonus / Commission / Leave / Reimbursement / Non-cash / Imputed. |
| `Is_Cash_Compensation` | bool | R | Distinguishes cash wages from imputed income and reimbursements. |
| `Includable_Base_Pay` | bool | R | Wage base for base-pay-only programs (NC, OH, CO, VA, TN, FL). |
| `Includable_All_Remuneration` | bool | R | Wage base for all-remuneration programs (GA, NY). |
| `Includable_WOTC` | bool | C | The Fabric seed already models this as a separate `WOTC_PayCode` mapping. |
| `Contributes_Hours` | bool | R | Whether hours on this code count toward the weekly-hours test. Holiday and PTO treatment is a program-level decision that must be made explicitly, not by accident. |

Ask the client for **every** code in use during the analysis window, including retired codes. A code
that appears in payroll but not in the master is a hard stop, not a warning — it means the wage base
is undefined.

### 6.6 D6 — Program rule pack

**Grain:** one document per program per version. Managed by us, not the client. Reproduced here so
the Data SE can model it and the SSP can see the SME dependency.

| Block | Field | Type | Description |
| --- | --- | --- | --- |
| root | `rule_pack_version` | semver | Immutable once used in a recorded run. |
| `jurisdiction` | `level`, `code`, `name` | string | federal / state / local. |
| `credit` | `code`, `name`, `statutory_citation`, `tier`, `summary` | string | Identity and citation for the audit trail. |
| `thresholds` | `minimum_new_jobs` | int | Statutory job floor. Tier-dependent in GA and TN. |
| | `minimum_hours_per_week_full_time` | decimal | 35 (GA, NY, NC, FL, OH, CO, VA), 32 (SC), 37.5 (TN). |
| | `minimum_investment_usd` | decimal | TN: $500,000. Requires capital-expenditure data. |
| | `minimum_annual_payroll_per_job_usd` | decimal | OH: $35,000. |
| | `minimum_wage_pct_of_local_average` | decimal | FL: 1.15 × county average private-sector wage. Requires an external county wage series. |
| | `tier3_minimum_new_jobs`, `tier4_minimum_new_jobs` | int | TN enhancement-county reductions. |
| | `eligibility_scope` | enum | statewide / designated-geography. |
| `benefit` | `amount_per_qualifying_job_usd` | decimal | GA Tier 1 $3,500; TN $4,500. |
| | `amount_per_qualifying_job_pct_of_wages` | decimal | NY Excelsior 6.5%. Mutually exclusive with the flat amount. |
| | `benefit_period_years` | int | GA 5, NY 10, TN 5. |
| | `carryforward_years` | int | GA 10, TN 15 (25 for years ending on/after 2008-12-31). |
| | `retroactive_years` | int | TN 15. Drives how far back a retroactive scan runs. |
| | `geography_value_tiers` | object | Base vs. enhancement additions. |
| `eligibility` | `qualifying_employment_type` | enum | full_time / any. |
| | `include_replacement_hires` | bool | Almost always false — requires rehire/term data to enforce. |
| | `include_seasonal` + `seasonal_conditions` | object | GA admits seasonal when the job is otherwise full-time. |
| | `staffing_entity_conditions` | object | GA staffing rules. |
| | `geographic_scope` | object | Level and designation gating. |
| `headcount_formula` | `type`, `fte_basis_hours_per_week`, `compare_to_prior_period_months`, `partial_month_handling` | mixed | Quick-estimate metric only; the statutory engine is `one_zero`. |
| `one_zero` | `min_weekly_hours` | decimal | Statutory hours floor. |
| | `min_weekly_wages` | decimal | Weekly wage floor. **Year-specific — see D8.** SC has none (0). |
| | `wage_basis` | enum | `regular` (base pay) or `all_remuneration`. Determines which D5 flag is used. |
| | `geographic_granularity` | enum | unit / county / statewide. Determines the headcount unit. |
| | `pt_aggregation` | bool | Whether part-time hours aggregate into full-time equivalents. |
| | `pt_band_hours`, `pt_weight` | array, decimal | SC: 20–32 hrs at 0.5. TN: PT ≥20 hrs and seasonal ≥26 wks at 0.5. |
| | `headcount_unit_field` | string | Which payroll column is the unit. |
| | `measuring_date` | enum | `last_day` for GA/SC. The "magical pay date" varies by state. |
| | `entity_combination` | enum | required / permitted / prohibited. |
| | `pay_code_policy` | object | `included_pay_codes`, `excluded_pay_codes`. |
| | `thresholds_by_year` | map | Year-keyed overrides. This is where the annual wage floor lands. |
| `filing` | `form`, `attach_to_return`, `filing_channel`, `window`, `cycle`, `deadline_note`, `required_attachments` | mixed | GA: Form IT-CA attached to 600 / 600S / 700, via Georgia Tax Center. |
| provenance | `authority`, `title`, `url`, `retrieved_at`, `confidence`, `artifact_sha256`, `_prototype_verify` | mixed | Per-value citation. Every threshold must carry one — thresholds are never hand-entered. |

### 6.7 D7 — Geographic designation table

**Grain:** one row per state × county (or census tract) × tax year. Annual, published by the state.

| Field | Type | Req | Description |
| --- | --- | --- | --- |
| `State` | string(2) | R | |
| `County` | string(60) | R | |
| `County_FIPS` | string(5) | R | Join key. |
| `Tax_Year` | int | R | Designations change annually. A designation change mid-window spawns a **parallel calculation** — each designation is its own analysis with its own threshold and benefit window. |
| `Tier` | int | R | GA 1–4; TN 1–4 enhancement tiers. |
| `Designation` | string(100) | R | Tier 1 Standard, Tier 1 Bottom 40, Less Developed Census Tract, Military Zone, Opportunity Zone, Enterprise Zone, Enhancement County. |
| `Minimum_New_Jobs` | int | R | GA pattern: Tier 1 = 2, Tier 2 = 10, Tier 3 = 15, Tier 4 = 25. |
| `Per_Job_Credit_USD` | decimal | R | Tier-dependent value. |
| `Benefit_Period_Years` | int | R | |
| `Eligible_Industries_Required` | bool | R | GA: true for standard Tier 1, false for bottom-40 / MZ / OZ / LDCT where retail also qualifies. |
| `Eligible_NAICS` | list | C | Where an industry gate applies. |
| `Effective_From`, `Effective_To` | date | R | |
| `Source_Document`, `Source_URL`, `Source_SHA256`, `Published_Date` | mixed | R | The annual ranking memo. GA's is published by the Department of Community Affairs. |

### 6.8 D8 — Annual wage and hour floor table

**Grain:** one row per program × tax year. This is the "state/county minimum hourly/wage per tax
year" dataset. It is small, annual, and absolutely load-bearing — it is the single number that
decides eligibility for every employee.

| Field | Type | Req | Description |
| --- | --- | --- | --- |
| `Program_Code` | string(20) | R | e.g. `GA_JTC`. |
| `Tax_Year` | int | R | The client's tax year. |
| `Source_Report_Year` | int | R | The underlying labour-statistics year, which lags. GA Tax Year 2023 uses **DOL Report Year 2022**. |
| `Basis_County` | string(60) | C | GA uses the average weekly wage of the **lowest-wage county**. Tax Year 2023 = Glascock. |
| `Min_Avg_Weekly_Wages_USD` | decimal(10,2) | R | GA: 2023 = $636.00, 2024 = $686.00, 2025 = $680.00. |
| `Annualized_Wage_USD` | decimal(12,2) | R | GA 2023 = $33,072.00. Cross-check against the weekly figure. |
| `Min_Avg_Weekly_Hours` | decimal(5,2) | R | GA 35.0, SC 32.0, TN 37.5. |
| `Regulation_Citation` | string(200) | R | GA: 110-9-1-.02(1)(a) and 110-9-1-.03(3)(b)1. |
| `Rounding_Mode` | enum | R | `half_up`. |
| `Test_Decimals` | int | R | 2. Averages are rounded to two decimals **before** the threshold comparison. This materially changes borderline outcomes. |
| `Source_Document`, `Source_SHA256`, `Retrieved_At` | mixed | R | e.g. `JTCHistoricalWages_Jul 2025.pdf`, SHA-256 `21A8D166…D8208`. |

Two traps worth flagging to the Data SE:

1. **The floor is keyed on the client's tax year, not on the labour-statistics year.** The lag is a
   modelled attribute, not an off-by-one bug.
2. **Rounding happens before comparison.** A two-decimal average of `635.995` rounds to `636.00` and
   passes a `$636` floor. Full-precision comparison would fail it. This is why `rounding_mode` and
   `test_decimals` are schema fields rather than code constants.

### 6.9 D9 — Client configuration

**Grain:** one row per client × program × tax year. Set during engagement onboarding.

| Field | Type | Req | Description |
| --- | --- | --- | --- |
| `Client_ID` | string(50) | R | |
| `Program_Code` | string(20) | R | |
| `Tax_Year` | int | R | |
| `Fiscal_Year_Begin`, `Fiscal_Year_End` | date | R | Reference example: 2023-07-28 to 2024-08-02. Not necessarily calendar-aligned and not necessarily 365 days. |
| `Fiscal_Year_End_Month` | int | R | Drives fiscal-year labelling for non-calendar filers. |
| `Trim_Basis` | enum | R | `pay_date_only` per assumption BA-02. |
| `Pay_Cycle_Groups` | list | R | The client's **material payroll dates**. Required by the Pay Period method's major-period step and is currently a sign-off gate, not a computed value. |
| `Denominator_Mode` | enum | R | `actual_span_inclusive` per BA-03. |
| `Min_Max_Span_Mode` | enum | R | `exclusive_days` per BA-11. |
| `Zero_Hour_Period_Treatment` | enum | R | `retain` per BA-05 v5. |
| `Entity_Combination_Election` | enum | C | Where the program permits a choice. |
| `Negotiated_Agreement` | object | C | Threshold override, wage/hour commitments, investment commitments, clawback terms. Overrides the statutory threshold — for example an agreement requiring "100 jobs at $18/hr". |
| `Assumption_Set_ID` | string(40) | R | e.g. `GDS-STEP1-2026-08-05-v5`. Immutable once used. |

### 6.10 D10 — Claim and base-year history

**Grain:** one row per client × program × site (or FEIN) × tax year. This is the dataset most likely
to be forgotten, and without it no credit dollar figure can be produced at all.

| Field | Type | Req | Description |
| --- | --- | --- | --- |
| `Client_ID`, `Program_Code`, `Worksite_ID`, `FEIN`, `Tax_Year` | mixed | R | Composite key. |
| `Base_Year` | int | R | The frozen base year. Georgia measures against a frozen base, not a rolling prior year. |
| `Base_Average_Headcount` | decimal(10,2) | R | The frozen baseline figure. |
| `High_Water_Mark` | decimal(10,2) | R | Running maximum Average Headcount through the year. Determines whether a year creates a fresh tranche or backfills an existing one. |
| `Tranche_ID` | string(40) | R | Each net-new-job layer earns the credit for the full benefit period; tranches run concurrently. |
| `Tranche_Start_Year`, `Tranche_Years_Remaining` | int | R | |
| `Qualifying_Jobs_Claimed` | decimal(10,2) | R | |
| `Credit_Earned_USD`, `Credit_Claimed_USD`, `Credit_Carried_Forward_USD` | decimal(14,2) | R | Carryforward balances expire — GA at 10 years, TN at 15 or 25. |
| `Carryforward_Expiry_Year` | int | R | |
| `Return_Filed`, `Form_Number`, `Filed_Date`, `Amended` | mixed | C | Determines whether a retroactive claim needs an amended return. |
| `Clawback_Exposure_USD` | decimal(14,2) | C | Negotiated programs with maintenance requirements. |

Sources: the client's filed returns, and the partner's own claim-tracking records where the partner has
been the provider historically. Where neither exists, the base year has to be **established** from
payroll — which is why the payroll request must cover the base year plus every year in an open
tranche, not just the current year.

### 6.11 D11 — WOTC certification (federal only)

**Grain:** one row per employee per hire event. Materially different from everything above: it is
per-hire, time-boxed, and requires PII.

| Field | Type | Req | Description |
| --- | --- | --- | --- |
| `Employee_ID`, `Hire_Date` | mixed | R | |
| `SSN`, `DOB`, `Home_Address` | mixed | R (PII) | Required for state workforce agency certification. |
| `Target_Group_Code` | string(10) | R | Veteran, SNAP, long-term unemployed, ex-felon, designated-community resident, vocational rehabilitation, SSI, summer youth. |
| `ETA_9061_Submitted_Date` | date | R | **Must be within 28 days of hire.** A missed window forfeits the credit permanently — this is a workflow requirement, not just a data requirement. |
| `ETA_9062_Conditional_Cert` | bool | C | |
| `SWA_Certification_Status`, `SWA_Certification_Date` | mixed | R | |
| `First_Year_Hours` | decimal(10,2) | R | 120-hour minimum; 400 hours unlocks the full rate. Derivable from D1 given hire date. |
| `First_Year_Qualified_Wages` | decimal(12,2) | R | Subject to per-target-group caps. |
| `Max_Credit_USD` | decimal(10,2) | R | $1,200–$9,600 by target group. |

### 6.12 D12 — Run manifest and provenance

**Grain:** one row per run. Generated by the platform; listed so the Data SE models storage for it.

| Field | Type | Description |
| --- | --- | --- |
| `Run_ID`, `Run_Timestamp` | mixed | |
| `Assumption_Set_ID`, `Assumption_Set_SHA256` | string | Which versioned assumptions produced this result. |
| `Source_Manifest_SHA256` | string | |
| `Code_Commit` | string(40) | |
| `Files[]` | array | Per file: name, byte size, SHA-256, column list, physical rows, usable rows, padded rows, invalid rows. |
| `Controls` | object | Distinct employees, FEINs, units; earliest/latest pay date and period date; zero-hour, negative-hour, negative-wage, duplicate-group counts. |
| `Rule_Pack_Version`, `Rule_Pack_Provenance[]` | mixed | Per-value citation for every threshold used. |
| `Calculation_Trail[]` | array | Per stage: step, inputs, formula, output, citation. |
| `Exceptions[]` | array | Every flag raised, with disposition and reviewer. |

---

## 7. Per-program supporting-data matrix

Payroll is common to all. This shows what each program needs **beyond** payroll.

| Requirement | GA JTC | TN JTC | SC JTC | NC JTEC | NY Excelsior | FL QTI | OH JCTC | CO EZ | VA MBJF | Fed WOTC |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| Annual wage floor table (D8) | R | R | — | R | R | R | R | R | R | — |
| County tier / designation (D7) | R | R | R | R | — | — | — | R | — | — |
| Census tract / zone overlay | R | — | — | — | — | — | — | R | — | C |
| Worksite NAICS | R | C | C | C | R | R | C | C | C | — |
| Base-year and claim history (D10) | R | R | R | R | R | R | R | R | R | — |
| Employment type (FT/PT/seasonal) | R | R | R | C | C | C | C | C | C | — |
| Pay code + wage-basis mapping | R | R | R | R | R | R | R | R | R | R |
| Hire / rehire / term dates | R | R | R | R | R | R | R | R | R | R |
| Capital investment by site | — | R | — | — | C | C | C | — | C | — |
| Health-benefit eligibility | — | R | — | — | — | — | — | — | — | — |
| Negotiated agreement terms | C | C | C | C | R | R | R | C | C | — |
| State certificate / pre-approval | — | — | — | — | R | R | R | R | C | — |
| County average wage series | — | — | — | R | — | R | — | — | — | — |
| Employee PII | — | — | — | — | — | — | — | — | — | R |
| 28-day certification workflow | — | — | — | — | — | — | — | — | — | R |

Headline: **wage basis, hire/term dates, and base-year history are required by every program.** They
are the three things most often missing from a first payroll extract.

---

## 8. Data quality gates and acceptance criteria

Run these against the client extract **before** any calculation is presented. Each is currently
implemented as a report-only control — nothing auto-repairs, and nothing is silently dropped.

### 8.1 Source integrity

| Gate | Acceptance criterion |
| --- | --- |
| File hash | Every file SHA-256 recorded before parsing. |
| Column conformance | Header matches the agreed contract exactly, including order. |
| Padding rows | Fully blank trailing rows identified and excluded from usable counts, not from physical counts. |
| Chunk completeness | Multi-file exports treated as one ordered logical source, no cross-file dedupe. |
| Control totals | Row count, total hours, total wages, distinct employees reconcile to the client's own figures **before** any transformation. |

### 8.2 Referential integrity

| Gate | Acceptance criterion |
| --- | --- |
| Every `Worksite_ID` in D1 exists in D3 | Zero orphans. An orphan worksite means no county, no tier, no credit. |
| Every `Entity_FEIN` in D1 exists in D4 | Zero orphans. |
| Every `Pay_Code` in D1 exists in D5 | Zero orphans. **Hard stop** — an unmapped code means an undefined wage base. |
| Every `Employee_ID` in D1 exists in D2 | Zero orphans once D2 is in scope. |
| Every worksite county resolves in D7 for the tax year | Zero unresolved. |

### 8.3 Temporal integrity

| Gate | Acceptance criterion |
| --- | --- |
| Boundary completeness | The window includes prior-period paychecks landing inside it. Report, never synthesize, missing lookback. |
| Continuous pay cycles | No missing pay period in any cycle. The reference extract fails this: November 2023's second-half semi-monthly period ends 2023-11-24 instead of month end, so **no** semi-monthly period covers 2023-11-30 and every semi-monthly employee scores 0 in that month. July 2024 has no second-half semi-monthly period at all. |
| `PPS ≤ PPE` | Zero violations. |
| Pay date vs. period end | Report `Pay_Date < Pay_Period_End` rows; do not repair. |
| Coverage of the full window | Earliest and latest pay dates bracket the configured fiscal window. |

### 8.4 Calculation invariants

| Gate | Acceptance criterion |
| --- | --- |
| Pay Period weeks ≤ Min-Max weeks | Report every violation. Never cap or auto-repair. |
| Pay Period weeks ≤ 53 | Report every employee above the ceiling for review. |
| Test of twos | No employee counted at more than one unit in the same month. Every occurrence is surfaced for human disposition; nothing is auto-removed. |
| Meaningful pay periods | Trivially small periods (below ~$50 and ~4 hours) flagged for review. Hours and wages are retained; only the period *structure* is at issue. |
| Method reconciliation | Pay Period and Min-Max eligible lists are compared and every disagreement is drilled to the first divergent stage. The two methods are not required to agree — but every difference must be explained. |
| Sign-off gate | A result cannot be signed off while major-cycle groups or test-of-twos dispositions are inferred rather than reviewed. |

### 8.5 Reference-data currency

| Gate | Acceptance criterion |
| --- | --- |
| Wage floor | A D8 row exists for the exact program and tax year. No fallback to a flat default in a client-facing result. |
| Designation | A D7 row exists for the worksite's county and tax year. |
| Rule pack | Every threshold used carries provenance with an authority, a source, and a retrieval date. |
| Verification flags | No value still marked `_prototype_verify: true` is used in a client deliverable without SME sign-off. |

---

## 9. Volumetrics, formats, and delivery

### 9.1 Observed volumetrics

From the current partner TCC extract — one client, one fiscal year:

| Measure | Value |
| --- | --- |
| Physical rows | 488,968 |
| Usable rows after padding removal | 384,433 |
| Distinct employees | 10,236 |
| Distinct units | 101 |
| Distinct FEINs | 2 |
| Duplicate groups / rows in them | 126,420 / 304,934 |
| Zero-hour rows | 129,619 |
| Negative hour / wage rows | 247 / 417 |
| Files / total size | 4 / ~36 MB uncompressed |
| Date range | 2023-08-01 to 2024-08-09 |

Sizing rule of thumb: roughly **38 payroll rows per employee per year** at this client's mix.
A base year plus a 5-year tranche window is therefore ~6× that per client. For a 50,000-employee
client across six years, plan for roughly 11–12 million fact rows.

### 9.2 Format contract

| Item | Requirement |
| --- | --- |
| Format | Delimited text (CSV) or Parquet. Parquet strongly preferred at volume — it preserves types and removes the currency-formatting problem entirely. |
| Encoding | UTF-8 without BOM. |
| Dates | ISO 8601 `YYYY-MM-DD`. The current extract uses `M/D/YYYY`, which is ambiguous and forces a parser fallback. |
| Numerics | Unformatted. No `$`, no thousands separators, no trailing spaces, no parenthesised negatives. The current Employees extract ships `"$2,061.19 "` as a string. |
| Nulls | Empty field, not the literal strings `NULL`, `N/A`, or `-`. |
| Line endings | Consistent within a file. |
| Chunking | If chunked, chunks are an ordered logical union with no cross-file dedupe, and a manifest states the order. |
| Header | Present in every chunk, identical across chunks. |
| Padding | No blank trailing rows. If unavoidable, state the count. |
| Compression | gzip or zstd per file. |
| Integrity | SHA-256 per file, supplied alongside. |
| Transport | Client-controlled secure channel. Records containing PII must never traverse an unlabelled channel. |

---

## 10. Privacy and PII boundary

The Silver Record Layout is 16 fields: **11 required, 5 PII, and the 5 PII fields are optional by
design.** That is a product principle, not an oversight — PII never needs to leave the client's
database to compute a state jobs credit.

| Category | Fields | Position |
| --- | --- | --- |
| Never required for state credits | SSN, first name, last name, date of birth, home address | Do not request. Do not accept if volunteered. |
| Required only for federal WOTC | SSN, DOB, home address, name | Request only when WOTC is in scope, under a separate agreement, into a separately governed store. |
| Pseudonymous keys | `Employee_ID` | Must be a surrogate. Reject any extract where the employee key is an SSN or an SSN fragment. |
| Quasi-identifiers | Job title, hire date, worksite, wage | Retained. Re-identification risk is real at small worksites; treat aggregate outputs below a small-cell threshold accordingly. |

Practical asks for the data request:

1. State the surrogate-key requirement explicitly, and require that the mapping table stays with the
   client.
2. Require that the extract is generated with PII columns excluded at source rather than nulled,
   so they never enter the transfer.
3. Apply and preserve sensitivity labelling on every artifact derived from client payroll.
4. Define retention and destruction terms per tax year, aligned to the longest carryforward window
   in scope (TN reaches 25 years, which is longer than most standard retention schedules).

---

## 11. Known gaps in the current partner extract

These are observed facts about the four TCC payroll chunks, not hypotheticals. They are the strongest
evidence for the expanded request.

| # | Gap | Consequence | Ask |
| --- | --- | --- | --- |
| 1 | No `Pay_Code` column | The wage-basis filter cannot run. GA's all-remuneration rule and the base-pay-only rule used by six other programs currently resolve to the same number. | Add `Pay_Code` to the fact extract plus a pay-code master with includable flags. |
| 2 | No hire or termination dates | `hire_term_caps_available` is `false` in every reference run. Min-Max spans are inferred from payroll activity, which is not the documented method. | Add D2 employee master. |
| 3 | No employment type | SC part-time weighting, TN part-time and seasonal 0.5-job rules, and the GA seasonal condition cannot be applied. | Add `Employment_Type` and `Wage_Type`. |
| 4 | No worksite dimension | 101 unit IDs with no address, county, FIPS, or NAICS. County tier, wage floor basis, and eligible-industry tests are all unresolvable. | Add D3 worksite master. |
| 5 | `PayFrequency` is mislabelled | Documented as "weeks in pay period", but code 4 is always a 16-day 16th-to-31st period and code 2 is predominantly a 15-day 1st-to-15th period. Applying the codes literally yields 447 eligible against a reported 659. The denominator now uses actual period spans and ignores the code. | Confirm the true meaning of each code, or replace with a text frequency label. |
| 6 | Semi-monthly cycle truncation | November 2023's second-half period ends 2023-11-24, so no period covers month end and semi-monthly employees score 0 in that month — Pay Period M4 drops to 311 against a ~520 neighbour-month baseline. July 2024 has no second-half period at all. | Confirm whether this is a source-system artifact or a genuine payroll event. Blocks M4 sign-off. |
| 7 | No pay-cycle group definition | The Pay Period method's major-period step is diagnostic only and remains an unresolved sign-off gate. | Ask the client to state its material payroll dates. |
| 8 | No base-year or claim history | Net-new cannot be computed against a frozen base with a high-water mark. Only Average Headcount can be produced. | Add D10, or extend the payroll request to cover the base year and all open tranche years. |
| 9 | Source `Tax Year` disagrees with the fiscal window | The window that reproduces the reported control totals is 2023-07-28 to 2024-08-02, trimmed on paycheck date only. | Confirm the client's fiscal calendar and the source column's meaning. |
| 10 | Currency and dates arrive formatted as strings | Parser fallbacks and a class of silent coercion bugs. | Apply the section 9.2 format contract. |

---

## 12. Open questions for the partner

Ordered by blocking impact.

**Data content**

1. Can the payroll extract include the earning/pay code, and can we get the client's full earning-code
   master including retired codes?
2. Can we get the employee master (hire, rehire, term, last day worked, term reason, employment type,
   status, work state)?
3. Can we get the worksite master with full street address, county, county FIPS, NAICS, and open/close
   dates?
4. How many prior years can be supplied? We need the frozen base year plus every year in an open
   5-year tranche — for GA that is up to 6 years, for TN's retroactive window potentially 15.
5. Does the partner hold the client's prior claim history and carryforward balances in its own
   claim-tracking system, or does that come from the client's filed returns?

**Methodology**

6. What do `PayFrequency` codes 1, 2, and 4 actually mean in the source system?
7. Is the November 2023 semi-monthly truncation a source artifact or a real payroll event?
8. What are the client's material payroll dates (pay-cycle groups) for the Pay Period method's major-period step?
9. Confirm the eligible and excluded pay-code list for GA JTC.
10. Confirm the GA DCA annual ranking memo and the DOR employers page as the canonical sources for
    tier and wage-floor values.
11. Confirm the exact GA IT-CA form edition, e-file path, and attachment list.

**Scope**

12. Which programs are in scope for the first release beyond GA JTC? The per-program matrix in
    section 7 changes materially with TN (capital investment, health benefits) and WOTC (PII).
13. Is federal WOTC in scope? If so it needs a separate PII agreement and a 28-day certification
    workflow, not just a data feed.
14. Which entities are in the controlled group, and does the client have an entity-combination
    election on file?

---

## Appendix A — reference sample rows

**D1 payroll fact — target shape**

```
Tax_Year,Employee_ID,Job_Title,Worksite_ID,Pay_Period_Start,Pay_Period_End,Pay_Date,Entity_FEIN,Pay_Frequency,Hours,Wages,Pay_Code
2024,E00001,Logistics Analyst,GA_SAV_DC,2024-01-01,2024-01-14,2024-01-19,58-2233445,Biweekly,72.82,2061.19,Regular
2024,E00001,Logistics Analyst,GA_SAV_DC,2024-01-01,2024-01-14,2024-01-19,58-2233445,Biweekly,4.00,169.86,Overtime
```

**D1 payroll fact — current partner extract**

```
TCCEmployeeId,Tax Year,JobTitle,TCCUnitId,PayPeriodStart,PayPeriodEnd,PaycheckDate,PayFrequency,FEIN,Hours,Wages
16816619,2024,GSMGR,1134559,8/1/2023,8/3/2023,8/3/2023,1,234567890,81.25,123.29
```

Differences: no pay code, numeric frequency of uncertain meaning, ambiguous date format.

**D8 annual wage floor**

```
Program_Code,Tax_Year,Source_Report_Year,Basis_County,Min_Avg_Weekly_Wages_USD,Annualized_Wage_USD,Min_Avg_Weekly_Hours,Regulation_Citation
GA_JTC,2023,2022,Glascock,636.00,33072.00,35.00,110-9-1-.02(1)(a); 110-9-1-.03(3)(b)1
GA_JTC,2024,2023,,686.00,,35.00,110-9-1-.02(1)(a)
GA_JTC,2025,2024,Taliaferro,680.00,,35.00,110-9-1-.02(1)(a)
```

---

## Appendix B — field-to-stage traceability

| Field | Stages that consume it |
| --- | --- |
| `Pay_Date` | 1 fiscal trim · 2 dedupe · 7 One/Zero month bucket |
| `Pay_Period_Start` / `Pay_Period_End` | 2 dedupe · 5a/5b denominator · 7 month coverage |
| `Hours` | 4 totals · 6 eligibility |
| `Wages` | 3 wage basis · 4 totals · 6 eligibility · 11 pct-of-wages valuation |
| `Employee_ID` | 2, 4, 5, 6, 7 · test of twos |
| `Worksite_ID` | 2 · 7 matrix · 8 unit summary · 10 geographic qualification |
| `Entity_FEIN` | 2 · 8 per-entity summary · 11 entity combination |
| `Pay_Code` | 3 wage basis |
| `Hire_Date` / `Term_Date` | 5b span caps · 9 replacement-hire exclusion · WOTC hours window |
| `Employment_Type` | 6 eligibility weighting · 7 fractional headcount |
| Worksite county / FIPS | 6 wage floor basis · 10 tier and threshold |
| Worksite NAICS | 10 eligible-industry test |
| Base-year headcount | 9 net-new |
| Claim history | 9 tranche and high-water · 12 carryforward |

---

## Appendix C — glossary

| Term | Meaning |
| --- | --- |
| **One/Zero** | The statutory base calculation. Each eligible employee scores 1 or 0 for each unit for each of 12 months, depending on whether their employment span covers the month's measuring date. |
| **Average Headcount** | Sum of monthly unit totals divided by the included month count. The output of the One/Zero engine and the input to all credit valuation. |
| **Pay Period method** | Preferred denominator method. Weeks = Σ (PPE − PPS + 1) / 7 over included periods. |
| **Min-Max method** | Fallback for messy payroll. Weeks = (latest PPE − earliest PPS) / 7. |
| **Measuring date** | The day of the month on which employment is tested. GA and SC use month end; the "magical pay date" varies by state. |
| **Test of twos** | The control preventing an employee being counted at more than one unit in the same month. |
| **Frozen base year** | The fixed baseline headcount a program measures net-new against. Not a rolling prior year. |
| **High-water mark** | The running maximum Average Headcount. Determines whether a year opens a new tranche or backfills an existing one. |
| **Tranche** | One layer of net-new jobs, earning the credit for the full benefit period. Multiple tranches run concurrently. |
| **Backfill** | Dropping below the threshold one year and climbing back the next, re-qualifying without starting over. |
| **Wage basis** | Which earning codes count toward the weekly-wage test. `all_remuneration` (GA, NY) vs. `regular` base pay (NC, OH, CO, VA, TN, FL). |
| **Entity combination** | Whether related FEINs may be combined into a single taxpayer calculation. Required, permitted, or prohibited by program. |
| **Assumption set** | A versioned, immutable configuration of every contested methodology decision, recorded with each run. |

---

## Document control

| Item | Value |
| --- | --- |
| Version | 1.0 |
| Date | 2026-08-06 |
| Status | Draft for internal validation |
| Grounded against | `tax-credit-copilot` · assumption set `GDS-STEP1-2026-08-05-v5` |
| Next step | Data SE and SSP review, then issue as a data request to the partner |
