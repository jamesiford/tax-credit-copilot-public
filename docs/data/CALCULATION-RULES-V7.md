---
title: "Tax Credit Copilot — Georgia JTC calculation rules, v7"
subtitle: "The frozen rule set, its sources, and what remains open"
date: "24 August 2026"
---

# Tax Credit Copilot — Georgia JTC calculation rules, v7

**Assumption sets** `GDS-STEP1-2026-08-24-v7` · `GDS-ONEZERO-2026-08-24-v7`
**Status** Stakeholder-confirmed on the 20 August call · **Supersedes** v6

> **Update, 26 August 2026 — every rule below still stands.** Step-1 v8 has since
> superseded v7, but it changed no rule and no number: it moved the Tax Year 2023
> statutory floor (35 hours / $636) out of the assumption set and into a
> year-scoped rule pack, so that adding a tax year no longer looks like a change
> of method ([ADR-005](../architecture/ADR-005-year-versioned-rules.md)). The
> parity gate reproduces 10,236 / 539 / 656 under v8 unchanged. Read §5 below as
> describing where that floor is *sourced from*, not where it is *stored*.

## 1. Why this document exists

These rules decide which employees count toward a Georgia Job Tax Credit claim, and the
resulting figures land on a filed return. They therefore need to be readable by a tax
practitioner, not only by an engineer, and every one of them needs to name the source it
came from.

Every version is retained, and each one records exactly what was decided and when. v1–v7
are now history: they predate the split between statute and method, so the engine no longer
runs them. v8 is the current set and is the one the application runs today.

The rules below are stated in the order the calculation applies them.

## 2. What changed in v7, and why

v6 was fitted to the partner's 12 August reconciliation file. On the 20 August call the
partner identified an error in that file:

> "I used the chopped payroll as my numerator, which is the wrong thing... mine was wrong."

v6 had faithfully reproduced the error. v7 implements the partner's stated intent instead: short pay
periods are removed from the **denominator** but their hours and wages remain in the
**numerator**.

| Metric | v6 | v7 |
| --- | --- | --- |
| Min-Max eligible | 519 | **539** |
| Pay Period eligible | 651 | **656** |
| Employees evaluated | 10,080 | **10,236** |

The population recovers because an employee whose only records sit in short pay periods is
no longer removed from the calculation altogether — their earnings still count.

Neither of the partner's published figures — 511 Min-Max and 659 Pay Period — is a valid
comparison target. The partner confirmed on the same call that the Min-Max run used the chopped
numerator and that the Pay Period run did not collapse multiple pay-code lines per period.
Both will be re-run on the partner's side.

## 3. Stage 1 — selecting the fiscal year

**BA-01. The analysis window is per client and comes from configuration, not from the
payroll.** For the reference dataset it is 28 July 2023 through 2 August 2024.

Fiscal years cannot be inferred from payroll data. Public filers take theirs from the 10-K;
many private flow-through entities are calendar-year; some are rule-based, such as the
Saturday nearest a given date. The partner: *"We'll have to build you a table with 'this is the
client, this is the fiscal year'... we can't just run it across every client and say, oh,
they're all calendar year."*

**BA-02. Include a payroll record when its paycheck date falls inside the window.** Nothing
else is tested. A pay period that ends after the fiscal year end is still included if the
cheque was issued in the window, and a period that began before the window opens is
included on the same basis.

> The partner, 20 August: *"You wouldn't take a pay period, even if it started in the current year,
> but it was paid in the next year. And conversely, you can pick up a pay period that was
> started last year, but paid this year."*

This selection reproduces the partner's reported control totals exactly: 384,418 records,
4,950,777.43 hours, $82,533,629.87 in wages, 10,236 employees.

## 4. Stage 2 — normalising the payroll

**BA-04. Collapse exact duplicate payroll facts.** Group on employee, unit, FEIN, pay period
start, pay period end, paycheck date and pay frequency; sum the signed hours and wages.

**BA-03. Collapse multiple pay-code lines into one denominator period.** Modern payroll
extracts carry several rows per pay period — regular, overtime, bonus and so on. Each
employee's records sharing a pay period start and end become a single period for
denominator purposes, with every source row retained as lineage.

This step is the one the partner identified as missing from their own Pay Period run:

> *"I could have one, two, 10 different lines for any one pay period... I did not collapse
> the payroll. So I was counting up too many ones or too many twos. That's why I think my
> number was wrong."*

**BA-05. Preserve corrections.** Negative hours and negative wages are retained rather than
discarded, and wage rows carrying no hours are kept in the totals.

## 5. Stage 3 — removing periods that are not real

**BA-12. Exclude any pay period shorter than seven days from the denominator, the Min-Max
span, and the One/Zero segment span. Keep its hours and wages in the numerator.**

This is the rule that most affects the result, and the asymmetry is deliberate.

> The partner, 20 August: *"You get a lot of these garbagey pay periods that come through — one day
> pay periods, two day pay periods, and they all have a one. So if you include those, you're
> going to potentially aggregate up to way more than 52 weeks in a year."*

and, on the numerator:

> *"For my numerator, I go back to the stored payroll file where I aggregated all wages
> paid, all hours worked, irrespective of good or bad pay periods."*

The reasoning is that a one-day pay period still represents real money the employee earned,
so it belongs in the numerator; but it is not a real unit of elapsed time, so counting it in
the denominator distorts the average. The partner's worked example: an employee with a four-day period
and 81 hours grossed up to 142 hours per week — *"they only really worked 81 hours, but it
grossed up to 142 hours."*

### 5.1 What this excludes in the reference dataset

| Period length | Rows excluded |
| --- | --- |
| 1 day | 951 |
| 2 days | 549 |
| 3 days | 82 |
| 4 days | 57 |
| 5 days | 53 |
| 6 days | 13 |
| **Total** | **1,705** |

Those rows carry 7,726.49 hours and $1,859,776.29 in wages, all of which remain in the
numerator. They touch 998 employees, of whom 156 are left with no qualifying pay period at
all.

### 5.2 Exclusions are reversible

Excluded rows are a soft delete, not a silent drop. Each is recorded with its source file
and row number, its period length, and the rule that removed it, so a reviewer can inspect
and reinstate it.

> The partner: *"Maybe you capture the ineligibles and then give the user the ability to review the
> ineligibles and say, well, wait a minute, that one should be eligible. Let's put it back
> over there."*

### 5.3 Longer anomalies are reported, not removed

The partner also raised excluding other abnormal lengths — *"technically I might want to knock out
a 13 or a 15 or anything that's not a normal pay period"* — but settled on one to six days
as the rule that can be automated safely, with visual inspection for the rest. Periods of
unusual length outside that band are therefore flagged on the exception report rather than
excluded. **This remains open for confirmation.**

## 6. Stage 4 — the two denominators

The two methods are expected to disagree. Parity means each matches the partner's implementation of
that method, not that the two agree with each other.

**BA-11. Min-Max weeks = (last pay period end − first pay period start) ÷ 7, with no
inclusive-day adjustment.**

> One Zero Min Max.docx, Step 2: *"count the number of days between the two and divide by 7."*

A full-year weekly employee therefore lands on 51.86 weeks rather than 52.00. This reading
was confirmed empirically: the partner's reported weeks reproduce exactly for eight of the nine
employees the partner detailed on 12 August.

**BA-03. Pay Period weeks = the sum over each included period of (end − start + 1) ÷ 7.**

The source `PayFrequency` code is retained as lineage but is not used as a week multiplier.

**On what that code actually is.** `FlexSchema.txt` (received 25 August) shows that the
`PayFrequency` column in the extract is `Payroll.PayFrequencyId` — a **surrogate foreign key**
into a `dbo.PayFrequency` lookup table that has not been supplied. Earlier drafts of this rule
said the codes "do not behave as documented"; the more accurate statement is that we never had
the documentation, and were inferring meaning from a key.

What the reference dataset shows, measured against actual period spans:

| `PayFrequencyId` | Rows | Dominant span |
| --- | --- | --- |
| 1 | 374,535 | 7 days (372,285 of them) |
| 2 | 7,153 | 15 days, then 14 |
| 4 | 2,745 | 16 days — every single one |

Reading 4 as "every four weeks" produced 447 eligible against the partner's 659. Whatever the lookup
turns out to say, **the measured span is authoritative** — it is observed rather than asserted,
and it is what the partner's own output does.

The partner independently confirmed the codes are unreliable in the extract:

> *"I run a little macro that goes down and basically recalculates whether it's a one or a
> two, because many times the download comes in... it's a blank field in the frequency
> column."*

and on code 4 specifically: *"fours are rarities... usually fours are miscoded twos."*

**BA-09. Report, never repair.** Pay Period weeks should not exceed Min-Max weeks, and
should not exceed 53 weeks without review. Violations are reported; no value is silently
capped or adjusted.

## 7. Stage 5 — the eligibility test

**BA-06. An employee qualifies when the rounded average weekly hours are at least 35 and the
rounded average weekly wage is at least the annual floor for the tax year.**

For Tax Year 2023 that floor is **$636**, which the Georgia Department of Community Affairs
table derives from DOL report year 2022, Glascock County, annualised at $33,072. The partner
confirmed the figure directly on the 6 August call.

Averages are rounded to two decimals, half up, and the rounded value is what the thresholds
test. This admits an employee whose unrounded average is 34.9998 hours, which the partner endorsed:

> *"When they're working 34.99 hours, why not include them? I'm a big fan of giving the
> auditors things to throw out. The auditors always want to throw something out, so
> sometimes you throw them something because you know they're going to throw it out."*

The partner paired that with a requirement for a manual adjustment function, so a reviewer can move
an employee either way and the decision is recorded.

## 8. Stage 6 — the One/Zero headcount matrix

**OZ-01. Twelve month-end targets, pinned explicitly.** For the reference dataset, August 2023
through July 2024. The window is configured rather than derived from the fiscal year start,
because the v7 window opens on 28 July and deriving month ends from it would silently shift
the entire matrix by a month.

**OZ-02 and OZ-03. A month scores 1 when the segment's pay period start is on or before the
month-end target and its pay period end is on or after it.** Min-Max segments span the
employee's whole time at a unit; Pay Period segments are per period.

**OZ-04. Month 12 exception.** If the last pay period end falls in month 12 on a day after
the 15th, that date becomes the target instead of month end.

**OZ-06. Test of twos: flagged, not resolved.** An employee appearing at more than one unit
in the same month is flagged for review rather than allocated automatically, matching the partner's
decision not to clear the twos yet.

**OZ-07. Average headcount = the twelve monthly totals divided by twelve**, preserved at
three precisions: unrounded, nearest whole with half rounding up, and two decimals.

## 9. What the calculation does not do

Average headcount is not a credit figure. Converting it into dollars needs county tier
designation, industry eligibility, the base-year comparison and entity-level treatment —
none of which exist in the payroll extract. No credit value is claimed from this data.

## 10. Known limitations

**The source file is missing pay periods.** Semi-monthly coverage runs at 219 to 246
employees in every month except November 2023, where it is zero: the second-half November
period stops on the 24th, and 313 of the 314 semi-monthly employees have no record at all
between 16 and 30 November. July 2024 has no second-half period. The partner confirmed this
unprompted — *"there is a missing pay period in this data, and that does happen to us"* —
and also confirmed the asymmetry we had measured: *"it'll hurt you significantly on the
min-max, but not on the pay period."*

Month 4 and Month 12 of the Pay Period matrix should not be signed off until the extract is
regenerated.

**Hire and termination dates are not applied.** The partner described substituting hire date for
pay period start on an employee's first period, which would tighten the denominator —
*"instead of 52 weeks, you have 51.1 weeks... that little nudge will get you over the
edge."* The supplied extract carries no hire or termination columns, and the partner cautioned that
those dates are unreliable in payroll systems because of turnover and rehires.

**Pay codes are absent.** Every wage in the extract is treated as eligible compensation. A
pay-code lookup is being added to the lakehouse, after which reimbursements and other
non-qualifying earnings can be excluded.

## 11. Open items

| # | Item | Owner |
| --- | --- | --- |
| 1 | Confirm the numerator correction in a re-run | The partner |
| 2 | Confirm whether 13- and 15-day periods should be excluded or only reported | The partner |
| 3 | Regenerate the extract for November 2023 and July 2024 | The partner |
| 4 | Supply hire and termination dates, if they can be trusted | The partner |
| 5 | Add the pay-code lookup and agree which codes are non-qualifying | The partner's team |
| 6 | Per-client fiscal year configuration table | The partner |

## Appendix — version history

| Set | Date | What it introduced |
| --- | --- | --- |
| v1 | 29 Jul | First formalisation of the Step 1 narrative |
| v2 | 29 Jul | Period identity and the denominator invariant |
| v3 | 29 Jul | Fiscal boundary controls |
| v4 | 30 Jul | Cash-basis leading selection; Tax Year 2024 floor |
| v5 | 5 Aug | Tax Year 2023 at $636; paycheck-date-only trim; actual-span denominator; exclusive-day Min-Max |
| v6 | 18 Aug | Short pay period rule, fitted to the partner's 12 August file |
| **v7** | **24 Aug** | **Numerator correction; exclusion audit trail** |

Every set is retained. A run recorded against v4 still reproduces its original figures.
