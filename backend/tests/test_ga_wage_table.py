"""Georgia's published historical wage table, and how a missing year behaves.

Two things are under test here.

**The transcription.** `_GA_HISTORICAL_WAGE_TABLE` is typed out of a PDF by hand,
and a mistyped floor changes eligibility counts without changing anything that
looks wrong. The PDF's annualised column is a check digit, so the table validates
against itself.

**The refusal.** [ADR-005] statute is not inherited across years. A year Georgia
has not published must raise on a single-year path and be *declined by name* on a
multi-year sweep — never silently skipped, because a report that quietly omits a
year looks complete.

Historical note: TY2020/21/22 were once prototype placeholders of $566/$588/$612.
The published figures are $541/$589/$602. All three were wrong, and wrong in a
telling way — the invented series rose smoothly (+22, +24, +24) while the real one
does not (+48, +13, +34, +50, **-6**). Georgia's floor tracks its lowest-wage
county, and which county that is changes. Nothing here may be smoothed.
"""
from __future__ import annotations

from datetime import date

import pytest

from data.rules.materialise_years import (
    _GA_HISTORICAL_WAGE_TABLE,
    _GA_MIN_WEEKLY_HOURS,
    _WEEKS_PER_YEAR,
    _validate_wage_table,
)
from tools.credit_math import resolve_statutory_floors

# Spot values read straight off JTCHistoricalWages_Jul 2025.pdf. Independent of
# the module's own table so a bad edit there cannot silently agree with itself.
_PUBLISHED = {
    2019: ("Glascock", 511.0),
    2020: ("Glascock", 541.0),
    2021: ("Glascock", 589.0),
    2022: ("Glascock", 602.0),
    2023: ("Glascock", 636.0),   # the certified reference-dataset year
    2024: ("Taliaferro", 686.0),
    2025: ("Taliaferro", 680.0),
}


def test_wage_table_validates_against_its_own_annualised_column():
    _validate_wage_table()


@pytest.mark.parametrize("tax_year,expected", sorted(_PUBLISHED.items()))
def test_resolved_floor_matches_the_published_table(tax_year, expected):
    county, weekly = expected
    floors = resolve_statutory_floors("GA_JTC", tax_year)

    assert floors.min_weekly_wages == weekly
    assert floors.min_weekly_hours == _GA_MIN_WEEKLY_HOURS
    assert floors.basis["lowest_wage_county"] == county
    assert floors.basis["dol_report_year"] == tax_year - 1
    assert floors.basis["annualized_wage_usd"] == weekly * _WEEKS_PER_YEAR


def test_no_georgia_year_is_an_unverified_placeholder():
    """Every authored GA year traces to the published table, not to a guess."""
    for tax_year in _PUBLISHED:
        floors = resolve_statutory_floors("GA_JTC", tax_year)
        assert floors.prototype_verify is False, (
            f"TY{tax_year} is still marked _prototype_verify"
        )


def test_the_floor_is_not_monotonic():
    """TY2025 is $6 BELOW TY2024 — any 'floors only rise' assumption is wrong."""
    assert (
        _GA_HISTORICAL_WAGE_TABLE[2025][2] < _GA_HISTORICAL_WAGE_TABLE[2024][2]
    )


def test_unpublished_year_raises_rather_than_inheriting():
    """TY2027 is not authored at all, not even as a placeholder."""
    with pytest.raises(FileNotFoundError, match="tax year 2027"):
        resolve_statutory_floors("GA_JTC", 2027)


def test_ty2026_is_a_placeholder_and_says_so():
    """24 Sep 2026: built so the in-year story has a year to be in. The value is
    TY2025's carried forward, labelled; the county and annualised wage are
    None rather than a plausible guess. Replace from the DOL 2025 table."""
    floors = resolve_statutory_floors("GA_JTC", 2026)
    assert floors.prototype_verify is True
    assert floors.provenance["source"] == "placeholder"
    assert "PLACEHOLDER" in floors.provenance["note"]
    assert floors.basis["lowest_wage_county"] is None
    assert floors.basis["annualized_wage_usd"] is None
    assert floors.basis["dol_report_year"] == 2025
    assert floors.min_weekly_wages == _GA_HISTORICAL_WAGE_TABLE[2025][2], "carried forward, not invented"
    assert 2026 not in _GA_HISTORICAL_WAGE_TABLE, "a placeholder must never enter the published table"


def test_retroactive_scan_declines_uncovered_years_by_name(client):
    """One unpublished year must not take down the whole multi-year report.

    The years come from payroll, which runs past what any legislature has
    published. Declining by name is the honest middle ground between failing
    everything and quietly omitting a year so the output looks complete.
    """
    body = client.get("/api/onezero/retroactive/scan").json()

    assert body["tax_years_scanned"], "the covered years should still calculate"

    declined_years = {d["tax_year"] for d in body["declined_years"]}
    assert declined_years.isdisjoint(body["tax_years_scanned"])
    assert body["summary"]["declined_year_count"] == len(body["declined_years"])

    for entry in body["declined_years"]:
        assert entry["reason"] == "no_authored_statute"
        assert entry["states"], "a declined year must name which states"
        assert str(entry["tax_year"]) in entry["detail"]


@pytest.mark.xfail(
    reason=(
        "OPEN — needs the partner (PILOT-07). `fiscal_year_of` labels a fiscal year by "
        "the year it ENDS; Georgia reg 110-9-1-.02(1)(a) labels a tax year by the "
        "year it BEGINS. They agree for calendar-year filers, which is why this "
        "has been invisible. The certified reference run is unaffected: it uses "
        "BA-01's explicit window and never calls fiscal_year_of. "
        "The statutory path now lives in domain/calculation/fiscal.py, which "
        "resolves a window from the client's own EntityFiscalYearRules and takes "
        "the labelling convention from the rule pack's `tax_year_convention` "
        "(GA = `begins`, flagged unconfirmed). This helper keeps the BUSINESS "
        "label and is deliberately left alone: changing it moves the month "
        "bucketing on every non-calendar client, and which reading Georgia "
        "intends is the partner's call, not ours. See tests/test_fiscal_window.py."
    ),
    strict=True,
)
def test_fiscal_year_label_matches_the_regulation():
    """A fiscal year beginning in April 2024 is Tax Year 2024, not 2025.

    The reference dataset agrees with the regulation, not with the engine: its
    BA-01 window opens 28 July 2023 and the whole project calls it TY2023.
    `fiscal_year_of` would call that same window FY2024, which would price it at
    TY2024's $686 rather than TY2023's $636.
    """
    from domain.calculation.onezero import fiscal_year_of

    # A March year-end filer's FY2024 runs Apr 2024 - Mar 2025.
    assert fiscal_year_of(date(2024, 9, 30), 3) == 2024

    # The reference dataset's own window, by its own label.
    assert fiscal_year_of(date(2023, 11, 15), 8) == 2023


def test_fiscal_year_label_disagreement_is_confined_to_non_calendar_filers():
    """Pins the blast radius of the open question above.

    Calendar-year filers are unaffected, so the disagreement cannot reach a
    client on a December year-end no matter how it is resolved.
    """
    from domain.calculation.onezero import fiscal_year_of

    for month in (1, 6, 12):
        assert fiscal_year_of(date(2023, month, 15), 12) == 2023

    # And it does currently disagree for the others, which is why the xfail
    # above is strict: when someone fixes it, this test must be revisited too.
    assert fiscal_year_of(date(2024, 9, 30), 3) == 2025
