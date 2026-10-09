# Reference Dataset Contract and Clarification Log

## Purpose

This document records what is known about the four private CSV files supplied
for an apples-to-apples comparison with the partner's Access calculation.
It intentionally contains only aggregate, de-identified observations.

Raw files stay local under `backend/data/payroll/`, are ignored by Git, and must
not be uploaded, committed, deployed, or included in model prompts or telemetry.

## Latest source package — July 23 follow-up

The partner's private follow-up contains:

- **Georgia JTC Step 1 Avg Wages and Hours Narrative**;
- a one-page high-level flow diagram for the same narrative;
- the existing **GA JTC One Zero Methodology Overview** workbook, now reviewed
    as additional GA-specific evidence.

The narrative and diagram define the first benchmark milestone from raw payroll
through separate Min-Max and Pay Period employee eligibility lists. The source
files now live as read-only inputs under `stakeholder-docs/`; the meeting
transcript is intentionally not retained in this repository.

### Confirmed benchmark sequence

1. Validate required source fields and emit exceptions.
2. Resolve the customer's fiscal-year begin/end dates.
3. Select fiscal-year payroll records.
4. Normalize hours, wages, duplicate activity, reversals, and pay codes.
5. Calculate one common total-hours/total-wages row per employee across units and
     FEINs.
6. Calculate Min-Max and Pay Period denominators independently.
7. Calculate average weekly hours and wages independently.
8. Apply the hours and wage tests independently and produce two eligible lists.
9. Compare the lists exactly and audit mismatches one employee at a time.
10. Only after eligibility parity, apply unit and FEIN to build One/Zero.

### The partner-authored Step 1 rules

- Required target-state employee fields are employee ID, hire date, termination
    date when applicable, and pay cadence. The supplied benchmark intentionally
    omits hire/termination dates; the partner confirmed they are not a blocker for this
    first comparison.
- Required target-state payroll fields are fiscal-year begin/end, PPS, PPE, pay
    date, hours, earnings, and pay code. Fiscal dates are run configuration; pay
    codes are not present in the supplied TCC source, so full wage-code validation
    remains a future-source gap.
- Include records when the paycheck date falls inside the approved analysis
    window. Do not exclude a row because its PPE falls outside that window.
- Normalize overtime hours to actual hours, remove confirmed duplicates, handle
    adjustments/reversals according to project methodology, include eligible
    compensation, and exclude reimbursements/non-wage pay codes.
- Common employee totals are computed before location/legal-entity allocation.
- Min-Max weeks are `(Last PPE - First PPS) / 7` across all employee rows,
    including zero-hour periods. Hire and termination dates are unavailable and
    remain a visible source limitation.
- Pay Period weeks are the sum of each distinct PPS/PPE period's inclusive
    actual span: `sum((PPE - PPS + 1) / 7)`. `PayFrequency` is lineage only.
- The hours floor is `35` average hours per week.
- The supplied weekly-wage schedule is: 2025 `$680`, 2024 `$686`, 2023 `$636`,
    2022 `$602`, 2021 `$589`, 2020 `$541`. `JTCHistoricalWages_Jul 2025.pdf`
    defines the lookup by its **Tax Year** column. The partner's active run is Tax Year
    2023, so the active floor is `$636`.
- Each method emits hours-pass, wage-pass, and overall-eligible `1/0` flags.
- Every mismatch must support a dual-method, single-employee payroll-history
    audit.

## Approved benchmark assumptions — 2026-07-29

These are project decisions approved for the first implementation. They are not
represented as partner-confirmed Access behavior unless also stated in the
partner-authored rules above. The Access outputs remain the authority for detecting
and resolving any difference.

Active machine-readable set:
GDS-STEP1-2026-08-05-v5. The table below is
its human-readable explanation; the benchmark runner must record the assumption
set ID and SHA-256 rather than reconstructing these values from prose.

| ID | Approved assumption | Implementation consequence |
| --- | --- | --- |
| **BA-01** | Tax Year 2023 runs from `2023-07-28` through `2024-08-02` | Use the partner's confirmed fiscal window |
| **BA-02** | Trim on paycheck date only | Keep every row paid in-window regardless of PPE; reproduce the partner's `384,418` records / `10,236` employees |
| **BA-03** | Pay Period denominator uses each distinct PPS/PPE period's actual inclusive span | Sum `(PPE - PPS + 1) / 7`; PayFrequency is lineage only, not a multiplier |
| **BA-04** | Duplicate key is employee + unit + FEIN + PPS + PPE + paycheck date + pay frequency | Sum signed hours and wages within the key; retain different unit/FEIN/pay-date/frequency rows separately; job title is not a key |
| **BA-05** | Preserve signed corrections and retain zero-hour PPS/PPE periods in the Pay Period denominator | Include zero-hour wages and periods; flag rather than silently remove |
| **BA-06** | Tax Year 2023 → DOL Report Year 2022 → Glascock → `$636` | Round weekly averages half-up to two decimals, then apply `35` hours / `$636` |
| **BA-07** | The partner will provide Step 1 CSV/XLSX outputs keyed by unchanged employee ID | Build local importers for common totals and both methods' denominator, average, flag, eligible-list, settings, and exclusion outputs; authoritative parity waits for them |
| **BA-08** | `One.csv` → `Two.csv` → `Three.csv` → `Four.csv` is one complete ordered logical export | Remove only fully blank padded rows, preserve source-file/row lineage, apply no cross-file dedupe, and do not create an authoritative consolidated CSV |
| **BA-09** | Pay Period weeks must not exceed Min-Max or 53 without review | Report violations, retain the 1.5-week review threshold, and never auto-repair |
| **BA-10** | Report source-boundary completeness without synthesizing rows | Paycheck-date-only trim relaxes the leading-lookback gate; never force 52 weeks |
| **BA-11** | Min-Max uses exclusive days over all employee rows | Calculate `(LastEnd - FirstStart) / 7`, including zero-hour periods |

### V5 paycheck-date decision

The partner's control totals are reproduced only when selection uses paycheck date
without an additional PPE boundary. V5 therefore keeps every row paid from
`2023-07-28` through `2024-08-02`, including a row whose PPE falls outside the
window. Any later change requires a superseding assumption set.

### Historical fiscal-boundary v4 finding — 2026-07-30

This finding explains the superseded v4 decision. V5 replaced its PPE boundary
with the stakeholder-reconciled paycheck-date-only rule above.

The dominant 50-week Min-Max result is a source-boundary issue, not evidence
that a full fiscal year contains only 50 weeks:

- `147` eligible Min-Max employees round to 50 weeks; `144` share the span
    `2023-08-05` through `2024-07-19`.
- The current source contains **zero** valid PPS rows before `2023-08-01`, zero
    prior-FY PPEs paid inside FY2024, and zero periods crossing the FY start.
- `4,080` employees have a PPE on/before `2024-07-31` paid after FY end. Those
    paychecks remain excluded under cash-basis selection.
- Including the trailing July PPE paid in August would move the dominant span to
    about 51 weeks, not 52, and would violate the pay-date boundary.
- For the observed weekly cadence, the likely missing leading records are the
    late-July PPE paid in early August and the period crossing August 1. If both
    are supplied and paid in FY2024, the dominant Min-Max span can reach 52 weeks
    while the post-FY paycheck stays excluded.
- Pay Period weeks remain independent: many of the same employees have 48
    positive-hour periods because zero-hour periods and actual gaps do not count.

V4 therefore changes leading-boundary selection to include records paid in the
fiscal year even when PPE is before the FY start, while retaining source lineage
and end-boundary exclusions. Because those records are absent from the supplied
files, v4 reports `MISSING_LEADING_LOOKBACK`; it does not generate them or force
any denominator to 52.

### Assumption change control

- V1-v4 are immutable recorded history. V5 is the active set.
- If Access evidence disproves an assumption, create a new versioned JSON file
    such as `reference-dataset-assumptions.v2.json`; do not edit the historical set.
- Mark the old set superseded in the new set and record the old/new IDs, changed
    BA IDs, evidence, reviewer, date, and first divergent stage.
- Every local run/report records assumption-set ID/hash, source-manifest hash,
    code commit, and timestamp so the result can always be reproduced.
- A discrepancy changes an assumption only after classification; it does not
    silently mutate production or benchmark configuration.

## One/Zero implementation basis and active v5

The original `One Zero Min Max.docx` Steps 5–6 and
`One Zero Pay Periods.docx` Steps 6–7 contain enough information to implement a
transparent v1. The partner's forthcoming diagrams and Access outputs are validation
evidence, not an implementation prerequisite.

Active interpretation set:
GDS-ONEZERO-2026-08-05-v5. V1-v4 remain
immutable history. Every run displays OZ assumption IDs and preserves the
set/hash plus both stakeholder evidence hashes.
The [One/Zero Source-to-Code Calculation Map](ONEZERO-CALCULATION-MAP.md) is the
implementation checklist tying each source step to formula, code, output, status,
and assumption.

| Method stage | Source rule | v5 output |
| --- | --- | --- |
| Min-Max matrix | One eligible employee × unit, earliest PPS through latest PPE; evaluate 12 monthly targets; Month-12 override; no employee >1 per month | Employee × unit × FEIN span with 12 decisions and citations |
| Pay Period matrix | One eligible employee × major pay period × unit; evaluate target coverage; Month-12 override; no employee >1 per month | Employee × major-period × unit × FEIN row with 12 decisions and citations |
| Summary | Sum monthly counts by unit, total them, divide by included months, and show rounded view | Unit-month totals, denominator, unrounded average, source-rounded average, and application precision |

### Ambiguities that v1 must show, not hide

- The documents alternate between PPS/PPE ranges and first/last paycheck-date
    wording. OZ-02/OZ-03 state the v5 interpretation.
- Pay Period Step 6 says `PaycheckDate <= target AND PaycheckDate >= target`,
    which collapses to equality and conflicts with its period-range examples.
- The source requires major periods but does not specify an exact classifier.
    OZ-05 keeps the current heuristic diagnostic-only pending reviewed cycles.
- The source forbids duplicate monthly counts but does not specify which unit
    wins. OZ-06 keeps a reproducible provisional view but requires review.
- The source requests nearest-whole summary rounding while the application also
    supports fractional part-time counts. OZ-07 emits unrounded, source-rounded,
    and application-precision values separately.
- Partial-year month denominators discussed on July 23 are not fully specified
    in the original docs. The full-year benchmark uses 12 and flags any future
    partial-year case.

All of these decisions must appear in the calculation walk. If the partner's follow-up
disproves one, create a superseding One/Zero assumption set and rerun; do not
rewrite historical sets.

## GA methodology workbook findings — 2026-07-29

`GA JTC One Zero Methodology Overview.xlsx` is a stakeholder source
created by Liz Piascik and last modified by the partner on 2025-04-21. Its
SHA-256 is
`C2F8CF527AF8423F88105D3EE77B30F938D7CFCE4E5D532A6C851F60701D310A`.

The workbook confirms or adds the following requirements:

- Min-Max assigns `1` when `Min PPS <= monthly cutoff <= Max PPE`.
- Pay Period records sharing employee/PPS/PPE collapse to one denominator
    period; pay date, unit, FEIN, and pay lines remain available as lineage.
- Pay Period weeks must never exceed Min-Max weeks and any value over 52 weeks
    requires review; violations are surfaced and never silently capped.
- Zero-hour periods are usually bonuses and do not create denominator periods.
- Test-of-twos duplicates require a review and clearing workflow. The workbook
    does not define which unit wins, so deterministic auto-disposition remains
    an explicit proposed assumption.
- Major pay cycles come from company-provided pay-cycle groups or practitioner
    inspection of material payroll dates. The workbook does not provide an
    automatic classifier; the current median-participation heuristic cannot be
    treated as validated methodology.
- The workbook's 2024 example uses `35` hours and `$686` weekly wages.
    `JTCHistoricalWages_Jul 2025.pdf` confirms that Tax Year 2024 maps to this
    value, superseding BA-06 v2's fiscal-begin-year interpretation.
- Seasonal full-time and staffing employees can qualify when they satisfy the
    full-time, wage, industry, and program conditions. The Reference source lacks
    employment type and staffing indicators, so this remains a visible source
    limitation rather than an inferred employee classification.
- GA JTC industry and retail/county restrictions remain relevant. Confirming the
    client is Georgia-based establishes program scope, not final credit dollars;
    county/tier, industry, base/comparison period, and return-level entity inputs
    are still required.

The workbook's hard-coded examples are not benchmark outputs. September and
November cutoff cells decode as 1931 dates, the December cutoff is December 27,
and sample employee spans do not align with the displayed cutoff year. Those
cells remain source defects and must not seed expected results.

Full-source diagnostics under v1 found 423 employees with Pay Period weeks above
Min-Max, including 22 of 340 employees eligible under both methods (12 above the
existing 1.5-week review tolerance), and 173 employees above 52 Pay Period
weeks. Same-PPS/PPE collapse removes only six violations, proving that pay-cycle
classification remains a separate unresolved input.

V5 is active under `GDS-STEP1-2026-08-05-v5` and
`GDS-ONEZERO-2026-08-05-v5`. It reproduces the partner's Step 1 controls exactly:
`384,418` selected rows, `4,950,777.43` hours, `$82,533,629.87` wages, and
`10,236` employees. Eligibility is close but not signed off: Min-Max `525` vs
the partner's `511`; Pay Period `664` vs the partner's `659`; `513` qualify under both.
One/Zero contains `811` Min-Max rows (`31` overlaps) and `19,217` Pay Period
rows (`281` overlaps). The remaining blockers are employee-level expected lists,
the missing November/July semi-monthly source runs, the exclusive/inclusive
one-day artifact, and the partner's anomalous M4 summary outputs. See
the partner parity runbook.

## Current conclusion

The four files are **four chunks of one employer-group payroll export**, not four
companies:

- thousands of employee IDs recur across files;
- the first three files contain the same 47 units and one FEIN;
- the fourth contains those same units plus 54 additional units and a second
  FEIN;
- the date windows progress across one FY2024-scale period;
- no exact source row is shared across chunks.

The employer identity is intentionally unspecified. Do not map this source to
MeridianCore or create three additional fictional tenants. Treat it as the
private benchmark scope `JOHN_REFERENCE_FY2024` until the partner supplies an approved
name or confirms a different structure.

## Aggregate makeup

| Measure | Observed value |
| --- | ---: |
| Physical rows | 488,968 |
| Fully blank padded rows | 104,535 |
| Usable rows | 384,433 |
| Distinct employees | 10,236 |
| Distinct units | 101 |
| Distinct FEINs | 2 |
| Earliest pay-period start | 2023-08-01 |
| Latest pay-period end | 2024-07-31 |
| Earliest paycheck date | 2023-08-03 |
| Latest paycheck date | 2024-08-09 |

### Chunk profile

| File | Usable rows | Padded rows | Employees | Units | FEINs | Apparent role |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `One.csv` | 122,242 | 0 | 6,644 | 47 | 1 | first export chunk |
| `Two.csv` | 93,150 | 29,092 | 5,976 | 47 | 1 | continuation chunk |
| `Three.csv` | 100,158 | 22,084 | 5,856 | 47 | 1 | continuation chunk |
| `Four.csv` | 68,883 | 53,359 | 5,583 | 101 | 2 | final chunk; adds units and second FEIN |

`One.csv` through `Four.csv` are working filenames, not company names.

## Source schema

| Source column | Intended meaning | Proposed benchmark mapping | Notes |
| --- | --- | --- | --- |
| `TCCEmployeeId` | Employee identifier | `Employee_ID` | Treat as confidential even if tokenized |
| `Tax Year` | Source-assigned tax year | `Source_Tax_Year` | Do not discard in favor of derived year |
| `JobTitle` | Job title | `Job_Title` | Informational; may help flag retail/ineligible roles |
| `TCCUnitId` | Employer location/unit | `Worksite_ID` | Numeric and not state-prefixed |
| `PayPeriodStart` | Pay-period start | `Pay_Period_Start` | Normalize to ISO date in adapter |
| `PayPeriodEnd` | Pay-period end | `Pay_Period_End` | Normalize to ISO date in adapter |
| `PaycheckDate` | Pay date | `Pay_Date` | Candidate fiscal anchor; confirmation required |
| `PayFrequency` | Weeks/cycle code | `Source_Pay_Frequency` | Values observed include 1, 2, and 4 |
| `FEIN` | Legal entity identifier | `Entity_FEIN` | Two values; relationship unconfirmed |
| `Hours` | Hours for source line | `Hours_Worked` | Includes zero and negative corrections |
| `Wages` | Wages for source line | `Gross_Wages` | Includes negative corrections |

The source does **not** contain hire date, termination date, state, county,
address, industry, investment, health-benefit, employment-type, pay-code,
position, or seating-date fields. Hire/term and pay-code absence are documented
limitations, not reasons to reject the first eligibility benchmark.

## Recorded implementation decisions

- The four CSVs remain the immutable source set. They are read as an ordered,
    logical union; no hand-built consolidated CSV becomes authoritative.
- Every normalized row retains benchmark-only lineage: source file, source row,
    source tax year, raw pay frequency, unit, and FEIN.
- A generated local columnar/cache artifact may accelerate repeat runs, but it is
    derived from source/config hashes, disposable, ignored, and never deployed.
- The TCC source is a separate private benchmark input. It does not replace the
    MeridianCore CSV or Fabric OneLake production source.
- We will expose existing calculation stages before changing production
    behavior. The July 23 rules are implemented first in the benchmark path;
    current production fiscal, collapse, zero-hour, major-period, weeks-worked,
    monthly allocation, tie-break, rounding, and threshold choices remain
    hypotheses until reconciled against Access.
- The first comparison is local. A UI is optional after parity and may show only
    aggregate status and de-identified discrepancy summaries.

## Work that can proceed now

1. Source manifest and deterministic four-file load order.
2. TCC-to-engine field adapter with strict validation and source lineage.
3. Aggregate QC/profile report with no identifiers in logs or committed output.
4. Step 1 stage schemas for common totals plus separate Min-Max and Pay Period
    denominators, averages, eligibility flags, and eligible lists.
5. Local runner, dual-method employee drill, cache, benchmark-import interfaces,
    and stage comparator tested with small de-identified fixtures.

These tasks do not require assumptions about company identity, state, county, or
credit eligibility. They must not silently discard or rewrite source records.

## Observed data-quality conditions

These are controls to reconcile, not defects to repair preemptively:

| Condition | Count | Required treatment |
| --- | ---: | --- |
| Fully blank padded rows | 104,535 | Exclude and report |
| Zero-hour rows | 129,619 | Preserve until the partner confirms exclusion/collapse behavior |
| Negative-wage rows | 417 | Preserve as corrections/reversals |
| Negative-hour rows | 247 | Preserve as corrections/reversals |
| Employees with a negative correction | 220 | Include in focused parity review |
| Employee/unit/period groups with repeated lines | 126,382 | Collapse only with confirmed key and aggregation rules |
| Groups with more than one paycheck date | 147 | Paycheck date may need to be part of the collapse key |
| Paycheck date before pay-period end | 2,981 | Confirm source semantics; do not rewrite |
| July 2024 periods paid in August 2024 | 7,769 | Confirm FY2024 inclusion rule |

All usable rows have nonblank employee, unit, FEIN, and date fields after padded
rows are removed.

## Jurisdiction applicability

### Georgia

The source has the fields needed to reproduce the partner's core GA One/Zero headcount
method: employee, unit, FEIN, pay-period boundaries, pay date, frequency, hours,
and wages. Although the source rows contain `Tax Year=2024`, the partner's active run
controls identify Tax Year 2023. V5 records that resolved run configuration and
uses the historical table's `$636` floor.

It does **not** prove that any unit is in Georgia and does not identify county
tier. Before calculating GA credit dollars, obtain either:

1. The partner's confirmation that the complete export is GA-only and the Access output
   is a GA Base Calculation; or
2. an approved unit-to-state/county registry.

### Tennessee

This source alone is not sufficient for a Tennessee statutory determination.
In addition to confirmed Tennessee location, the program needs evidence for
capital investment, minimum health care, permanent/part-time/seasonal status,
industry/site eligibility, and potentially position/seating continuity. The
current TN rule pack also retains a prototype weekly-wage placeholder and has
not activated statutory part-time weighting.

Use this source for Tennessee only if the partner provides the missing program inputs
and confirms that the units belong to the Tennessee project scope.

## Working assumptions

| ID | Assumption | Status |
| --- | --- | --- |
| **A-01** | The four files represent one benchmark customer and the exact dataset the partner will run | Confirmed in July 23 discussion; chunk completeness/order remains open |
| **A-02** | Both FEINs belong to that employer group | Plausible; unconfirmed |
| **A-03** | Active run is Tax Year 2023 with a `2023-07-28` through `2024-08-02` paycheck window | Stakeholder-reconciled in BA-01/02 v5 |
| **A-04** | Fully blank rows are export padding | Approved project assumption BA-08 |
| **A-05** | Negative values are usually corrections/reversals | Approved treatment in BA-05; validate against Access outputs |
| **A-06** | Duplicate rows use the audit-preserving BA-04 key | Approved project assumption; validate against Access outputs |
| **A-07** | The dataset is intended for a Georgia eligibility/Base Calculation comparison | Confirmed in July 23 method discussion; geography is absent from the schema |
| **A-08** | The source is an input only; the partner's expected output is still separate | Confirmed by current folder contents |

## Required from the partner

Step 1 implementation proceeds under BA-01 through BA-11. The table below
distinguishes approved project assumptions from remaining external dependencies.

| ID | Decision or artifact | Status | Remaining purpose |
| --- | --- | --- | --- |
| **J-01** | Four chunks are one complete ordered export | Assumed by BA-08 | Revisit only if the partner's source manifest differs |
| **J-02** | Return-level treatment of two FEINs | Deferred | Required for One/Zero/credit, not Step 1 eligibility |
| **J-03** | Tax Year 2023 uses `2023-07-28` through `2024-08-02` | Reconciled by BA-01 v5 | Confirm directly with the partner |
| **J-04** | Trim on paycheck date only; PPE may fall outside the window | Exact control match under BA-02 v5 | Confirm directly with the partner |
| **J-05** | Duplicate key and signed aggregation | Assumed by BA-04 | Reconcile employee totals |
| **J-06** | Zero-hour, reversal, overtime-hour, and straggler treatment | Assumed by BA-05 | Reconcile controls/totals; classify manual exceptions |
| **J-07** | Pay Period uses actual inclusive spans; frequency is lineage only | BA-03 v5; output is within five employees | Confirm exact Access denominator |
| **J-08** | Tax Year 2023 `$636` floor and half-up two-decimal tested averages | Historical wage source resolved; v5 implemented | Confirm `$635.99` is only a query-rounding artifact |
| **J-09** | Access Step 1 outputs keyed by employee ID | Outstanding | Required for authoritative reconciliation/sign-off |
| **J-10** | Manual exclusions, overrides, and post-processing list | Outstanding | Required to disposition mismatches |

### Required Access output package

For the same four source files and run configuration, request CSV or XLSX exports
of every table the partner can provide:

1. source/preprocessing control totals and excluded-row counts;
2. common total hours and wages by employee;
3. Min-Max first/last dates, span days, weeks, average weekly hours/wages,
    test flags, and eligible list;
4. Pay Period cadence, included-period count, weeks, average weekly hours/wages,
    test flags, and eligible list;
5. final Step 1 run settings, wage-table row, rounding rules, tolerances, manual
    exclusions, and overrides.

The employee × unit/legal-entity × month matrices and unit summaries are a
second output package after the partner completes the One/Zero diagrams.

The exports should retain stable employee and unit keys so they can be joined
locally. They remain private and receive the same handling as the source CSVs.

### Needed later for credit dollars, not core Base Calculation parity

- confirmation that the run is Georgia and which units/counties are in scope;
- unit-to-state/county designations for the applicable year;
- legal-entity combination treatment under the program;
- base/prior-year headcount and statutory threshold treatment;
- verified per-job amount and filing-year rule version.

These items should not delay adapter development or the employee/unit/month
comparison. They do block a defensible GA credit amount. Tennessee requires
additional investment, health-plan, employment-type, industry, and position data
that is absent from this source.

## Questions for the partner

The detailed interview checklist below expands J-01 through J-10 and should be
used to record the partner's answers verbatim.

### Dataset identity and scope

1. Are `One.csv` through `Four.csv` four pages/chunks of one export?
2. Is the export complete, and in what order should the files be loaded?
3. Do the two FEINs belong to one controlled employer group? Should they be
   combined, shown separately, or both?
4. Are all 101 units in the same state and credit program?
5. Is this the client/fiscal-year example the partner calculated in Access? What neutral
   benchmark label may we use internally?

### Fiscal and row-selection rules

6. What exact 12-month window does `Tax Year=2024` represent?
7. Does source `Tax Year` control inclusion, or is inclusion determined by
   paycheck date?
8. Should the 7,769 July periods paid in August remain in FY2024?
9. How should the 2,981 rows whose paycheck date precedes pay-period end be
   interpreted?
10. Are fully blank rows known export padding?

### Collapse and correction rules

11. Is the collapse key employee + unit + pay-period start + pay-period end +
    paycheck date?
12. If the same key appears multiple times, are hours and wages always summed?
13. How does Access treat zero-hour wage rows: drop first, net into wages, or
    retain for another purpose?
14. How does Access treat negative hours and wages?
15. Are any source lines already collapsed before these CSVs were produced?

### Method configuration

16. Confirm both method outputs will include stable employee keys, denominator,
    average weekly hours/wages, and three eligibility flags.
17. Confirm source frequency-code/cycle-group treatment and the rounding
    precision applied after selecting the resolved Tax Year 2024 `$686` floor.
18. Is the Month-12 special rule active for this run?
19. How are employees crossing units or FEINs handled when one month could be
    counted more than once?
20. What tolerance, if any, is acceptable at employee, unit-month, and final
    Average Headcount levels?

### Months no pay period reaches

Added 2 September 2026. This extends the registered `november_zero_column`
open question with evidence from a second client, and it is the highest-value
question on this list because it moves the credit.

A month scores 1 only when a pay period spans its measuring date. For a
calendar-year client, no period spans 31 December, so the Month-12 special rule
is the only thing producing a December figure — and it applies only when the
employee's last period end falls after the 15th. That is a cliff. On the
Cascade Retail Partners fixture:

| Tax year | Last December period end | After the 15th? | Month 12 |
| --- | --- | --- | --- |
| 2020 | 2020-12-15 | no | **0** |
| 2021 | 2021-12-16 | yes | 25 |
| 2022 | 2022-12-16 | yes | 25 |
| 2023 | 2023-12-16 | yes | 26 |
| 2024 | 2024-12-15 | no | **0** |
| 2025 | 2025-12-16 | yes | 25 |

**A one-day difference in the pay calendar moves a location's annual average by
roughly 8%**, which moves net-new jobs and therefore the credit. Two of six
years are affected on this client.

23. When no pay period spans a month's measuring date, should the target fall
    back to the latest period end in that month? Should that be one date for
    the whole month, or each employee's own last period end as the Month-12
    rule does today?
24. Your Min-Max summary reports 0 for Month 4 across all 101 units while the
    average column still divides by 12. Is the zero month intended to stay in
    the denominator? We divide by 12 to match you.
25. Does a year whose final month has no measuring date still count as a
    complete year for the purpose of setting a base year?

### Expected output package

26. Can the partner export the Step 1 Access tables listed in the Required Access output
    package now, then the employee-unit-month and summary tables with the
    forthcoming One/Zero package?
27. What stable keys and formats should we use to join those outputs back to the
    source?

## Required benchmark package

The source CSVs alone are not a reference benchmark. A complete package consists of:

1. source manifest and hashes;
2. confirmed run configuration;
3. the partner's Access intermediate/final outputs;
4. documented manual exclusions or overrides;
5. reconciliation report and discrepancy dispositions;
6. reviewer sign-off tied to source/config hashes.

## Security and handling

- Keep raw source and direct Access exports outside Git.
- Treat employee IDs and FEINs as confidential identifiers.
- Do not use this data in Foundry prompts, chat, screenshots, telemetry, CI, or
  the public demo deployment.
- Generate only aggregate or de-identified fixtures for committed tests.
- Do not infer or publish the employer identity from job titles, units, FEINs,
  meeting transcripts, or external research.
- Keep stakeholder methodology documents read-only under `stakeholder-docs/`.
- Do not retain meeting transcripts or temporary transcript extracts in Git.

## Related documents

- [One/Zero source-to-code calculation map](ONEZERO-CALCULATION-MAP.md)
- [Calculation provenance standard](../architecture/CALCULATION-PROVENANCE.md)
- [Engine convergence](../architecture/ENGINE-CONVERGENCE.md)
