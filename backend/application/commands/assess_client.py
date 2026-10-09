"""Run the engine over a client's payroll and record what it found.

A **command**: it changes what the business believes. Each assessed
programme-year is written to the claim store with the actor who ran it, the
statute version it was priced under, and the run that produced it.

Assessment is append-only. Re-assessing does not overwrite a prior belief — the
earlier record and the run behind it stay readable, because a recalculation is
new evidence, not a new decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from application.mediator import Command


@dataclass(frozen=True)
class AssessClientCommand(Command):
    """Assess one client's programme-years and record the outcome.

    `tax_years` empty means every year present in the payroll. Years with no
    authored rule pack are **declined by name** rather than estimated, and the
    result reports them so a caller can describe coverage honestly instead of
    presenting a partial sweep as a complete one.
    """

    client_id: int = 0
    program_code: str | None = None
    tax_years: tuple[int, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.client_id <= 0:
            raise ValueError("client_id is required and must be positive")


class ClientHasNoPayroll(LookupError):
    """No payroll for this client in the active data source.

    Distinct from 'the dataset is missing'. A caller asking for client 42 needs
    to hear that client 42 has no rows, not that they should go generate
    fixtures — and must never silently receive another client's payroll.
    """


def handle_assess_client(command: AssessClientCommand) -> dict[str, Any]:
    from api._assess import assess_client
    from application.wiring import get_claim_repository as get_repository
    from infrastructure.payroll.pay_period_source import load_pay_periods

    rows = load_pay_periods(command.client_id)
    if not rows:
        raise ClientHasNoPayroll(
            f"No payroll for client {command.client_id} in the active data source."
        )

    # The repository is not optional here. `assess_client` accepts None and then
    # computes without persisting anything — a command that returns a plausible
    # result and writes nothing is the worst kind of silent failure, because the
    # caller has every reason to believe it worked.
    return assess_client(
        command.client_id,
        rows,
        program_code=command.program_code,
        tax_years=list(command.tax_years) or None,
        assessed_by=command.actor,
        repository=get_repository(),
    )
