"""Human validation annotations on an employee's eligibility.

In-memory, and it resets on restart; production persists to the audit store. It lives
in the application layer because the derivation read attaches the annotation to what
it returns and the review command writes it, and neither should import a router to
reach the other.
"""
from __future__ import annotations

from typing import Any

EMPLOYEE_REVIEWS: dict[str, dict[str, Any]] = {}


def reset_employee_reviews() -> None:
    """Test hook — clear the in-memory employee-review annotations."""
    EMPLOYEE_REVIEWS.clear()
