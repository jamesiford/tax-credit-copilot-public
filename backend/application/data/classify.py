"""Who may see a result: the person asking, or the person and the model. [CH-16b]

This is the privacy design in one function. Sensitivity lives on the model's columns and
describes the *raw* value, so what matters is what a particular query returns:

- a query that selects an `employee_level` column (a record token, one person's hours or
  wages, a monthly One/Zero cell) returns person-level values, and
- a query with no aggregate over an employee-level dataset returns its rows as they are.

Either way the rows are `user` audience: delivered to the person, never sent to a model.
An aggregate over a group (a count by location, an average by month) is `both`: the model
may see it and narrate it. Which facts a user-audience result may still contribute is
decided in CH-16d, from `employee_level_labels`.
"""
from __future__ import annotations

from application.data.plan import Plan
from application.data.semantic_model import Sensitivity

USER = "user"
BOTH = "both"


def employee_level_labels(plan: Plan) -> tuple[str, ...]:
    """Result columns whose raw values are person-level: what a model must not be handed."""
    return tuple(c.label for c in plan.result_columns if c.kind == "dimension" and c.sensitivity is Sensitivity.EMPLOYEE_LEVEL)


def result_audience(plan: Plan) -> str:
    """`user` when the result carries person-level values, `both` for an aggregate a model may see."""
    if employee_level_labels(plan):
        return USER
    if plan.dataset.employee_level and not plan.measures:
        return USER
    return BOTH
