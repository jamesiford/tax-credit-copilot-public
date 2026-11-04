"""Why a One/Zero read cannot be answered, in terms a router can map to a status code."""
from __future__ import annotations


class OneZeroNotFound(LookupError):
    """The thing asked about does not exist: a rule pack, an employee's rows, a benchmark."""
