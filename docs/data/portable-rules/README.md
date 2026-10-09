# Portable business rules

**For** Sam Hameed · **From** James Ford · **Date** 2026-09-04
**Generated from** commit `d1beefe`

The deterministic rules that turn raw partner payroll into a Georgia JTC
headcount, extracted from the certified engine as pure Python functions with no
dependencies beyond the standard library.

## Files

| File | What it is |
| --- | --- |
| `flex_rules.py` | The rules. Stdlib only. Drop it in a notebook and import it. |
| `crosscheck.py` | Proof it matches the engine. Run it after any change to either side. |

## Start here

```bash
python flex_rules.py
```

Runs sixteen assertions covering every rule, and prints pass/fail per rule. No
data or configuration needed. If this passes, the module is intact.

```bash
cd backend && ../.venv/Scripts/python.exe ../docs/data/portable-rules/crosscheck.py
```

Runs both implementations over the same rows and reports any disagreement.
Current result:

```
fixture rows (GA, TY2025): 3,154
employees: engine 107  portable 107
min_max weeks compared: 107  mismatched: 0
min_max eligible:    engine 77  portable 77
pay_period eligible: engine 72  portable 72

AGREES - portable rules match the engine on every compared value
```

It uses the public fixture in the repo, not the private reference dataset, so it
runs on any clone.

## Rules, in pipeline order

| Stage | Rule | Function |
| --- | --- | --- |
| Bronze -> Silver | BA-01 fiscal window from config | `fiscal_window()` |
| | BA-02 select on paycheck date only | `select_rows()` |
| | BA-04 / BA-03 collapse to one period row | `collapse_duplicates()` |
| | BA-12 exclude periods under 7 days | `is_real_pay_period()` |
| | | `short_period_exclusions()` |
| Silver -> Gold | BA-05 sum the numerator, keep negatives | `employee_totals()` |
| | BA-11 Min-Max weeks, exclusive | `min_max_weeks()` |
| | BA-03 Pay Period weeks, inclusive | `period_weeks()` |
| | BA-06 eligibility on rounded averages | `test_eligibility()` |
| | OZ-01 twelve month-end targets | `month_end_targets()` |
| | OZ-04 Month 12 exception | `measuring_date()` |
| | OZ-02 score a month | `onezero_row()` |
| | OZ-07 average headcount | `unit_summary()` |
| | year completeness (new 2 Sep) | `year_is_complete()` |

Full narrative for each, with the stakeholder quote behind it, is in
`CALCULATION-RULES-V7.md`. Where that document and this code disagree, the
document is right.

## The five that will bite you

These are the ones where a reasonable implementation quietly differs. Each has
a self-check assertion.

**1. BA-02 selects on paycheck date, not period end.** The intuitive filter is
period end and it is wrong. A period starting before the window but paid inside
it is IN; a period ending inside the window but paid after it is OUT.

**2. BA-11 counts days exclusively.** `(last_ppe - first_pps).days`, no `+ 1`.
A full-year weekly employee is 51.86 weeks, not 52.00. Confirmed against the partner's
own figures for eight of nine employees. BA-03 is inclusive — the two differ on
purpose.

**3. BA-12 is asymmetric.** Periods under seven days come out of the
denominator, the Min-Max span and the One/Zero segment span — but their hours
and wages stay in the numerator. A one-day period is real money and not a real
week.

**4. BA-06 tests the rounded value.** Round to two decimals half-up first, then
compare to the floor. An employee at 34.9998 hours rounds to 35.00 and
qualifies. Comparing unrounded drops employees the reference run keeps.

**5. OZ-07 always divides by twelve.** Including months that scored zero. It
looks wrong and it matches the partner's output. Dividing by months-with-data will
look more correct and will not tie out.

Everything uses `Decimal`, never `float`. `Decimal(str(x))`, not
`Decimal(x)` — a float reading 2061.19 is really 2061.18999999999996.

## What changed on 2 September

From the partner's feedback. **A year is complete when it fills every REACHABLE month,
not all twelve.** A calendar-year client has no December measuring date, so
eleven months is its complete year. Judging against twelve rejected it as a base
year and pushed the base a year later.

| | Before | After |
| --- | --- | --- |
| Cascade base year | TY2021 | TY2020 |
| Portfolio claim | 229,285 | 607,110 |
| Certified figures | | unmoved |

The divisor stays 12. Only the completeness test changed — different question,
and conflating them moves every average.

## What is still open

Do not treat these as settled while building.

**The Month-12 cliff (questions 23-25 for the partner).** OZ-04 moves the target to the
last period end only when it falls after the 15th. On the Cascade fixture a
final period ending 12-15 scores Month 12 as **0**, while 12-16 scores ~25. A
one-day pay-calendar difference moves a location's annual average by roughly 8%
and therefore the credit. Two of six years affected on that client.

**Three lookups outstanding from the partner.** `EntityFiscalYearRules` (BA-01 —
highest priority, the per-client fiscal year is not derivable from payroll),
`PayFrequency` (BA-03), `PayCodeCategory` (BA-07, may carry the state-credit
inclusion flag).

**NULL versus 0 in hours and wages (Q2).** The source allows both and they are
not the same fact. `to_decimal()` currently treats NULL as zero; if the partner
says NULL means "not reported", that changes.

## What this is not

Not the production engine. The engine carries provenance recording, rule packs
resolved per tax year, agent surfaces and a soft-delete audit trail; none of that
is here. The arithmetic is identical and `crosscheck.py` is the evidence.

Headcount is certified — 10,236 employees, 539 Min-Max eligible, 656 Pay Period
eligible for TY2023. **Credit value is not**; it needs county tier, industry
eligibility and the base-year comparison. County and industry are both present in
the partner's schema, so that is plumbing rather than a data gap.

## If we disagree

Run `crosscheck.py` first — it isolates whether the difference is in the rules or
in the data reaching them. Then narrow by stage: employee population, then weeks,
then eligibility. The self-check assertions in `flex_rules.py` are named for the
rule they cover, so a failure points at the rule.
