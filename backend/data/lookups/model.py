"""App-owned lookups: what the app must resolve that the customer's schema does not carry. [07]

Four lookups are referenced by the source and are not in the schema the customer shared. They are NOT authored
in the customer's lakehouse (their system of record, read-only to us). Each is resolved in the application, by
key, after the account-scoped read, through one resolver, in this provider order:

    source  ->  override  ->  seed  ->  default  ->  none

`source` a table in the customer's estate under its mapped name, when present with rows (read-only)
`override` app-owned rows in the operational store, per client or global, with provenance and an audit trail
`seed` a versioned file in git (`backend/rules/lookups/<name>.v<N>.json`) with provenance and an `inferred` flag
`default` blank or a documented default, for display-only lookups
`none` absent, with a defined consequence

A lookup is `statute_affecting` when what it returns can change a filed figure. Its policy is `strict` (a missing
lookup blocks the affected calculation with a message that names what is missing) or `assume` (use the next
provider and FLAG it). No provider is ever assumed silently: every resolution carries its provider, its version and
whether it was inferred, and `PayCodeReport` counts what could not be mapped.
"""
from __future__ import annotations

from dataclasses import dataclass, field

STRICT, ASSUME = "strict", "assume"
PROVIDERS = ("source", "override", "seed", "default", "none")


@dataclass(frozen=True)
class LookupSpec:
    """What a lookup is for, and what its absence costs."""

    name: str
    statute_affecting: bool
    used_for: str
    if_missing: str


SPECS: dict[str, LookupSpec] = {s.name: s for s in (
    LookupSpec("pay_code_category", True, "which pay counts as remuneration (BA-07)",
               "an unmapped pay code is dropped by the state's whitelist: eligibility reads zero with no error"),
    LookupSpec("entity_fiscal_year_rules", True, "the client's own fiscal window (BA-01)",
               "a calendar-year window is assumed, flagged; the base year hangs off it"),
    LookupSpec("pay_frequency", False, "lineage only (BA-03): the label is derived from the measured period span",
               "none; the label comes from the data, not from a lookup"),
    LookupSpec("industry_type", False, "display only", "the industry shows no name (the raw id is kept)"),
)}


@dataclass(frozen=True)
class Provenance:
    """Where one lookup answer came from. Travels with the answer into the manifest, the trail and the UI."""

    lookup: str
    provider: str
    version: str | None = None
    inferred: bool = False
    rows: int | None = None
    policy: str = ASSUME
    note: str = ""

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "")}

    @property
    def label(self) -> str:
        """`source (N rows)`, `override`, `seed v3 (inferred)`, `default`, `missing (strict)`."""
        if self.provider == "none":
            return f"missing ({self.policy})"
        text = self.provider + (f" v{self.version}" if self.version and self.provider == "seed" else "")
        text += f" ({self.rows} rows)" if self.rows is not None and self.provider == "source" else ""
        return text + (" (inferred)" if self.inferred else "")


@dataclass(frozen=True)
class PayCodeReport:
    """What the pay-code resolution did to one account's payroll. Never silent about what it could not map."""

    policy: str
    distinct_codes: int = 0
    unmapped_codes: tuple[str, ...] = ()
    unmapped_rows: int = 0
    inferred_codes: int = 0
    providers: dict[str, int] = field(default_factory=dict)
    null_code_rows: int = 0

    def as_dict(self) -> dict:
        return {
            "policy": self.policy, "distinct_codes": self.distinct_codes, "distinct_unmapped": len(self.unmapped_codes),
            "unmapped_codes": list(self.unmapped_codes), "rows_unmapped": self.unmapped_rows,
            "codes_resolved_by_inferred_seed": self.inferred_codes, "providers": dict(self.providers),
            "rows_with_no_pay_code_treated_as_regular": self.null_code_rows,
        }
