"""The program registry's types: what a tax incentive program is, as data. [ADR-013]

Pure and standard-library only. Reading the manifest and the rules folder is `tools/program_registry.py`; this
module only says what an entry is and which calculation models the engine supports, so a validator, the loader and
the portal all agree on the words.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: Credit models the engine prices today: headcount delta over the base year x a flat per-job amount, with a
#: base-year tranche (`tools/credit_math.py`, `domain/calculation/`). A program that needs anything else (a percentage
#: of wages, an investment credit, caps, refundability) needs engine work and is rejected, never ignored.
SUPPORTED_CREDIT_MODELS: tuple[str, ...] = ("per_net_new_job",)

#: Headcount models: the One/Zero pay-period and min-max methods (`domain/calculation/onezero.py`).
SUPPORTED_HEADCOUNT_MODELS: tuple[str, ...] = ("one_zero",)

#: What a person may type. `calculable` is deliberately absent: it is derived from authored year packs, because a
#: typed "calculable" is a claim nothing checks. [ADR-005]
STORED_LIFECYCLES: tuple[str, ...] = ("draft", "described", "retired")

JURISDICTION_LEVELS: tuple[str, ...] = ("federal", "state", "local")


class RegistryError(ValueError):
    """The manifest or an entry in it cannot be used. The message names the file, the entry and the field."""


@dataclass(frozen=True)
class EngineProfile:
    """Which supported models a program uses."""

    credit_model: str = "per_net_new_job"
    headcount_model: str = "one_zero"


@dataclass(frozen=True)
class ProgramEntry:
    """One program in the registry. `lifecycle` is the stored ceiling; see `ProgramEntry.status` for the effective one."""

    code: str
    name: str
    level: str
    jurisdiction_code: str
    pack_file: str
    state: str | None = None
    lifecycle: str = "described"
    engine_profile: EngineProfile = field(default_factory=EngineProfile)
    notes: str = ""

    def status(self, authored_years: list[int]) -> str:
        """`retired` and `draft` stand; otherwise `calculable` exactly when a year pack is authored, else `described`."""
        if self.lifecycle in ("retired", "draft"):
            return self.lifecycle
        return "calculable" if authored_years else "described"
