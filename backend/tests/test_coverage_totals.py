"""Row totals over a coverage grid.

These moved here from `frontend/src/lib/coverage.js`, where the account grid
reduced `opportunity_usd` and `variance_usd` across each row in the browser.
Every other dollar on that screen arrives summed from SQL as a `Decimal`; that
one row was adding cent-accurate figures as IEEE 754 doubles.

The rule the frontend tests protected comes with it: a row NEVER nets an
opportunity against an exposure.
"""
from __future__ import annotations

from decimal import Decimal

from domain.claims import ClaimStatus, ProgramClaim
from domain.coverage import totals, totals_by_program


def _opportunity(
    *, program_code: str = "GA_JTC", tax_year: int = 2023, identified: str = "40000"
) -> ProgramClaim:
    """Assessed, nothing claimed, something to claim — an UNCLAIMED cell."""
    return ProgramClaim(
        claim_id=f"{program_code}-{tax_year}-opp",
        client_id=1001,
        entity_id=None,
        program_code=program_code,
        tax_year=tax_year,
        status=ClaimStatus.ASSESSED,
        identified_usd=Decimal(identified),
        claimed_usd=Decimal("0"),
    )


def _exposure(
    *, program_code: str = "GA_JTC", tax_year: int = 2023, claimed: str = "40000"
) -> ProgramClaim:
    """Claimed more than was identified — an OVER_CLAIMED cell."""
    return ProgramClaim(
        claim_id=f"{program_code}-{tax_year}-exp",
        client_id=1001,
        entity_id=None,
        program_code=program_code,
        tax_year=tax_year,
        status=ClaimStatus.CLAIMED,
        identified_usd=Decimal("0"),
        claimed_usd=Decimal(claimed),
    )


class TestARowNeverNets:
    def test_opportunity_and_exposure_are_reported_separately(self):
        """Netted, both read zero and the row looks like nothing to discuss."""
        result = totals([
            _opportunity(tax_year=2022, identified="40000"),
            _exposure(tax_year=2023, claimed="40000"),
        ])
        assert Decimal(result["opportunity_usd"]) == Decimal("40000")
        assert Decimal(result["exposure_usd"]) == Decimal("40000")

    def test_an_exposure_is_counted_as_well_as_summed(self):
        assert totals([_exposure()])["exposure_cells"] == 1


class TestPerProgrammeTotals:
    def test_each_programme_totals_only_its_own_rows(self):
        by_program = totals_by_program([
            _opportunity(program_code="GA_JTC", tax_year=2022, identified="40000"),
            _opportunity(program_code="GA_JTC", tax_year=2023, identified="60000"),
            _opportunity(program_code="SC_JTC", tax_year=2023, identified="10000"),
        ])

        assert set(by_program) == {"GA_JTC", "SC_JTC"}
        assert Decimal(by_program["GA_JTC"]["opportunity_usd"]) == Decimal("100000")
        assert Decimal(by_program["SC_JTC"]["opportunity_usd"]) == Decimal("10000")

    def test_the_rows_sum_to_the_whole_grid(self):
        """A row total that disagrees with the grid total is the bug this
        replaced: two additions of the same money, one of them in a float."""
        rows = [
            _opportunity(program_code="GA_JTC", tax_year=2022, identified="40000.33"),
            _opportunity(program_code="GA_JTC", tax_year=2023, identified="60000.33"),
            _opportunity(program_code="SC_JTC", tax_year=2023, identified="10000.34"),
        ]
        summed = sum(
            (Decimal(t["opportunity_usd"]) for t in totals_by_program(rows).values()),
            Decimal("0"),
        )
        assert summed == Decimal(totals(rows)["opportunity_usd"])

    def test_money_is_a_string_so_json_cannot_round_it(self):
        rows = [_opportunity(identified="12345678.91")]
        assert totals_by_program(rows)["GA_JTC"]["opportunity_usd"] == "12345678.91"

    def test_no_claims_is_an_empty_map_not_a_zero_row(self):
        assert totals_by_program([]) == {}
