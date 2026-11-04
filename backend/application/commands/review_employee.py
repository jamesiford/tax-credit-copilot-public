"""Record, or clear, a human validation annotation on one employee.

A command: it changes what the business holds about an employee's eligibility, and it
carries the person who decided. It declares no policy because the route is withheld
from the channel agent at the edge (`AGENT_FORBIDDEN_WRITES`), the same standing as
`AssessClientCommand`; the named exception is recorded in
`test_every_registered_command_declares_a_policy_or_is_named_open`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from application.employee_reviews import EMPLOYEE_REVIEWS
from application.mediator import Command


@dataclass(frozen=True)
class ReviewEmployeeCommand(Command):
    """`status` is validated | flagged | cleared; `cleared` removes the annotation."""

    employee_id: str = ""
    status: str = "validated"
    note: str | None = None


def handle_review_employee(command: ReviewEmployeeCommand) -> dict[str, Any]:
    if command.status == "cleared":
        EMPLOYEE_REVIEWS.pop(command.employee_id, None)
        return {"ok": True, "review": None}
    entry = {
        "employee_id": command.employee_id,
        "status": command.status,
        "note": command.note,
        "reviewer": command.actor,
        "reviewed_at": date.today().isoformat(),
    }
    EMPLOYEE_REVIEWS[command.employee_id] = entry
    return {"ok": True, "review": entry}
