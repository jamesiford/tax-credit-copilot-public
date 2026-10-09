"""The statutory floors a programme imposes for one tax year.

A value object, not a service: it holds the hours and wages thresholds resolved
from a year-scoped rule pack, and knows how to describe itself. It lived in
`tools/credit_math.py`, which meant `domain/calculation/proximity.py` had to
reach outward into `tools/` to type its own arguments — an inward dependency
pointing the wrong way [ADR-003].

Resolution still belongs in `tools/`: reading a pack file is I/O, and the domain
does no I/O. `tools.credit_math.resolve_statutory_floors` constructs one of
these from disk and hands it in.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def program_name(pack_file: str) -> str:
    """`ga_jtc.json` -> `ga_jtc`. The directory name for its year packs."""
    return pack_file[:-5] if pack_file.endswith(".json") else pack_file


@dataclass(frozen=True)
class StatutoryFloors:
    """The weekly hours/wages floors a programme imposes for one tax year.

    These are facts about a tax year, not choices we made, so they are resolved
    from the year-scoped rule pack and never from an assumption set. [ADR-005]
    """

    program_code: str
    tax_year: int
    min_weekly_hours: float
    min_weekly_wages: float
    basis: dict[str, Any]
    provenance: dict[str, Any]
    pack_file: str

    @property
    def prototype_verify(self) -> bool:
        """True when this year's floor is an unverified placeholder."""
        return bool(self.basis.get("_prototype_verify") or self.provenance.get("_prototype_verify"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "program_code": self.program_code,
            "tax_year": self.tax_year,
            "minimum_average_weekly_hours": self.min_weekly_hours,
            "minimum_average_weekly_wages_usd": self.min_weekly_wages,
            **{k: v for k, v in self.basis.items() if not k.startswith("_")},
            "prototype_verify": self.prototype_verify,
            "source": f"rules/{program_name(self.pack_file)}/{self.tax_year}.json",
        }
