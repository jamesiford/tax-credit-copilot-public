"""[L1] CALC-07 — frozen-base-year tranche + backfill engine tests."""
from __future__ import annotations

from tools.baseyear import compute_base_year_tranches


def _result(seq: dict[int, float], **kw):
    return compute_base_year_tranches(
        "GA", seq, base_year=2021, threshold=2, per_job_usd=3500, **kw
    )


def test_l1_calc07_frozen_base_not_rolling_prior_year():
    # Credit is measured against the FROZEN 2021 base, not the rolling prior year.
    r = _result({2021: 100, 2022: 105, 2023: 104})
    y2022 = next(y for y in r.years if y.year == 2022)
    y2023 = next(y for y in r.years if y.year == 2023)
    # 2023 nets against the 2021 base (104-100=4), NOT against 2022 (104-105).
    assert y2022.net_new == 5
    assert y2023.net_new == 4
    assert y2023.base_average_headcount == 100


def test_l1_calc07_credit_on_full_net_new_threshold_gates_not_subtracts():
    # The partner: "I go up to 105, I get credits on FIVE people" — full net-new, the
    # threshold only gates participation (it is not subtracted).
    r = _result({2021: 100, 2022: 105})
    y2022 = next(y for y in r.years if y.year == 2022)
    assert y2022.eligible_jobs == 5
    assert y2022.annual_credit_usd == 5 * 3500


def test_l1_calc07_below_threshold_year_claims_zero():
    r = _result({2021: 100, 2022: 101})  # net-new 1 < threshold 2
    y2022 = next(y for y in r.years if y.year == 2022)
    assert y2022.qualified is False
    assert y2022.eligible_jobs == 0
    assert y2022.annual_credit_usd == 0


def test_l1_calc07_backfill_recovers_after_dip():
    # The partner's stair-step: 100 -> 105 -> 104 -> 101(out) -> 103(backfill).
    r = _result({2021: 100, 2022: 105, 2023: 104, 2024: 101, 2025: 103})
    by_year = {y.year: y for y in r.years}
    assert by_year[2024].qualified is False        # 101-100=1 < 2 -> kicked out
    assert by_year[2025].qualified is True          # 103-100=3 >= 2 -> back in
    assert by_year[2025].backfilled is True          # re-qualified after a dip
    assert by_year[2025].eligible_jobs == 3


def test_l1_calc07_tranche_events_open_on_new_high_water():
    r = _result({2021: 100, 2022: 105, 2023: 104})
    # A fresh creation event (new high-water) opens in 2022 only; 2023 dipped.
    creation_years = [e.creation_year for e in r.tranche_events]
    assert 2022 in creation_years
    assert 2023 not in creation_years
    ev = next(e for e in r.tranche_events if e.creation_year == 2022)
    assert ev.tranche_years == 5
    assert len(ev.installments) == 5


def test_l1_calc07_high_water_mark_override():
    # A long-present GA employer carries a persistent high-water baseline (DISC-9).
    r = _result({2021: 100, 2022: 130}, high_water_mark_override=150)
    y2022 = next(y for y in r.years if y.year == 2022)
    # 130 is still below the seeded 150 HWM -> no fresh creation event.
    assert y2022.new_jobs_created == 0
    assert r.high_water_mark_overridden is True


def test_l1_calc07_base_average_override_wipes_base():
    r = _result({2021: 100, 2022: 105}, base_average_override=80)
    y2022 = next(y for y in r.years if y.year == 2022)
    assert y2022.base_average_headcount == 80
    assert y2022.net_new == 25
    assert r.base_year_overridden is True


def test_l1_calc07_to_dict_carries_traceability_tags():
    d = _result({2021: 100, 2022: 105}).to_dict()
    assert d["_roadmap_tag"] == "L1"
    assert d["_story"] == "CALC-07"
    assert d["_disc_ref"] == "DISC-8"
    assert d["total_annual_credit_usd"] > 0


# --- statute is versioned by tax year [ADR-005] ------------------------------
#
# Georgia has held $3,500 per job and a 2-job threshold across every authored
# year, so a per-year defect is INVISIBLE against the live packs. These pass
# rates that differ on purpose: without them the engine could go back to reading
# one year's statute for a six-year series and nothing would fail.


def _varying(seq: dict[int, float], rates: dict[int, float], **kw):
    return compute_base_year_tranches(
        "GA", seq, base_year=2021, threshold=2, per_job_usd=3500,
        benefit_by_year={
            year: {"threshold": 2, "per_job_usd": rate} for year, rate in rates.items()
        },
        **kw,
    )


def test_each_year_is_priced_at_its_own_rate():
    r = _varying(
        {2021: 100, 2022: 105, 2023: 110},
        {2022: 3500, 2023: 4000},
    )
    y2022 = next(y for y in r.years if y.year == 2022)
    y2023 = next(y for y in r.years if y.year == 2023)

    assert y2022.annual_credit_usd == 5 * 3500
    # 10 net-new at the LATER year's rate, not the base year's.
    assert y2023.annual_credit_usd == 10 * 4000


def test_the_year_carries_the_rate_that_priced_it():
    """On the year, not the series: six years can span six rates, and a single
    scalar reports whichever one happened to be read."""
    r = _varying({2021: 100, 2022: 105, 2023: 110}, {2022: 3500, 2023: 4000})
    assert {y.year: y.per_job_usd for y in r.years} == {2022: 3500.0, 2023: 4000.0}
    assert next(y for y in r.years if y.year == 2023).to_dict()["per_job_usd"] == 4000.0


def test_a_tranche_holds_the_rate_of_the_year_it_opened():
    """The rate attaches to the job when it is created. A later year's rate must
    not reprice a window already running."""
    r = _varying({2021: 100, 2022: 105, 2023: 110}, {2022: 3500, 2023: 9999})
    opened_2022 = next(e for e in r.tranche_events if e.creation_year == 2022)
    assert opened_2022.per_job_usd == 3500


def test_a_year_threshold_gates_that_year_only():
    r = compute_base_year_tranches(
        "GA", {2021: 100, 2022: 103, 2023: 103},
        base_year=2021, threshold=2, per_job_usd=3500,
        benefit_by_year={
            2022: {"threshold": 2, "per_job_usd": 3500},
            2023: {"threshold": 5, "per_job_usd": 3500},
        },
    )
    assert next(y for y in r.years if y.year == 2022).qualified is True
    # Same 3 net-new, but 2023 asks for 5.
    assert next(y for y in r.years if y.year == 2023).qualified is False


def test_a_year_absent_from_the_map_falls_back_to_the_scalar_not_a_neighbour():
    """Inheriting statute across years is what year packs exist to prevent."""
    r = _varying({2021: 100, 2022: 105, 2023: 110}, {2023: 4000})
    assert next(y for y in r.years if y.year == 2022).per_job_usd == 3500.0


def test_no_map_at_all_behaves_exactly_as_before():
    """The scalar form is the fallback, and every existing caller uses it."""
    plain = _result({2021: 100, 2022: 105})
    mapped = _varying({2021: 100, 2022: 105}, {2022: 3500})
    assert plain.years[0].annual_credit_usd == mapped.years[0].annual_credit_usd
