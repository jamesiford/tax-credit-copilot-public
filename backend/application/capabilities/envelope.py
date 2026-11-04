"""The envelope every capability returns.

`facts` are the engine's numbers, untouched. `blocks` are text the platform
rendered from those facts through `format.py` — deterministic, no model. A
caller that wants prose around them (the portal narrator, the channel composer)
may add words; it may not add a figure, because the only figures that exist are
the ones in `facts` [ADR-004, ADR-008].

Dataclasses rather than pydantic: this module has no framework dependency, and
the envelope must serialise identically wherever it travels.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

#: One short sentence, drawn from DISCLAIMER.md ("This is not tax advice").
#: Standing text on every result and every composed reply.
DISCLAIMER = (
    "Not tax advice: these figures are computed from payroll by this software "
    "and must be reviewed by a qualified tax professional before any filing or claim."
)

BLOCK_KINDS = ("heading", "paragraph", "bullets", "table", "callout")

#: Who may read a block. `both`: the person and any model that narrates around the result.
#: `user`: the person only. A lane is a property of the envelope, not a convention a caller
#: remembers, so a consumer that does not know the word treats the block as `user` [ADR-009].
AUDIENCE_BOTH = "both"
AUDIENCE_USER = "user"
AUDIENCES = (AUDIENCE_BOTH, AUDIENCE_USER)


@dataclass(frozen=True)
class Block:
    """A unit of platform-rendered text.

    `heading`, `paragraph` and `callout` carry `text`. `bullets` carries one
    single-cell row per item. `table` carries `rows`, header first, every row the
    same width. `audience` is `both` unless the block holds person-level values.
    """

    kind: str
    text: str = ""
    rows: tuple[tuple[str, ...], ...] = ()
    audience: str = AUDIENCE_BOTH

    def __post_init__(self) -> None:
        if self.kind not in BLOCK_KINDS:
            raise ValueError(f"block kind must be one of {BLOCK_KINDS}, got {self.kind!r}")
        if self.audience not in AUDIENCES:
            raise ValueError(f"block audience must be one of {AUDIENCES}, got {self.audience!r}")
        if self.kind == "table":
            widths = {len(row) for row in self.rows}
            if len(widths) > 1:
                raise ValueError("table rows must all have the same number of cells")
        if self.kind == "bullets" and any(len(row) != 1 for row in self.rows):
            raise ValueError("bullet rows must have exactly one cell")

    def to_dict(self) -> dict[str, Any]:
        """The wire form. `audience` is written only when it is not the default, so every
        existing envelope serialises byte-for-byte as before."""
        wire: dict[str, Any] = {"kind": self.kind, "rows": [list(r) for r in self.rows], "text": self.text}
        if self.audience != AUDIENCE_BOTH:
            wire["audience"] = self.audience
        return wire


@dataclass(frozen=True)
class Provenance:
    """Where a figure came from. A field is None when there is genuinely none.

    A claims-only read has no run and no trail; saying so with None is honest,
    and inventing a run id to fill the slot would be the one thing the field
    exists to prevent.
    """

    run_id: str | None = None
    rule_pack_version: str | None = None
    assumption_set_id: str | None = None
    trail_sha256: str | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumption_set_id": self.assumption_set_id,
            "rule_pack_version": self.rule_pack_version,
            "run_id": self.run_id,
            "source": self.source,
            "trail_sha256": self.trail_sha256,
        }


def json_safe(value: Any) -> Any:
    """Plain JSON types, with dict keys sorted so the output is byte-stable.

    Money stays exact: a `Decimal` becomes its string, never a float. Sets are
    sorted; tuples become lists; dates become ISO strings.
    """
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((json_safe(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and value != value:
        return None
    return value


@dataclass(frozen=True)
class ToolResult:
    """What a capability hands back.

    `facts` keeps the producer's own key order, because the portal narrator is
    handed `json.dumps(facts, indent=2)` and its prompt must not change.
    `to_dict()` is the stable wire form: sorted keys, JSON types only.

    `user_only_facts` names top-level `facts` keys derived from person-level values. They
    are delivered to the person and are never part of what a model is shown (`lanes.py`).
    """

    tool: str
    facts: dict[str, Any]
    blocks: tuple[Block, ...] = ()
    provenance: Provenance = field(default_factory=Provenance)
    disclaimer: str = DISCLAIMER
    warnings: tuple[str, ...] = ()
    user_only_facts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        unknown = set(self.user_only_facts) - set(self.facts)
        if unknown:
            raise ValueError(f"user_only_facts names keys the facts do not have: {sorted(unknown)}")

    def to_dict(self) -> dict[str, Any]:
        wire: dict[str, Any] = {
            "blocks": [b.to_dict() for b in self.blocks],
            "disclaimer": self.disclaimer,
            "facts": json_safe(self.facts),
            "provenance": self.provenance.to_dict(),
            "tool": self.tool,
            "warnings": list(self.warnings),
        }
        if self.user_only_facts:
            wire["user_only_facts"] = sorted(self.user_only_facts)
        return wire

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
