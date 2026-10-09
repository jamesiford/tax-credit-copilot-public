"""Synthetic clients in the partner's source shape.

Candle Bottle (the reference dataset) is one real client with one
fiscal calendar in one state, for one tax year. A demo needs more than that, and
neither multi-tenancy nor the **retroactive audit** — the case the partner actually
sells — can be shown with a single tenant in a single year.

Each client runs a **six-year window** (a base year plus five), and each is shaped
to exercise something the reference dataset cannot:

    Cascade Retail Partners    Steady growth. Calendar-year fiscal, multi-state,
                               biweekly. The clean net-new story: a fresh tranche
                               most years, several running at once. In TY2025
                               GA-007 loses staff from June and falls below the
                               minimum. GA-016 is a newer store: it opens with
                               TY2023 (its base), qualifies in TY2024 and TY2025,
                               and dips below in the open TY2026 — the "how am I
                               doing" story. All layered on as labelled events.

    Northwind Care Systems     Shrink then recover. March year-end, semi-monthly,
                               part-time-heavy. Falls below its frozen base and
                               climbs back, so the persistent high-water mark and
                               `backfilled` in baseyear.py have something to bite
                               on. Its wage growth deliberately LAGS Georgia's
                               rising floor (DISC-12).

    Ironbridge Logistics       Threshold crossing. Small, two entities, a worksite
                               opening mid-window. Net-new sits under the statutory
                               minimum for the early years and crosses it later —
                               the "you could have claimed from 2023" case.

    Halloway Foods             Grew, then fell and stayed down. Creates tranches
                               early, then drops below the high-water mark while
                               those tranches are still inside their five-year
                               window. The exposure case: installments claimed for
                               jobs no longer maintained.

Trajectories are headcount multipliers against the base year, and they are the
whole point — six years of the same shape would be six times the rows and none
of the signal.

Employee identity is stable across years. Someone employed in the base year keeps
their `employee_id` into the next, so growth reads as hiring rather than total
churn; when headcount falls, people are terminated and a later recovery hires
NEW ids rather than resurrecting the departed.

Determinism
-----------
Everything derives from a seeded `random.Random`. The same seed yields the same
bytes, so a run manifest that pins a snapshot hash stays meaningful and a demo
does not shift between rehearsal and delivery.

These never touch the certified figures: they are separate accounts, and the
parity gate runs against Candle Bottle alone.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from .schema import (
    Account,
    Address,
    Employment,
    Entity,
    EntityFiscalYearRules,
    SourceDataset,
    Location,
    PayCode,
    PayFrequency,
    Payroll,
    StateCountyZip,
)

# INFERRED — mirrors from_reference. The real dbo.PayFrequency was never supplied.
_PAY_FREQUENCY_LABELS = {
    1: "Weekly (inferred: 7-day spans)",
    2: "Semi-monthly (inferred: 15- and 14-day spans)",
    3: "Biweekly (inferred: 14-day spans)",
    4: "Semi-monthly, 16th-31st (inferred: 16-day spans)",
}

_PAY_CODES = [
    ("REG", "Regular", True),
    ("OT", "Overtime", True),
    ("BON", "Bonus", True),
    ("PTO", "Paid time off", True),
]

# (state, county, zip, city) — county is what drives tier, and therefore credit
# value. Real counties so a tier lookup has something plausible to resolve.
_PLACES = {
    "GA": [("Fulton", "30303", "Atlanta"), ("Chatham", "31401", "Savannah"),
           ("Bibb", "31201", "Macon"), ("Lowndes", "31601", "Valdosta")],
    "SC": [("Greenville", "29601", "Greenville"), ("Charleston", "29401", "Charleston")],
    "NC": [("Mecklenburg", "28202", "Charlotte"), ("Wake", "27601", "Raleigh")],
    "TN": [("Davidson", "37201", "Nashville"), ("Shelby", "38103", "Memphis")],
}

_JOB_TITLES = [
    "Store Associate", "Shift Supervisor", "Assistant Manager", "Store Manager",
    "Warehouse Operative", "Forklift Operator", "Logistics Coordinator",
    "Care Assistant", "Registered Nurse", "Unit Coordinator", "Scheduler",
]

# The six-year window every synthetic client runs. Georgia has published a
# verified wage floor for each of these (TY2020 $541 through TY2025 $680); TY2026
# needs the summer-2026 DOL release, which we do not hold. Generating a year we
# cannot legally price would produce payroll the engine must refuse.
BASE_TAX_YEAR = 2020
WINDOW_YEARS = 6

# The CURRENT year, beyond the retroactive window: open, and generated only up
# to the in-year checkpoint (24 Sep 2026, WI-21 follow-up — "so we can properly
# tell the How am I doing and What if story"). Generated AFTER the window in the
# same seeded loop, so every TY2020-25 row is byte-identical with or without it.
# Its statute is a labelled placeholder (rules/ga_jtc/2026.json).
CURRENT_TAX_YEAR = 2026
CURRENT_YEAR_THROUGH = date(2026, 8, 31)

# Base-year hourly rate band. Anchored to the TY2020 floor of $541/week: at 40
# hours that is $13.53/hour, at 35 hours $15.46. The band starts just above the
# 35-hour break so the lower tail drifts out of eligibility as Georgia's floor
# climbs to $680 — which is a real effect (DISC-12), not a data defect.
#
# Deliberately a literal rather than resolved from the rule pack: coupling demo
# data to statute would make every synthetic row move whenever a floor is
# corrected. `test_source_synthetic.py` asserts the resulting eligible share, so a
# statutory change that would hollow out the demo fails a test instead of
# quietly producing an all-zero screen.
_BASE_HOURLY_MIN = 14.50
_BASE_HOURLY_MAX = 32.00


@dataclass(frozen=True, slots=True)
class DemoDeparture:
    """Named employees leave one worksite, on purpose, for a demo story.

    Applied AFTER the seeded generation rather than inside it, so it draws
    nothing from the RNG: every other row a client produces is byte-identical
    with or without it. That keeps the change reviewable as "these people left
    this site", not "the whole client quietly regenerated".

    Leavers are established full-timers comfortably over the wage floor, because
    only a job that COUNTS can be lost — removing somebody who never qualified
    would move nothing and look like it should have.
    """

    tax_year: int
    #  `client_location_id`, e.g. "GA-016".
    site: str
    #  (calendar month, how many leave before it opens). Staggered so the monthly
    #  grid reads as a location winding down, not a one-day cliff.
    leavers_by_month: tuple[tuple[int, int], ...]
    reason: str


@dataclass(frozen=True, slots=True)
class DemoOpening:
    """One worksite opens later than the rest, on purpose, for a demo story.

    Like `DemoDeparture`, applied after the seeded generation and drawing
    nothing from the RNG: rows at the site before it opened are removed, and
    nothing anywhere else moves. Opening on a fiscal-year boundary makes that
    year the location's first complete one, and therefore its base year.
    """

    site: str
    opens: date
    reason: str


@dataclass(frozen=True, slots=True)
class DemoHiring:
    """Named full-timers join one worksite at the open of a year, for a demo story.

    Fixed hours and pay, no RNG, and new employee ids from a reserved block, so
    every generated row is byte-identical with or without it. They stay on
    payroll until a `DemoDeparture` or the end of the generated window.
    """

    tax_year: int
    site: str
    count: int
    weekly_hours: float
    #  The rate in the hire year; later years grow at the client's wage growth.
    hourly_rate: float
    reason: str


#  Story hires take ids from the top of the tenant's block, clear of anything
#  the seeded generator reaches, and inside the range `load_fabric --accounts`
#  rewrites.
_STORY_EMPLOYEE_OFFSET = 99_000


@dataclass(frozen=True, slots=True)
class SyntheticClientSpec:
    """What makes one generated client different from the others."""

    account_id: int
    name: str
    states: tuple[str, ...]
    #  Headcount in the BASE year. Later years scale by `trajectory`.
    base_employees: int
    worksites: int
    #  The base year's fiscal window. Later years shift by whole years, so a
    #  March-year-end client keeps its March year-end throughout.
    fiscal_begin: date
    fiscal_end: date
    pay_frequency_id: int
    period_days: int
    #  Headcount multiplier per year, index 0 == the base year. Must have
    #  WINDOW_YEARS entries. This is the client's story.
    trajectory: tuple[float, ...]
    #  One line on what this client demonstrates. Surfaced in the demo, so it
    #  lives with the data rather than in a slide that drifts out of date.
    narrative: str
    entities: int = 1
    #  Fraction of the workforce placed just below the 35-hour floor. The point
    #  is to have employees near the boundary, so a demo of "who is close to
    #  qualifying" has something real to show.
    part_time_share: float = 0.25
    mid_year_worksite_opens: bool = False
    #  Annual wage growth. Georgia's floor rose ~4.7%/year across this window
    #  ($541 to $680), so a client below that rate sheds eligible employees
    #  without shedding a single job.
    annual_wage_growth: float = 0.045
    #  Baseline churn even in a flat year, so Min-Max spans vary and the
    #  denominator is not a constant.
    annual_attrition: float = 0.10
    seed: int = 20260825
    #  Labelled story events layered on the generated payroll. See DemoDeparture.
    departures: tuple["DemoDeparture", ...] = ()
    #  Labelled story events: a late-opening site, and hires at it. Applied
    #  before departures, in this order.
    openings: tuple["DemoOpening", ...] = ()
    hirings: tuple["DemoHiring", ...] = ()
    #  NAICS sector (data/source/industry.py). Display-only: WI-20.
    industry_type_id: int | None = None
    #  Headcount multiplier for the CURRENT year (TY2026, open to 31 Aug).
    #  None generates no current year at all.
    current_year_trajectory: float | None = None

    def __post_init__(self) -> None:
        if len(self.trajectory) != WINDOW_YEARS:
            raise ValueError(
                f"{self.name}: trajectory has {len(self.trajectory)} entries, "
                f"expected {WINDOW_YEARS} (base year plus five)"
            )
        if self.trajectory[0] != 1.0:
            raise ValueError(
                f"{self.name}: trajectory[0] is the base year and must be 1.0"
            )

    @property
    def tax_years(self) -> tuple[int, ...]:
        return tuple(BASE_TAX_YEAR + i for i in range(WINDOW_YEARS))

    @property
    def generated_years(self) -> tuple[int, ...]:
        """The window, plus the open current year when this client has one."""
        extra = (CURRENT_TAX_YEAR,) if self.current_year_trajectory is not None else ()
        return self.tax_years + extra


def _shift_years(d: date, years: int) -> date:
    """Same calendar day, `years` later. 29 Feb lands on 28 Feb in a common year."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


SYNTHETIC_CLIENTS: tuple[SyntheticClientSpec, ...] = (
    SyntheticClientSpec(
        account_id=2001,
        name="Cascade Retail Partners",
        states=("GA", "NC", "SC"),
        base_employees=380,
        worksites=18,
        fiscal_begin=date(2020, 1, 1),
        fiscal_end=date(2020, 12, 31),
        pay_frequency_id=3,
        period_days=14,
        trajectory=(1.00, 1.09, 1.19, 1.28, 1.38, 1.48),
        narrative=(
            "Steady expansion across three states. A fresh tranche in most years, "
            "several claimable at once — the clean net-new story."
        ),
        part_time_share=0.30,
        annual_wage_growth=0.050,
        seed=20260825,
        industry_type_id=44,
        # TY2026, open to 31 Aug. Cascade keeps growing; GA-007 stays down
        # after WI-11's leavers, and GA-016 dips for the first time.
        current_year_trajectory=1.52,
        # "How am I doing": GA-007 gives back its growth part-way through
        # TY2025, in months that are CLOSED by the 31 August checkpoint the
        # progress view projects from — so the grid and the on-track read agree.
        departures=(
            DemoDeparture(
                tax_year=2025, site="GA-007",
                leavers_by_month=((6, 4),),
                reason="Demo story: four full-timers leave in June TY2025 and are not replaced.",
            ),
            # 30 Sep: GA-016 dips in the CURRENT year only. Staggered, and it
            # must not empty out: a unit-year with a zero-count month reads as
            # `partial`, which is a different and wrong story.
            DemoDeparture(
                tax_year=2026, site="GA-016",
                leavers_by_month=((3, 2), (4, 2), (5, 2)),
                reason="Demo story: six full-timers leave across the spring of TY2026.",
            ),
        ),
        # 30 Sep: GA-016 is a newer store. It opens with TY2023, which is
        # therefore its base year; two hires at the open of TY2024 carry it
        # clear of the two-job minimum in TY2024 and TY2025, and the TY2026
        # leavers above take it back under so far.
        openings=(
            DemoOpening(
                site="GA-016", opens=date(2023, 1, 1),
                reason="Demo story: the location opens with TY2023, its base year.",
            ),
        ),
        hirings=(
            DemoHiring(
                tax_year=2024, site="GA-016", count=2, weekly_hours=40.0, hourly_rate=19.00,
                reason="Demo story: two full-timers join at the open of TY2024.",
            ),
        ),
    ),
    SyntheticClientSpec(
        account_id=2002,
        name="Northwind Care Systems",
        states=("GA", "TN"),
        base_employees=260,
        worksites=10,
        fiscal_begin=date(2020, 4, 1),
        fiscal_end=date(2021, 3, 31),
        pay_frequency_id=2,
        period_days=15,
        # Below base for three years, then past it. Exercises the persistent
        # high-water mark and `backfilled`: the recovery must not be treated as
        # fresh job creation up to the level they already had in 2020.
        trajectory=(1.00, 0.88, 0.74, 0.83, 0.97, 1.14),
        narrative=(
            "Contraction through 2022 then recovery. Tests the frozen base and the "
            "persistent high-water mark — the 2025 rebound is not all new jobs."
        ),
        part_time_share=0.45,
        # Deliberately behind Georgia's ~4.7%/yr floor growth: eligibility erodes
        # from wage drift alone, with headcount held constant (DISC-12).
        annual_wage_growth=0.022,
        annual_attrition=0.16,
        seed=20260826,
        industry_type_id=62,
        # TY2026, open to 31 Aug. Northwind's recovery continues.
        current_year_trajectory=1.20,
    ),
    SyntheticClientSpec(
        account_id=2003,
        name="Ironbridge Logistics",
        states=("GA",),
        base_employees=88,
        worksites=4,
        fiscal_begin=date(2020, 1, 1),
        fiscal_end=date(2020, 12, 31),
        pay_frequency_id=1,
        period_days=7,
        # Net-new stays under GA's two-job minimum until 2023, then clears it
        # decisively. The retroactive pitch: "you could have claimed from 2023."
        trajectory=(1.00, 1.00, 1.01, 1.14, 1.30, 1.44),
        narrative=(
            "Flat until 2023, then a step change. Net-new sits below the statutory "
            "two-job minimum for the early years and crosses it mid-window."
        ),
        entities=2,
        part_time_share=0.15,
        mid_year_worksite_opens=True,
        annual_wage_growth=0.048,
        seed=20260827,
        industry_type_id=48,
        # TY2026, open to 31 Aug. Ironbridge keeps its step change.
        current_year_trajectory=1.50,
    ),
    SyntheticClientSpec(
        account_id=2004,
        name="Halloway Foods",
        states=("GA", "SC"),
        base_employees=210,
        worksites=7,
        fiscal_begin=date(2020, 7, 1),
        fiscal_end=date(2021, 6, 30),
        pay_frequency_id=3,
        period_days=14,
        # Up hard, then down and stays down — below the 2020 base, so net-new
        # goes to zero and the year stops qualifying while the 2021-22 tranches
        # are still inside their five-year window.
        trajectory=(1.00, 1.22, 1.35, 1.05, 0.86, 0.81),
        narrative=(
            "Grew hard through 2022, then declined and stayed down. Early tranches "
            "remain in-window while the jobs behind them are gone — the exposure case."
        ),
        part_time_share=0.22,
        annual_wage_growth=0.031,
        annual_attrition=0.18,
        seed=20260828,
        industry_type_id=72,
        # TY2026, open to 31 Aug. Halloway is still sliding.
        current_year_trajectory=0.79,
    ),
)


def _loaded_at(tax_year: int) -> datetime:
    """When a year's payroll was loaded. A closed year loads the January after;
    the open year was loaded the night after its checkpoint, never in the future."""
    if tax_year == CURRENT_TAX_YEAR:
        return datetime.combine(CURRENT_YEAR_THROUGH + timedelta(days=1), datetime.min.time()).replace(hour=3)
    return datetime(tax_year + 1, 1, 15, 3, 0, 0)


def _pay_periods(begin: date, end: date, days: int) -> list[tuple[date, date, date]]:
    """(start, end, paycheck) triples covering the fiscal window.

    The paycheck date lands five days after period end — enough to be realistic,
    and enough that the last period of a year is paid in the next one, which is
    exactly the boundary BA-02's paycheck-date trim exists to handle.
    """
    out: list[tuple[date, date, date]] = []
    cursor = begin
    while cursor <= end:
        period_end = min(cursor + timedelta(days=days - 1), end)
        out.append((cursor, period_end, period_end + timedelta(days=5)))
        cursor = period_end + timedelta(days=1)
    return out


@dataclass
class _Worker:
    """One person, tracked across the whole window rather than per year."""

    employee_id: int
    location_index: int
    part_time: bool
    base_hours: float
    base_rate: float
    job_title: str
    hired_on: date
    first_year: int
    terminated_on: date | None = None
    last_year: int | None = None



def build_synthetic_dataset(spec: SyntheticClientSpec) -> SourceDataset:
    """Generate one client's tables in the partner's source shape, across the window."""
    rng = random.Random(spec.seed)

    fiscal_rule = EntityFiscalYearRules(
        fiscal_year_rules_id=spec.account_id,
        name=f"{spec.name} fiscal calendar",
        fiscal_year_begin=spec.fiscal_begin,
        fiscal_year_end=spec.fiscal_end,
        rule_expression=(
            "Calendar year"
            if (spec.fiscal_begin.month, spec.fiscal_begin.day) == (1, 1)
            else f"Fiscal year ending {spec.fiscal_end:%d %B}"
        ),
    )

    # Entities. Where there is more than one, the rest hang off the first so
    # CALC-06 has a real parent/child hierarchy rather than a flat list.
    entities: list[Entity] = []
    for i in range(spec.entities):
        eid = spec.account_id * 10 + i + 1
        entities.append(
            Entity(
                entity_id=eid,
                account_id=spec.account_id,
                name=spec.name if i == 0 else f"{spec.name} Subsidiary {i}",
                federal_tax_id=f"{spec.account_id}{i:02d}0001"[-9:].rjust(9, "0"),
                parent_entity_id=None if i == 0 else spec.account_id * 10 + 1,
                fiscal_year_rules_id=fiscal_rule.fiscal_year_rules_id,
                inception_date=date(2015, 1, 1),
            )
        )

    # Places, addresses and worksites.
    state_county_zips: list[StateCountyZip] = []
    scz_lookup: dict[tuple[str, str], int] = {}
    next_scz = spec.account_id * 100
    for st in spec.states:
        for county, zip_code, _city in _PLACES[st]:
            next_scz += 1
            state_county_zips.append(
                StateCountyZip(
                    state_county_zip_id=next_scz,
                    state_abbr=st,
                    state_name=st,
                    county_name=county,
                    zip_code=zip_code,
                )
            )
            scz_lookup[(st, county)] = next_scz

    addresses: list[Address] = []
    locations: list[Location] = []
    for i in range(spec.worksites):
        st = spec.states[i % len(spec.states)]
        county, zip_code, city = _PLACES[st][i % len(_PLACES[st])]
        addr_id = spec.account_id * 100 + i + 1
        addresses.append(
            Address(
                address_id=addr_id,
                street_address_1=f"{200 + i * 7} Commerce Drive",
                city_name=city,
                state_county_zip_id=scz_lookup[(st, county)],
                zip_code_original=zip_code,
                state_original=st,
            )
        )
        # One worksite opens part-way through the window where the spec asks for
        # it: a site with no early payroll is not a site with missing data. It
        # opens in the fourth year, alongside Ironbridge's step change.
        opens = (
            _shift_years(spec.fiscal_begin, 3) + timedelta(days=45)
            if spec.mid_year_worksite_opens and i == spec.worksites - 1
            else date(2015, 1, 1)
        )
        locations.append(
            Location(
                location_id=addr_id,
                account_id=spec.account_id,
                entity_id=entities[i % len(entities)].entity_id,
                location_name=f"{city} {'DC' if i % 3 == 0 else 'Site'} {i + 1}",
                client_location_id=f"{st}-{i + 1:03d}",
                address_id=addr_id,
                open_date=opens,
            )
        )

    pay_codes = [
        PayCode(
            pay_code_id=spec.account_id * 10 + i + 1,
            account_id=spec.account_id,
            pay_code=code,
            description=desc,
            is_futa=futa,
        )
        for i, (code, desc, futa) in enumerate(_PAY_CODES)
    ]
    regular_code_id = pay_codes[0].pay_code_id

    pay_frequencies = [
        PayFrequency(pay_frequency_id=k, name=v) for k, v in sorted(_PAY_FREQUENCY_LABELS.items())
    ]

    weeks_per_period = spec.period_days / 7.0
    payroll: list[Payroll] = []
    payroll_id = spec.account_id * 1_000_000
    next_employee_id = spec.account_id * 100_000

    # The workforce, carried across years. Growth hires onto the end of this
    # list; contraction terminates from it. Nobody is resurrected — a recovery
    # hires new people, which is both realistic and the thing that makes the
    # high-water mark meaningful.
    active: list[_Worker] = []
    all_workers: list[_Worker] = []

    def _hire(count: int, when: date, tax_year: int, open_sites: list[int]) -> None:
        nonlocal next_employee_id
        for _ in range(count):
            part_time = rng.random() < spec.part_time_share
            worker = _Worker(
                employee_id=next_employee_id,
                location_index=rng.choice(open_sites),
                part_time=part_time,
                # Part-timers cluster just under the 35-hour floor, so the "close
                # to qualifying" view has real cases; full-timers sit clear of it.
                base_hours=rng.uniform(26.0, 34.6) if part_time else rng.uniform(36.0, 44.0),
                base_rate=round(rng.uniform(_BASE_HOURLY_MIN, _BASE_HOURLY_MAX), 2),
                job_title=_JOB_TITLES[next_employee_id % len(_JOB_TITLES)],
                hired_on=when,
                first_year=tax_year,
            )
            next_employee_id += 1
            active.append(worker)
            all_workers.append(worker)

    for year_index, tax_year in enumerate(spec.generated_years):
        fy_begin = _shift_years(spec.fiscal_begin, year_index)
        fy_end = _shift_years(spec.fiscal_end, year_index)
        periods = _pay_periods(fy_begin, fy_end, spec.period_days)
        current = tax_year == CURRENT_TAX_YEAR
        if current:
            # The open year exists only up to the checkpoint: a period is here
            # if it has been PAID by then, and nothing after has happened yet.
            periods = [p for p in periods if p[2] <= CURRENT_YEAR_THROUGH]
            if not periods:
                continue
        open_sites = [i for i, loc in enumerate(locations) if loc.open_date <= fy_end]

        multiplier = spec.current_year_trajectory if current else spec.trajectory[year_index]
        target = max(1, round(spec.base_employees * multiplier))

        # Churn and trajectory are handled separately, and the ORDER OF HIRING
        # MATTERS more than it looks. Average Headcount is a mean of monthly
        # counts, so a replacement hired in January for someone who left in June
        # inflates the average for five months and the trajectory stops being
        # legible. Replacements therefore start when the leaver leaves; only the
        # deliberate growth is hired at the year's open, where a full-year
        # presence is what the trajectory is asserting.
        if year_index > 0 and spec.annual_attrition > 0 and active:
            leavers = rng.sample(active, k=min(len(active), round(len(active) * spec.annual_attrition)))
            for worker in leavers:
                left_at = periods[rng.randrange(len(periods))]
                worker.terminated_on = left_at[1]
                worker.last_year = tax_year
                active.remove(worker)
                # Backfill the seat the day after it opens.
                _hire(1, left_at[1] + timedelta(days=1), tax_year, open_sites)

        if len(active) > target:
            cut = rng.sample(active, k=len(active) - target)
            for worker in cut:
                # A reduction the trajectory called for applies from the year's
                # open, so the annual average reflects it rather than half of it.
                worker.terminated_on = periods[0][1]
                worker.last_year = tax_year
                active.remove(worker)
        elif len(active) < target:
            _hire(target - len(active), fy_begin, tax_year, open_sites)

        # Wages compound from the base year. Where this trails the statutory
        # floor's own growth, employees fall out of eligibility without anyone
        # losing a job — which is the point for Northwind and Halloway.
        wage_factor = (1.0 + spec.annual_wage_growth) ** year_index

        for worker in list(active) + [w for w in all_workers if w.last_year == tax_year]:
            home = locations[worker.location_index]
            rate = Decimal(str(round(worker.base_rate * wage_factor, 2)))

            for pps, ppe, paid in periods:
                if home.open_date and pps < home.open_date:
                    continue
                if worker.hired_on > ppe:
                    continue
                if worker.terminated_on and pps > worker.terminated_on:
                    continue

                # Week-to-week variation, so a denominator is not a constant.
                hours = Decimal(str(round(worker.base_hours * weeks_per_period * rng.uniform(0.9, 1.08), 2)))
                wages = (hours * rate).quantize(Decimal("0.01"))

                payroll_id += 1
                payroll.append(
                    Payroll(
                        payroll_id=payroll_id,
                        account_id=spec.account_id,
                        employee_id=worker.employee_id,
                        entity_id=home.entity_id,
                        location_id=home.location_id,
                        worksite_location_id=home.location_id,
                        pay_frequency_id=spec.pay_frequency_id,
                        pay_period_start=pps,
                        pay_period_end=ppe,
                        pay_date=paid,
                        hours=hours,
                        wages=wages,
                        hourly_rate=rate,
                        is_full_time=not worker.part_time,
                        is_salaried=False,
                        pay_code_id=regular_code_id,
                        client_employee_id=f"E{worker.employee_id}",
                        create_date=_loaded_at(tax_year),
                        modify_date=_loaded_at(tax_year),
                    )
                )

    for opening in spec.openings:
        _apply_opening(opening, locations, all_workers, active, payroll)
    for hiring in spec.hirings:
        _apply_hiring(spec, hiring, locations, all_workers, active, payroll)
    for departure in spec.departures:
        _apply_departure(spec, departure, locations, all_workers, active, payroll)

    employments = [
        Employment(
            employment_id=worker.employee_id,
            employee_id=worker.employee_id,
            hire_location_id=locations[worker.location_index].location_id,
            current_location_id=locations[worker.location_index].location_id,
            status="Terminated" if worker.terminated_on else "Active",
            job_title=worker.job_title,
            hire_date=worker.hired_on,
            start_date=worker.hired_on,
            termination_date=worker.terminated_on,
            termination_reason="Voluntary" if worker.terminated_on else None,
            employment_type="PT" if worker.part_time else "FT",
            wage_type="H",
        )
        for worker in all_workers
    ]

    account = Account(
        account_id=spec.account_id,
        account_eid=spec.account_id,
        name=spec.name,
        billing_state=spec.states[0],
        billing_city=_PLACES[spec.states[0]][0][2],
        billing_postal_code=_PLACES[spec.states[0]][0][1],
        actual_number_of_employees=len(active),
        external_name=spec.name,
        industry_type_id=spec.industry_type_id,
    )

    return SourceDataset(
        account=account,
        entities=entities,
        locations=locations,
        addresses=addresses,
        state_county_zips=state_county_zips,
        employments=employments,
        pay_codes=pay_codes,
        pay_frequencies=pay_frequencies,
        fiscal_year_rules=[fiscal_rule],
        payroll=payroll,
    )


def _site_index(spec: SyntheticClientSpec, locations: list[Location], site: str) -> int:
    index = next(
        (i for i, loc in enumerate(locations) if loc.client_location_id == site), None,
    )
    if index is None:
        raise ValueError(f"{spec.name}: no worksite {site}")
    return index


def _year_periods(spec: SyntheticClientSpec, tax_year: int) -> list[tuple[date, date, date]]:
    """A generated year's pay periods, trimmed to the checkpoint for the open year."""
    index = spec.generated_years.index(tax_year)
    periods = _pay_periods(
        _shift_years(spec.fiscal_begin, index), _shift_years(spec.fiscal_end, index), spec.period_days,
    )
    if tax_year == CURRENT_TAX_YEAR:
        periods = [p for p in periods if p[2] <= CURRENT_YEAR_THROUGH]
    return periods


def _apply_opening(
    opening: DemoOpening,
    locations: list[Location],
    all_workers: list[_Worker],
    active: list[_Worker],
    payroll: list[Payroll],
) -> None:
    """The site did not exist before `opens`: its earlier rows and leavers go."""
    from dataclasses import replace

    index = next(
        (i for i, loc in enumerate(locations) if loc.client_location_id == opening.site), None,
    )
    if index is None:
        raise ValueError(f"no worksite {opening.site}")
    site = locations[index]
    locations[index] = replace(site, open_date=opening.opens)
    payroll[:] = [
        p for p in payroll
        if not (p.location_id == site.location_id and p.pay_period_start < opening.opens)
    ]
    for worker in [w for w in all_workers if w.location_index == index]:
        if worker.terminated_on is not None and worker.terminated_on < opening.opens:
            # Left before the site opened, so was never employed there at all.
            all_workers.remove(worker)
            if worker in active:
                active.remove(worker)
        elif worker.hired_on < opening.opens:
            # Staff the site opened with.
            worker.hired_on = opening.opens
            worker.first_year = opening.opens.year


def _apply_hiring(
    spec: SyntheticClientSpec,
    hiring: DemoHiring,
    locations: list[Location],
    all_workers: list[_Worker],
    active: list[_Worker],
    payroll: list[Payroll],
) -> None:
    """Add `count` full-timers at one site from the open of `tax_year`."""
    if hiring.tax_year not in spec.generated_years:
        raise ValueError(f"{spec.name}: hiring year {hiring.tax_year} is not generated")
    index = _site_index(spec, locations, hiring.site)
    home = locations[index]
    first = spec.generated_years.index(hiring.tax_year)
    taken = {w.employee_id for w in all_workers}
    next_payroll = max(p.payroll_id for p in payroll) + 1
    hours = Decimal(str(round(hiring.weekly_hours * spec.period_days / 7.0, 2)))
    regular = spec.account_id * 10 + 1
    for n in range(hiring.count):
        employee_id = spec.account_id * 100_000 + _STORY_EMPLOYEE_OFFSET + len(
            [w for w in all_workers if w.employee_id >= spec.account_id * 100_000 + _STORY_EMPLOYEE_OFFSET]
        )
        if employee_id in taken:
            raise ValueError(f"{spec.name}: story employee id {employee_id} is already taken")
        worker = _Worker(
            employee_id=employee_id, location_index=index, part_time=False,
            base_hours=hiring.weekly_hours, base_rate=hiring.hourly_rate,
            job_title=_JOB_TITLES[0], hired_on=_shift_years(spec.fiscal_begin, first),
            first_year=hiring.tax_year,
        )
        all_workers.append(worker)
        active.append(worker)
        for offset, tax_year in enumerate(spec.generated_years[first:]):
            rate = Decimal(str(round(hiring.hourly_rate * (1.0 + spec.annual_wage_growth) ** offset, 2)))
            for pps, ppe, paid in _year_periods(spec, tax_year):
                payroll.append(
                    Payroll(
                        payroll_id=next_payroll,
                        account_id=spec.account_id,
                        employee_id=employee_id,
                        entity_id=home.entity_id,
                        location_id=home.location_id,
                        worksite_location_id=home.location_id,
                        pay_frequency_id=spec.pay_frequency_id,
                        pay_period_start=pps,
                        pay_period_end=ppe,
                        pay_date=paid,
                        hours=hours,
                        wages=(hours * rate).quantize(Decimal("0.01")),
                        hourly_rate=rate,
                        is_full_time=True,
                        is_salaried=False,
                        pay_code_id=regular,
                        client_employee_id=f"E{employee_id}",
                        create_date=_loaded_at(tax_year),
                        modify_date=_loaded_at(tax_year),
                    )
                )
                next_payroll += 1


def _apply_departure(
    spec: SyntheticClientSpec,
    departure: DemoDeparture,
    locations: list[Location],
    all_workers: list[_Worker],
    active: list[_Worker],
    payroll: list[Payroll],
) -> None:
    """Terminate the named number of counting full-timers at one site."""
    if departure.tax_year not in spec.generated_years:
        raise ValueError(f"{spec.name}: departure year {departure.tax_year} is outside the window")
    site_index = _site_index(spec, locations, departure.site)

    year_index = spec.generated_years.index(departure.tax_year)
    fy_begin = _shift_years(spec.fiscal_begin, year_index)
    fy_end = _shift_years(spec.fiscal_end, year_index)
    wage_factor = (1.0 + spec.annual_wage_growth) ** year_index
    # Clear of Georgia's TY2025 $680 floor even on a short week (the generator
    # varies hours by 0.9-1.08), so a leaver was certainly a counted job.
    safe_weekly = 720.0

    candidates = sorted(
        (
            w for w in all_workers
            if w.location_index == site_index
            and not w.part_time
            # On payroll from the year's open, so every month before they
            # leave was a counted month.
            and w.hired_on <= fy_begin
            and (w.terminated_on is None or w.terminated_on > fy_end)
            and w.base_hours * 0.9 * w.base_rate * wage_factor >= safe_weekly
        ),
        key=lambda w: w.employee_id,
    )
    needed = sum(count for _, count in departure.leavers_by_month)
    if len(candidates) < needed:
        raise ValueError(
            f"{spec.name}: {departure.site} has {len(candidates)} counting full-timers, "
            f"{needed} asked to leave"
        )

    pay_ends = sorted({
        p.pay_period_end for p in payroll
        if p.location_id == locations[site_index].location_id
    })
    leaving = iter(candidates)
    gone: dict[int, date] = {}
    for month, count in departure.leavers_by_month:
        # Paid through the first period that ends in the leaving month, so the
        # previous month's measuring date still counts them and this month's
        # does not. Cutting at the last period BEFORE the 1st lost them a month
        # early.
        opens = date(departure.tax_year, month, 1)
        last_end = min(end for end in pay_ends if end >= opens)
        for _ in range(count):
            worker = next(leaving)
            worker.terminated_on = last_end
            worker.last_year = departure.tax_year
            if worker in active:
                active.remove(worker)
            gone[worker.employee_id] = last_end

    # Same rule the generator applies: no period that starts after the leave date.
    payroll[:] = [
        p for p in payroll
        if p.employee_id not in gone or p.pay_period_start <= gone[p.employee_id]
    ]


def build_all_synthetic() -> list[SourceDataset]:
    """Every synthetic client, in a stable order."""
    return [build_synthetic_dataset(spec) for spec in SYNTHETIC_CLIENTS]
