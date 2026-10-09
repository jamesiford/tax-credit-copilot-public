# One/Zero Source-to-Code Calculation Map

## Purpose

Map every Georgia Step 1 and One/Zero calculation stage to its stakeholder
source, deterministic formula, code owner, output, assumptions, and current
status. This is the engineering counterpart to the
Reference Dataset Calculation Demo.

**Status terms**

- **Implemented:** code exists and matches the cited rule as currently understood.
- **Benchmark update:** implement in the private Reference Dataset path before
  changing production behavior.
- **Review-gated:** implementation exists, but the source leaves a decision that
  requires Access/company evidence before sign-off.
- **Validation pending:** requires the partner's Access outputs or follow-up diagram to
  claim parity.

## Source hierarchy

1. July 23 Step 1 narrative: source validation through eligibility.
2. `One Zero Pay Periods.docx`: Pay Period Steps 1–7.
3. `One Zero Min Max.docx`: Min-Max Steps 1–6.
4. `GA JTC One Zero Methodology Overview.xlsx`: GA-specific period identity,
   invariants, review controls, wage example, and employment conditions.
5. `JTCHistoricalWages_Jul 2025.pdf`: annual Tax Year wage lookup.
6. Versioned Step 1 assumptions: v1 → v2 → v3 → v4 → active v5.
7. One/Zero assumptions: v1 → v2 → v3 → v4 → active v5.
8. Rule pack/statutory sources for credit benefit math.

Later evidence supersedes an interpretation only through a new versioned
assumption set; it does not silently alter historical runs.

## Shared source and normalization

| Stage | Rule/formula | Source | Code owner | Output | Status / assumptions |
| --- | --- | --- | --- | --- | --- |
| Manifest | Hash each immutable chunk; ordered logical union | Reference Dataset contract | New `TccPayrollAdapter`/manifest tool | File hashes, counts, schema, order | Benchmark update · BA-08 |
| Fiscal selection | Trim only on paycheck date for `2023-07-28` through `2024-08-02`; PPE may fall outside the window | The partner's 2026-07-30 controls; BA-01/02 v5 | Reference v5 selector | 384,418 rows / 10,236 employees | Exact control parity |
| Boundary completeness | Retain boundary controls and never synthesize rows; v5 relaxes the leading-lookback gate because paycheck-date selection retains in-window checks | BA-10 v5 | Reference boundary controls | Aggregate run control + calculation step | Report-only |
| Duplicate collapse | Group by employee, unit, FEIN, PPS, PPE, pay date, frequency; sum signed hours/wages | July 23 normalization + project decision | New benchmark normalizer; production key is narrower | Collapsed rows and before/after counts | Benchmark update · BA-04 |
| Corrections | Preserve signed corrections and zero-hour wages; retain zero-hour PPS/PPE periods in the Pay Period denominator; flag stragglers | BA-05 v5 | Reference normalizer/QC | Normalized facts and exception report | Stakeholder-selected v5 behavior |
| Wage basis | Include eligible compensation; exclude reimbursement/non-wage pay codes | July 23 Step 3; GA pack | `apply_pay_code_policy`; source lacks pay codes | Included/excluded compensation | Limited by source; visible exception |

## Common employee totals

$$
\text{TotalHours}_e = \sum_r \text{EligibleHours}_{e,r}
$$

$$
\text{TotalWages}_e = \sum_r \text{EligibleWages}_{e,r}
$$

| Source | Code | Output | Status |
| --- | --- | --- | --- |
| Pay Period Step 1; Min-Max Step 1; July 23 Step 4 | `run_pay_period_method` and `run_min_max_method` each calculate totals | Employee, TotalHours, TotalWages | Implemented twice; refactor benchmark path to one shared materialized table · GDS-20 |

Totals are customer-wide for eligibility. Unit and FEIN are deliberately ignored
until One/Zero allocation.

## Min-Max eligibility

| Step | Formula/output | Source | Code | Status |
| --- | --- | --- | --- | --- |
| Span | First included PPS; last included PPE; future target state caps with hire/term | July 23 Step 5; Min-Max Step 2 | `run_min_max_method` span block | Benchmark update: inclusive days; source has no hire/term · GDS-21 |
| Weeks | $(LastEnd - FirstStart) / 7$ | Min-Max Step 2; BA-11 v5 | `_run_min_max` exclusive-day span | Implemented v5; the source says "count the number of days between the two and divide by 7", so no `+1` |
| Averages | TotalHours/Weeks; TotalWages/Weeks | Min-Max Step 3; July 23 Step 6 | `run_min_max_method` averages | Implemented; expose rounded and full precision |
| Floors | rounded AvgHours ≥ 35 and rounded AvgWages ≥ 636 | July 23 Steps 7–8; historical wage PDF; BA-06 v5 | `_eligibility_filter` with resolved pack | Implemented for Reference Tax Year 2023 (DOL 2022, Glascock, $636/wk) |
| Output | Dates, inclusive days, weeks, averages, hours/wage/overall flags, eligible list | July 23 final deliverables | `OneZeroResult` partially exposes | Extend stage schema and trail |

## Pay Period eligibility

| Step | Formula/output | Source | Code | Status |
| --- | --- | --- | --- | --- |
| Cadence | Source 1/2/4 retained as lineage only; NOT a week multiplier | BA-03 v5 | Denominator uses actual period span | Code 4 is a 16-day second-half semi-monthly period, not four weeks |
| Included periods | Collapse employee+PPS+PPE to one denominator period; zero-hour periods ARE counted in v5; preserve all source lineage | July 23 Step 5; BA-03/BA-05 v5 | Reference v5 period grouping | Implemented |
| Weeks | $\sum_p (PPE_p - PPS_p + 1)/7$ | BA-03 v5 | `_run_pay_period` actual-span mode | Implemented v5 |
| Averages | TotalHours/Weeks; TotalWages/Weeks | Pay Period Step 4; July 23 Step 6 | `run_pay_period_method` averages | Implemented; expose rounded and full precision |
| Floors | rounded AvgHours ≥ 35 and rounded AvgWages ≥ 636 | July 23 Steps 7–8; historical wage PDF; BA-06 v5 | `_eligibility_filter` with resolved pack | Implemented for Reference Tax Year 2023 (DOL 2022, Glascock, $636/wk) |
| Output | Cadence, period count, weeks, averages, hours/wage/overall flags, eligible list | July 23 final deliverables | `OneZeroResult` partially exposes | Extend stage schema and trail |

## Min-Max One/Zero

| Step | Rule/formula | Source | Code | Status / assumptions |
| --- | --- | --- | --- | --- |
| Grain | One row per eligible employee × unit × FEIN | Min-Max Step 5; stakeholder methodology | Reference `_build_min_max` | Implemented · OZ-08/09 |
| Span | Earliest PPS through latest PPE at unit | Min-Max Step 5 | `ee_unit_span` | Implemented · OZ-02 |
| Month targets | Month end for 12 FY months | Min-Max Step 5 | `_twelve_month_ends`, `_measuring_date_for_month` | Implemented; use BA-01 window · OZ-01 |
| Month window start | First month-end a pay period actually spans, not the window's own month | OZ-01, generalised | `first_measurable_month` | Implemented. A mid-month fiscal open is a **stub**: Candle Bottle's window opens 2023-07-28 but nothing spans 2023-07-31, so starting there scored every employee 0 in Month 1 and dropped July 2024 off the end (MM average 410.13 → 375.53). OZ-01 pinned Aug–Jul by hand for the sealed run; this derives the same answer for every client |
| Month 12 | If last PPE is in Month 12 and day >15, target last PPE | Min-Max Step 5 | `_adjusted_target_for_month` | Implemented · OZ-04. **Load-bearing:** nothing spans 2024-07-31 either (latest PPE 2024-07-26), so without this rule Month 12 would also read 0. A client whose final period ends on or before the 15th would silently read 0 |
| Unreachable months | Name the month positions no pay period spans | Derived from the above | `unreachable_months` | Implemented. Persisted on `unit_month_summary`, served per year by `GET /api/v2/clients/{id}/units` and hatched in the grid, so a structurally-empty month is not read as a location that emptied out |
| Year completeness | A year is complete when it fills every REACHABLE month, not all twelve | Ours, not the partner's | `tools/unit_trend.infer_base_year` | Implemented. A calendar-year client has no December measuring date, so eleven months is its complete year. Judging against twelve rejected it as a base year and pushed the base a year later — the most leveraged input in the model. **The divisor stays 12**; only the completeness test changed |
| Month-12 cliff | `day > 15` decides whether an unreachable final month scores at all | OZ-04 | `_adjusted_target_for_month` | **OPEN — questions 23-25 in REFERENCE-DATASET.md.** On Cascade, TY2020 and TY2024 end 12-15 and score 0; TY2021/22/23/25 end 12-16 and score ~25. A one-day calendar shift moves the annual average ~8% and therefore the credit |
| Cell | $1$ when span covers target; otherwise $0$ | Min-Max Step 5 | matrix loop | Implemented using PPS/PPE · OZ-02 |
| Test of twos | Employee ≤1 count per month | Min-Max Step 5 | flags + `_dedupe_one_per_month` | Flag exists; current last-row tie-break must become explicit OZ-06 ordering |
| Trail | One decision per employee-unit-month plus assumptions/exceptions | Provenance standard | Aggregate trail only today | Extend for private benchmark drill |

## Pay Period One/Zero

| Step | Rule/formula | Source | Code | Status / assumptions |
| --- | --- | --- | --- | --- |
| Major periods | Use reviewed company pay-cycle groups or practitioner-identified material payroll dates | Pay Period Step 2; GA methodology workbook rows 49–51 | `_major_periods` is diagnostic only | Not used to filter v5 denominator; remains a sign-off gate · OZ-05 v5 |
| Grain | One row per eligible employee × major period × unit × FEIN | Pay Period Step 6 | Reference `_build_pay_period` | Implemented · OZ-08/09 |
| Cell | $1$ when PPS ≤ target ≤ PPE; otherwise $0$ | Pay Period Step 6 examples | matrix loop | Implemented · OZ-03; source wording ambiguity visible |
| Month 12 | Same target override | Pay Period Step 6 | `_adjusted_target_for_month` | Implemented · OZ-04 |
| Test of twos | Employee ≤1 count per month | Pay Period Step 6 | `_dedupe_one_per_month` | Implemented hidden tie-break; expose/replace with OZ-06 ordering |
| Trail | One decision per employee-period-unit-month | Provenance standard | Aggregate trail only today | Extend for private benchmark drill |

## Unit summary and Average Headcount

$$
\text{UnitMonthTotal}_{u,m} = \sum_e \text{OneZero}_{e,u,m}
$$

$$
\text{AverageHeadcount}_u =
\frac{\sum_m \text{UnitMonthTotal}_{u,m}}{\text{IncludedMonthCount}}
$$

| Source | Code | Required outputs | Status |
| --- | --- | --- | --- |
| Pay Period Step 7; Min-Max Step 6; July 23 partial-year discussion | `_build_summary` | Month totals, total, denominator, unrounded average, nearest-whole half-up source view, two-decimal application view | Current code divides by 12 and returns two decimals; extend outputs · OZ-07 |

## Method reconciliation

The two methods need not produce the same eligible list or Average Headcount.
Parity means each method matches the partner's implementation of that method.

`reconcile_methods` currently shows:

- unit/month differences;
- eligibility disagreements;
- weeks-worked gaps;
- Min-Max ≥ Pay Period invariant violations.

Reference reconciliation must additionally identify the first divergent stage and
provide a dual-method employee drill.

The GA methodology workbook adds two non-repairing controls:

- Pay Period denominator weeks must not exceed Min-Max weeks; report every
  violation and every employee above the configured Pay Period week ceiling (53 in v5, per One Zero Pay Periods.docx Step 3).
- A methodology result cannot be signed off while major-cycle groups or
  test-of-twos dispositions are inferred without reviewed evidence.

## Credit benefit math — separate cited stage

One/Zero produces Average Headcount; it does not by itself determine credit
value. `apply_one_zero_state_credit` currently calculates:

$$
\text{NetNew} = \max(0, CurrentAverage - ComparisonAverage)
$$

$$
\text{QualifyingJobs} = \max(0, NetNew - MinimumJobs)
$$

$$
\text{AnnualCredit} = QualifyingJobs \times PerJobValue
$$

This stage must independently show its rule-pack version, statutory citation,
base/comparison period, threshold interpretation, value, benefit period, and any
negotiated override. Reference One/Zero parity does not automatically validate these
credit-dollar rules.

## Known source-data defects

1. **November 2023 semi-monthly cycle is truncated.** Every other month's
   second-half semi-monthly period runs to month end (`2023-10-16..2023-10-31`,
   `2023-12-16..2023-12-31`), but November's is `2023-11-16..2023-11-24`. No
   semi-monthly period covers 2023-11-30, so semi-monthly employees score 0 in
   Month 4 of the Pay Period matrix. This depresses our Pay Period M4 to 311
   against a ~520 neighbour-month baseline. Min-Max is unaffected because it uses
   a continuous span. Raise with the partner before any M4 sign-off.
2. **July 2024 has no second-half semi-monthly period at all**, and the June
   entry (`2024-06-29..2024-07-12`) straddles the boundary.
3. **`PayFrequency` is mislabelled.** `One Zero Pay Periods.docx` defines
   `Frequency = Weeks in Pay Period`, but code 4 is always a 16-day 16th-to-31st
   period and code 2 is predominantly a 15-day 1st-to-15th period. Applying the
   codes as week multipliers yields 447 eligible against the partner's reported 659.

## Implementation status

1. Build the private TCC adapter and shared Step 1 stages.
2. V5 implements exclusive-day Min-Max and actual-span Pay Period denominators
  in the benchmark path.
3. Extend One/Zero matrix keys and trails with FEIN and stable source lineage.
4. Replace hidden test-of-twos correction with flag + explicit disposition.
5. Emit all summary precision/denominator views.
6. Extend `TrailRecorder` or wrap it to satisfy the Calculation Provenance
   Standard without breaking existing consumers.
7. Add source-step, formula, assumption, exception, and reproducibility tests.
8. V5 employee+PPS+PPE denominator identity and invariant reporting are implemented.
9. Reference v5 uses Tax Year 2023 `$636`; production rule packs also retain the
   2024 `$686` and 2025 `$680` annual overrides.
10. V5 supersedes v4 boundary selection with paycheck-date-only trim while
    retaining non-repairing boundary controls.
