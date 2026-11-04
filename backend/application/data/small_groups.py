"""Small-group suppression: an aggregate over people must not describe one person. [RM-01, ADR-009]

A count, sum or average over an employee-level dataset is only as anonymous as the group behind
it. The average wages at a worksite with one employee IS that employee's wages, and the model
(or Copilot Cowork's model, which reads whatever text a tool returns) can narrate it. So the data
service enforces a minimum group size K before anything is projected into a lane:

- **The group's size is the number of distinct PEOPLE in it**, not rows (a pay-period dataset holds
  many rows per person). The statement carries one extra column, `_group_size`, computed from the
  dataset's `person_key`, and the service removes it before anyone sees the result.
- **A group below K is suppressed, never altered.** Merging into an "other" bucket would need the
  suppressed groups' averages and distinct counts re-derived, which is not computable from the
  groups' own results; so the group is left out and the result REPORTS how many were, in its
  provenance and notes. That is what reconciles this rule with the product's exactness: every
  figure shown is exact, and the count of what is not shown is exact too.
- **An ungrouped aggregate is one group**: an average over a filter that isolates two people is a
  group of two and is withheld the same way.
- **A group-by whose every group holds one person is refused** (`groups_are_individuals`): it lists
  individuals with an aggregate's clothes on.
- **K is a floor, not a preference.** The default is 5, `DATA_MIN_GROUP_SIZE` may raise it, and no
  setting lowers it below 2 (`QueryLimits` refuses to be built with less).
- **A writer is exempt** (they may already read the client's employee rows), as is a result over a
  dataset that is not employee-level: its grain is already a worksite or a year.

Suppression is NOT protection against differencing (two queries whose groups differ by one
person); KNOWN-LIMITATIONS says so.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.data.errors import GroupsAreIndividuals
from application.data.executor import Rows
from application.data.plan import Plan
from application.data.semantic_model import SemanticModel

DEFAULT_MIN_GROUP_SIZE = 5
MIN_GROUP_SIZE_FLOOR = 2
#: The hidden trailing column of a statement that counts people. Not a model column: nobody can ask for it.
SIZE_LABEL = "_group_size"
WRITER = "writer"


@dataclass(frozen=True, slots=True)
class SmallGroupReport:
    """What the rule did to one result: stated in its provenance, so nobody has to infer it."""

    min_group_size: int
    applied: bool
    suppressed_groups: int = 0
    exempt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe form for the envelope's facts and the audit trail."""
        return {
            "min_group_size": self.min_group_size, "applied": self.applied,
            "suppressed_groups": self.suppressed_groups, "exempt": self.exempt,
            "basis": "distinct people in the group",
        }

    def notes(self) -> tuple[str, ...]:
        """One sentence when something was left out; silence otherwise."""
        if not self.suppressed_groups:
            return ()
        return (
            f"{self.suppressed_groups} group(s) with fewer than {self.min_group_size} people were left out of this "
            "result so that no individual can be identified. The groups shown are exact and complete.",
        )


def counts_people(plan: Plan) -> bool:
    """Whether the rule applies to a plan: an aggregate over a dataset whose rows describe people."""
    return plan.dataset.employee_level and plan.dataset.person_key is not None and bool(plan.measures)


def require_person_keys(model: SemanticModel) -> None:
    """Refuse a model where an employee-level dataset cannot say who is in a group: a rule with a hole in it."""
    for dataset in model.datasets:
        if dataset.employee_level and (dataset.person_key is None or dataset.column(dataset.person_key) is None):
            raise ValueError(f"{dataset.name}: an employee-level dataset must name the column that counts its people")


def _size(row: tuple[Any, ...]) -> int:
    """A group's size; no rows at all (an empty ungrouped aggregate) is zero people."""
    return int(row[-1] or 0)


def withhold(rows: Rows, k: int, *, grouped: bool) -> tuple[Rows, int]:
    """`rows` without the hidden size column and without any group below `k`, and how many groups went.

    Raises `GroupsAreIndividuals` for a grouped result in which every group is one person.
    """
    sizes = [_size(r) for r in rows.rows]
    if grouped and sizes and all(s == 1 for s in sizes):
        raise GroupsAreIndividuals(
            "Every group in that result holds a single person, so the grouping would list individuals. "
            "Group by something coarser (a location, a month, a year) instead.",
        )
    kept = tuple(r[:-1] for r, s in zip(rows.rows, sizes) if not 0 < s < k)
    return Rows(rows.columns[:-1], kept, rows.truncated), len(sizes) - len(kept)
