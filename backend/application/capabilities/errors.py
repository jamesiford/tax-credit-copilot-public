"""Typed failures a capability can raise.

A capability never raises `HTTPException`: it may be driven by the chat, the
channel gateway or a notebook, and only the router knows what a status code is.
Each error carries a message safe to show a reader, because the statute messages
("declined by name") are exactly the text the user needs.
"""
from __future__ import annotations


class CapabilityError(Exception):
    """Base class. `str(error)` is safe to show to the person who asked."""


class ClientNotFound(CapabilityError):
    """The client is not in the book, or the book could not be read."""


class YearNotAuthored(CapabilityError):
    """No statute is authored for this programme-year.

    Carries the existing "declined by name" message [ADR-005]. A year is never
    estimated from a neighbour, so this is a real gap in coverage, not a miss.
    """


class NotCalculated(CapabilityError):
    """No run has reached this client-year, or nothing is recorded for the cell.

    Not a zero. "Nobody qualifies" and "we have not looked" are different
    statements and only one of them is about the client's payroll.
    """


class ClaimNotFound(CapabilityError):
    """A change was asked of a claim cell nobody has recorded, so there is nothing to change.

    A 404, not a crash: the cell is simply not there. Distinct from `NotCalculated`, which says a
    figure has not been produced yet; here the request names a record that does not exist.
    """


class InvalidArguments(CapabilityError):
    """The arguments are well-formed but not acceptable (a lever out of range)."""


class Ambiguous(CapabilityError):
    """The question does not name one client. `candidates` lists the choices."""

    def __init__(self, message: str, candidates: tuple[dict, ...] = ()) -> None:
        super().__init__(message)
        self.candidates = candidates
