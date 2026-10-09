# ADR-005 — Statute is versioned by year, and materialised

**Date** 2026-08-25 · **Status** Accepted

## Context

The retroactive audit is a core use case, not an extension: a client arrives
having already claimed credits and asks whether they could have claimed more.
That is answered by recalculating several prior years and comparing.

Which means the calculation must run under **the rules that were in force in the
year being calculated** — not today's. Statute changes annually, and in ways that
move the number materially:

| Changes yearly | Effect |
| --- | --- |
| County tier assignment | Georgia re-tiers annually; tier sets the per-job credit amount |
| Average weekly wage floor | Derived from the prior year's DOL county table — `JTCHistoricalWages_Jul 2025.pdf` is that source |
| Minimum new-jobs threshold | Varies by tier and by year |
| Zone designations | Opportunity zones, military zones and less-developed census tracts expire and are redesignated |
| Eligible industries | Statutory amendment |
| Credit amount per job | Statutory amendment |

### What exists today

`tools/baseyear.py` already implements the multi-year credit mechanics — a frozen
base year, five-year tranches, and a high-water mark. The partner:
*"five-year tranches, each year is its own opportunity."* That part is built.

Rule **versioning**, however, is barely there:

| Pack | Year coverage |
| --- | --- |
| `ga_jtc.json` | `thresholds_by_year` for 2024, 2025 |
| `sc_jtc.json` | `thresholds_by_year` for 2025 |
| The other eight | None |

And `thresholds_by_year` only covers floors. Nothing expresses a county
re-tiering, an expired zone, or an amended industry list.

So a six-year audit today would silently apply **2026 rules to 2021 payroll** for
most years and most programs. That is not a degraded answer; it is a wrong one,
and nothing would flag it.

## Decision

### 1. A rule pack is scoped to (program, tax year)

`rules/<program>/<tax_year>.json`. One file per program per year.

```
rules/
  ga_jtc/2020.json  2021.json  2022.json  2023.json  2024.json  2025.json
  sc_jtc/…
  federal_wotc/…
```

Ten programs across six years is sixty files. That is fine — they are data, they
are diffable, and most years differ from their predecessor in a handful of
fields.

### 2. Materialised, not computed

A year's pack is **fully resolved and stored**, not a base plus overlays merged
at run time.

This is the decision worth defending. Base-plus-overlay is DRY and would please
an engineer. But the question a tax authority asks is *"what rules did you apply
to my 2021 return?"* — and the answer should be **a file, with a hash**, not the
output of a merge that has to be re-executed and trusted.

Authoring may use a base and a diff. What gets committed, hashed and referenced
by a `run_manifest` is the resolved year.

This mirrors the assumption-set discipline already in place: v1 through v7 are
immutable and replay exactly. Statute deserves the same treatment.

### 3. A pack referenced by a filed return is frozen

Once a `program_claim` reaches `claimed`, the pack version it used cannot be
edited. A correction becomes a new version, and the amendment records both.

### 4. Resolution is explicit and fails loudly

`load_pack(program, tax_year)` returns the pack for that year or **raises**. It
never silently falls back to the nearest year or to a base.

A missing year is a real gap in our statutory coverage, and the honest response
is to say so — "we cannot calculate GA JTC for 2021, that ruleset is not
authored" — rather than to produce a number under the wrong rules.

### 5. The retroactive window is a pack attribute

`tn_jtc.json` already declares `retroactive_years: 15`. Make that systematic:
every pack states how far back its program can be claimed, and the audit window
is derived per program rather than assumed uniform.

## Four things freeze, not three — and one is currently in the wrong place

"Frozen programs, frozen state eligibility rules, payroll per year" is the right
decomposition. Working through it precisely gives **four** artifacts, because two
kinds of rule change on different cadences from different sources, and a fourth
axis is orthogonal to all of them.

| # | Artifact | Changes when | Source | Have it? |
| --- | --- | --- | --- | --- |
| 1 | **Program definition** — benefit structure, tranche years, carry-forward, retroactive window | A legislature amends the code | State statute | **No.** Flat packs, no year dimension |
| 2 | **Eligibility parameters** — wage floor, hour floor, county tier, zone designations, minimum jobs | **Every year, administratively** | DOL wage tables, DCA tier maps | **Wrong place** — see below |
| 3 | **Methodology** — BA-01…BA-12: how we measure | We learn something | Us, with the partner | **Yes.** v1–v8, immutable. v8 is the runnable set; v1–v7 predate this split and are retired. |
| 4 | **Payroll** — per client, per fiscal year | Continuously | The partner | **One year.** Four clients, one window each |

The distinction between 1 and 2 matters more than it first appears. A program's
*structure* changes rarely and only by statutory amendment. Its *parameters*
change **annually and automatically** — Georgia's wage floor is derived from the
prior year's DOL county table and moves every single year without anyone
legislating. Freezing them together is fine; not noticing they have different
sources is how a year gets missed.

### The one in the wrong place

> **Resolved on 26 Aug 2026 by assumption set v8.** The move described below has
> been made: `$636` now lives in `backend/rules/ga_jtc/2023.json`, v8 carries
> methodology alone, and the parity gate reproduces 10,236 / 539 / 656 with the
> floor resolved from the pack. The section is kept in the present tense because
> it is the reasoning that justified the change.

The Tax Year 2023 wage floor — **$636**, from the DOL 2022 table for Glascock
County — currently lives in the **assumption set** (`BA-06` in
`reference-dataset-assumptions.v7.json`), not in a year-scoped rule pack.

That is a conflation. $636 is a **statutory fact about 2023**. It is not a
methodological choice. Methodology is *"we round half-up"* and *"we exclude
sub-seven-day periods"* — decisions we made about how to measure.

It has a concrete consequence for the retroactive audit. To calculate TY2021
today, the only available lever is to author a new assumption set. But that would
assert *"we changed our method"* when we did not — we changed the **year**. The
version history becomes unreadable: given v8, was that a method change or a year
change? Nobody could tell, and replaying a historical run would require knowing.

**The separation:**

```
rule pack   (program, tax year)   statutory facts   ← $636 belongs here
assumption  (version)             our methodology   ← BA-01..BA-12 stays here
```

A TY2021 run then reads `pack(GA_JTC, 2021) + assumptions(v7)` — the same
certified method applied to a different year's statute. A TY2023 run reads
`pack(GA_JTC, 2023) + assumptions(v7)` and must still reproduce
**10,236 / 539 / 656**, which is the migration's acceptance test.

`run_manifest` already carries both `rule_pack_version` and
`step1_assumption_set_id`, so the model anticipated this even though the data
does not yet honour it.

### Migration

1. Author `rules/ga_jtc/2023.json` carrying the statutory floors currently in
   `BA-06`.
2. Point the engine at it; the parity gate must still return 10,236 / 539 / 656.
3. Only then strip the statutory values from the assumption set, leaving
   methodology. **v7 does not change** — it is published and immutable; v8 is
   "methodology only", and its own parity run proves it equivalent.
4. Author the remaining years and programs.

Step 2 before step 3 matters. Moving the value and removing it in one change
would leave no green state to bisect back to if the number moved.

## An ambiguity to resolve before building

**"Five years back" is two different mechanisms and they must not be conflated.**

- **The tranche window.** In Georgia, jobs created in year X generate credit for
  five subsequent years. This is what `baseyear.py` implements and what the
  partner's quote describes. It is about *credit duration*.
- **The amendment window.** How far back a filed return can be amended to claim
  a credit that was missed. It is about *statute of limitations*, is typically
  much shorter, and differs by state.

A six-year lookback justified by the first does not license amending six years of
returns under the second. Getting this wrong produces confident, unrecoverable
figures.

**Open for the partner:** which mechanism drives the six-year scope, and what is the
actual amendment window per program? Recorded as an ask, not assumed.

## Consequences

**Good.** A retroactive audit is defensible year by year. "What rules applied"
is a file. A missing ruleset is visible rather than silently wrong. Per-year
authoring is data work that parallelises and needs no engine change.

**Costs.** Sixty files instead of ten, and a migration: the current flat packs
become their most recent year. The year-authoring effort is real, and it is the
gating dependency for the retroactive product — `agents/rules_ingestion.py`
(ADR-004 F5.4) exists precisely to accelerate it, which makes that agent more
valuable than it first appeared.

**Data we do not yet hold.** Georgia county tier history by year; historical wage
tables beyond the one PDF; zone designation history. All are public, all are
sourceable, and all are needed before a six-year audit can be run for real.

## Follow-up: the benefit was not year-resolved *(fixed 10 September 2026)*

The floors were year-resolved from the day this ADR landed. The **benefit** was
not. `_replay_unit_series` read `_year_benefit(program, years[-1])` once and
applied it to the entire series, so a TY2020 credit was priced at TY2025's
per-job amount and gated by TY2025's minimum-new-jobs.

It produced no wrong number, because Georgia has held $3,500 per job, a 2-job
threshold and a 5-year tranche across every authored year. That is exactly what
made it dangerous: **the defect was invisible against the only packs we have**,
and the retroactive five-year scan is the feature it would have misreported the
moment a rate moved.

Two things changed:

- `compute_base_year_tranches` takes `benefit_by_year`. Each year is priced at
  its own rate and gated by its own threshold. A year absent from the map falls
  back to the caller's scalar — **never to a neighbouring year**, which is the
  behaviour this ADR exists to forbid.
- `TrancheYear` carries `per_job_usd`. The rate belongs on the year it priced,
  not on the series: six years can span six rates, and a single scalar reports
  whichever one happened to be read. `unit_year_master.per_job_usd` now comes
  from the year rather than the run.

**A tranche holds the rate of the year it opened.** The rate attaches to a job
when it is created, so a later year must not reprice a window already running.

Because no authored pack can exercise any of this, `tests/test_baseyear.py`
passes rates that differ **on purpose**. Without those six tests the engine could
revert to reading one year's statute for a whole series and the suite would stay
green — which is how this got in.

A negotiated designation still overrides the pack threshold in every year. A
designation is a current fact about a location, not a statutory value; it stays
flagged as prototype data (DISC-10).
