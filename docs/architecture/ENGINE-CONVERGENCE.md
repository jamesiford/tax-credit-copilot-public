# Engine convergence — specification

**Date** 2026-08-24 · **Author** James Ford · **Status** Phase 1 complete

## 1. The problem

The repository contains two calculation engines.

| | `tools/reference_*.py` | `tools/onezero.py` |
| --- | --- | --- |
| Size | ~130 KB across six modules | 54 KB |
| Consumed by | `api/workspace.py` only | `api/onezero.py`, `api/eligibility.py`, `api/chat.py`, `tools/simulation.py`, `tools/portfolio.py` — every product feature |
| Source data | The partner's four payroll files | Synthetic demo set / Fabric lakehouse |
| Rules | v7, certified against the partner | Pre-v5 |

Every parity decision reached with the partner between 30 July and 24 August — the paycheck-date
trim, the Tax Year 2023 floor, the exclusive-day Min-Max span, the actual-span Pay Period
denominator, the short-pay-period rule and its numerator asymmetry — landed in the benchmark
path. The engine behind the product never received any of it.

Three specific divergences, all confirmed by inspection:

1. **No short-pay-period rule.** `minimum_pay_period_days`, BA-12 and every related term are
   absent from `onezero.py`. The rule that moved Min-Max by twenty employees does not exist
   in the product.
2. **Frequency constants, not actual span.** `_frequency_weeks_per_period` still returns
   1.0 / 2.0 / 2.167 / 4.333. This is precisely the approach we tested and rejected: it
   produces 447 eligible against the partner's 659, because the source frequency codes do not mean
   what the documentation says.
3. **Weeks rounded to two decimals.** `round(days / 7.0, 2)` in the Min-Max step, where the
   certified path keeps full precision until the threshold test.

The practical consequence: the same payroll run through the app's Eligibility page and
through the Reference workspace returns **materially different answers today**.

## 2. Why this blocks expansion

Each proposed feature inherits the engine it is built on.

- **What-if** derives scenarios from a base calculation. `simulation.py` imports
  `credit_math` and `portfolio` — the production path. Scenarios computed from uncertified
  rules are wrong in a way users cannot see, and they act on them.
- **Other states** would ship from the production engine while Georgia is certified in the
  benchmark engine. That is an uncomfortable position to defend.
- **More customers** multiplies the surface that a later port has to cross.

Convergence is cheaper now than after another feature lands on top of it.

## 3. The seam

`OneZeroPack` is already the right abstraction and does not need replacing. It externalises
the *statutory* parameters — floors, wage basis, geographic granularity, measuring date, pay
codes, entity combination, part-time bands — and resolves them per tax year from rule-pack
JSON. Nine states already load through it.

What it does not carry is **methodology**: how the denominator is measured, what counts as a
real pay period, how the numerator is assembled, how values are rounded. Those are currently
implicit in the function bodies.

That is the whole shape of the fix. **Add a methodology block to the pack, have the
production functions read it, and default it to the certified v7 values.** No rewrite, no
second engine, no big-bang migration.

The distinction is worth stating precisely, because it is what makes the design hold:

- **Statutory parameters vary by state.** Georgia requires 35 hours and $636; South Carolina
  bands part-time hours. These belong per rule pack.
- **Methodology parameters vary by practice, not by state.** The partner measures a Min-Max span
  the same way in Georgia as he would in Tennessee. These belong as shared defaults, with
  a per-pack override only where a state genuinely dictates otherwise.

## 4. Phases

### Phase 1 — methodology convergence *(done, 2026-08-24)*

1. `OneZeroMethodology` carries the seven v7 parameters, defaulted to the
   certified values and validated strictly — an unknown or malformed key raises
   rather than silently reverting a pack to defaults.
2. `OneZeroPack` gained a `methodology` field; `load_pack_one_zero` populates it
   from an optional `one_zero.methodology` block. All ten packs inherit correct
   behaviour unedited.
3. Both production methods now honour it. Specifically:
   - `preprocess` takes an explicit `fiscal_window` (BA-01) and stopped
     hard-dropping zero-hour rows (BA-05).
   - `run_min_max_method` filters short periods from the span, honours the span
     mode, and no longer rounds weeks to two decimals (BA-11, BA-12).
   - `run_pay_period_method` sums measured spans instead of frequency constants
     and filters short periods from the denominator only (BA-03, BA-12).
   - The legacy off-cycle heuristic became opt-in; BA-12's day test supersedes
     it.
   - Averages round half-up via `Decimal`, matching Access, not Python's
     banker's rounding.
4. `tests/test_engine_parity_reference.py` runs the partner's four files through the
   production engine.

**Result — the production engine now reproduces the certified figures exactly:**

| | Certified (reference) | Production engine |
| --- | --- | --- |
| Employees | 10,236 | 10,236 |
| Min-Max eligible | 539 | 539 |
| Pay Period eligible | 656 | 656 |

Employee-level totals match to the cent, and the eligible *sets* match, not
merely the counts. 443 backend tests and 78 frontend tests pass. The independent
stdlib re-derivation is 17/17.

Two things were corrected along the way. The synthetic reconciliation fixture
was a snapshot of the old engine, so it was regenerated and its note now points
at the parity test as the real gate. The independent verifier was still on v6
and was moved to v7 — where it also revealed that its own One/Zero segment build
was missing the BA-12 filter the repo already applied.

### Phase 2 — tenancy

`client_id`, `employer_id` and `account_id` have **zero occurrences** across `tools/`. The
engine is implicitly single-client. Adding customers is therefore a data-model change, not
a configuration one.

Thread a client key through the calculation surface, the rule-pack resolution, the trail and
the operational tables specified in `OPERATIONAL-DATA-MODEL.md`. Per-client fiscal year
configuration lands here too, replacing the hand-edited dates at the top of a
manually maintained query.

**Acceptance:** two clients calculated in one process yield independent, correctly attributed
results.

### Phase 3 — retire the duplicate

Once the production engine is certified, the reference modules reduce to what they are actually
for: a parity harness that pins the engine against the partner's dataset in CI. The duplicated
calculation logic inside them goes.

**Acceptance:** one implementation of each rule; the reference path calls the production engine.

> **Correction, 30 August — the oracle has to survive the deletion.**
>
> As written, this phase is unsafe. `tests/test_engine_parity_reference.py` earns
> its keep by running the same payroll through *two independently written*
> implementations and comparing them. Make the reference path call the production
> engine and that test compares the engine to itself — it will pass for a bug
> present in both sides, which is precisely the failure it exists to catch.
>
> Deleting the duplicated *calculation* is right. Deleting the independent
> *check* is not. Two things must therefore outlive Phase 3, and neither may be
> reimplemented in terms of the production engine:
>
> 1. **`tests/certified.py`** — the pinned literals 10,236 / 539 / 656 and the
>    certified pack. A value, not a derivation, so it cannot drift with the code.
> 2. **`backend/tools/verify_reference_independent.py`** — a stdlib-only
>    re-derivation written without reference to the implementation. It is 17/17
>    today and has caught two defects the suite did not, including one in its own
>    earlier version. It stays a second implementation **on purpose**.
>
> Restated acceptance: *one implementation of each rule **in the product**, plus
> one independent re-derivation retained solely as an oracle. `reference_*`
> shrinks to a source adapter and a comparison harness; the statutory logic
> inside it goes.*

### Phase 4 — expand

What-if, additional states end to end, additional programs. All now inheriting certified
rules by construction.

## 5. What is safe to build in parallel

These do not touch the engine and need not wait:

- Rule-pack authoring for other states — JSON data against a schema already proven ten times
- The Fabric landing and operational tables
- Exception report, soft delete and manual override — the partner asked for these twice
- Power BI, prospecting, UI

## 6. Risk

The main risk in Phase 1 was **silent behaviour change in the demo path**, and it
materialised as expected: correcting the rules moved the synthetic portfolio
numbers. Five of nine states shifted, the largest by 1.0 average headcount (TN
1.83 → 0.83), because the demo set contains semi-monthly and monthly periods
where the frequency constant and the measured span genuinely disagree.

Those figures were wrong before and are right now, but **demo scripts and any
screenshots quoting headcount need re-checking before the next customer
session.**

Mitigated by defaulting every methodology parameter explicitly rather than
implicitly, so the change is visible in the pack rather than buried in a diff.

## 7. Not in scope

Credit *value* remains out of reach regardless of convergence. County tier, industry
eligibility, base-year comparison and entity treatment are absent from the payroll extract.
Convergence certifies headcount, not dollars.
