"""Seeded claims must describe themselves as illustrative.

The `claimed` side of every coverage cell is invented. We had no prior filing
for any account, so the figures exist only to give the matrix something to
compare `identified` against. The engine's side is real; this side is not.

That was fine until it reached a screen and a script as a statement of fact —
"they filed TY2023 through a prior provider and claimed $410,000" — which is
not something anybody told us. These tests keep the data self-describing so the
next person to read it cannot make the same mistake.
"""
from __future__ import annotations

from decimal import Decimal

from data.seed_claims import _ASSERTIONS
from domain.claims import Provenance


def test_every_seeded_claim_names_itself_illustrative():
    """The note reaches the screen as `filing_reference`."""
    for client_id, program, year, _claimed, note in _ASSERTIONS:
        assert "llustrative" in note, (
            f"{client_id} {program} TY{year} asserts {note!r} as fact"
        )


def test_no_seeded_claim_invents_a_filing_reference():
    """A form number or provider name reads as evidence we do not have."""
    forbidden = ("IT-CA", "Form ", "prior provider", "in-house", "Self-filed")
    for client_id, program, year, _claimed, note in _ASSERTIONS:
        for token in forbidden:
            assert token.lower() not in note.lower(), (
                f"{client_id} {program} TY{year} note {note!r} implies a real filing"
            )


def test_the_seeded_figures_are_the_ones_the_walkthrough_quotes():
    """If these move, the run of show and the guided tour are both wrong."""
    by_cell = {(c, p, y): amount for c, p, y, amount, _ in _ASSERTIONS}
    assert by_cell[(1001, "GA_JTC", 2023)] == Decimal("410000")
    assert by_cell[(2001, "GA_JTC", 2022)] == Decimal("95000")
    assert by_cell[(2003, "GA_JTC", 2024)] == Decimal("45535")


def test_seeding_never_records_a_claim_as_computed():
    """`client_asserted` is what drives the UNVERIFIED badge."""
    import inspect

    from data import seed_claims

    source = inspect.getsource(seed_claims.main)
    assert "Provenance.CLIENT_ASSERTED" in source
    assert "Provenance.COMPUTED" not in source
