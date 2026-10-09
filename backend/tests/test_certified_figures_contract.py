"""The certified figures are defined twice on purpose. This proves they agree.

`tests/certified.py` holds them as literals so a rule-pack edit cannot move the
gate along with the engine. `rules/methodology/certified-figures.json` is the
production-readable copy, needed because the runtime equivalence gate in
`ReferenceWorkspaceService` refuses to serve a lakehouse-sourced run that does not
reproduce them — and production code may not import from `tests/`.

Two copies of a number is normally a defect. It is safe only while something
fails loudly when they diverge, which is this module.
"""
from __future__ import annotations

from certified import (
    CERTIFIED_EMPLOYEES,
    CERTIFIED_MIN_MAX_ELIGIBLE,
    CERTIFIED_PAY_PERIOD_ELIGIBLE,
    CERTIFIED_PROGRAM_CODE,
    CERTIFIED_TAX_YEAR,
)
from tools.reference_source import _CERTIFIED_FIGURES, certified_figures


def test_production_copy_matches_the_test_literals():
    assert certified_figures() == {
        "employees_evaluated": CERTIFIED_EMPLOYEES,
        "min_max_eligible": CERTIFIED_MIN_MAX_ELIGIBLE,
        "pay_period_eligible": CERTIFIED_PAY_PERIOD_ELIGIBLE,
    }


def test_the_contract_names_the_programme_and_year_it_was_certified_under():
    """A count without the statute it was computed under is not a certification."""
    import json

    payload = json.loads(_CERTIFIED_FIGURES.read_text(encoding="utf-8"))
    assert payload["program_code"] == CERTIFIED_PROGRAM_CODE
    assert payload["tax_year"] == CERTIFIED_TAX_YEAR
