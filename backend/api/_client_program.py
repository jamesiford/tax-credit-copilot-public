"""The two query parameters every per-client read shares: which client, and which program. [F04c.6]

A state can hold several programs, so a read that answers "for this state" has to be told which one. Both are optional on
the wire and read the same query names the endpoints always took (`account_id`) plus the new `program_code`, so this is a
refactor of the parameter list, not a change to the URL.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query


@dataclass(frozen=True)
class ClientProgram:
    """Which client and which program a read is for; either may be omitted."""

    account_id: int | None
    program_code: str | None


def client_program(
    account_id: int | None = Query(None, description="Client; defaults to the tenant"),
    program_code: str | None = Query(None, description="Program; needed when the state has several"),
) -> ClientProgram:
    return ClientProgram(account_id, program_code)
