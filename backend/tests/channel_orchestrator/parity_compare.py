"""How the parity test decides two doors said the same thing. [RM-13]

Two envelopes are the same when their canonical JSON (sorted keys, no whitespace) is the same string, after the
VOLATILE fields below are masked. Nothing else is masked, and a mask keeps the field (its value becomes a marker),
so a door that dropped a field, or a door that stopped sending one, still fails. Each volatile field is a value
that is different on every call or for every person BY DESIGN, never a figure:

    correlation_id                      the gateway's id for this request: a different request, a different id. The
                                        API's own answer has none, so the field is REMOVED, not masked, and the tests
                                        assert separately that every gateway door carries one
    facts.as_of                         the second a data read was taken, stamped by the data service
    facts.confirmation.token            a prepared write's single-use token: minted per preview
    facts.confirmation.confirmation_id  the row that holds that token
    facts.confirmation.expires_at       when that token stops working: the minting time plus the window
    facts.preview.after.set_by          who the change would be recorded under (`decided_by` for a claim), and the
    facts.preview.after.decided_by      "set by" / "decided by" cell of the table that shows it: each door names the
                                        same person the way its credential does (a user principal name from a
                                        person's token, an object id from the orchestrator's header), which is
                                        attribution, not a figure

The caller's lane is also declared. A caller that is positively Teams or Copilot Chat is first-party; every other
door (a person's own token, Cowork) is not, and the catalog's `data_catalog` says so to the second kind in one
channel note. `LANE_NOTES` is that note: it is removed before two doors of different lanes are compared, and never
within one lane.
"""
from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from application.capabilities.data_catalog import _COWORK_NOTE
from application.composer.render import render_markdown
from channel.render import blocks_from

MASK = "<volatile>"
VOLATILE_FIELDS = (
    "facts.as_of", "facts.confirmation.token", "facts.confirmation.confirmation_id",
    "facts.confirmation.expires_at", "facts.preview.after.set_by", "facts.preview.after.decided_by",
)
ATTRIBUTION_ROWS = ("set by", "decided by")
LANE_NOTES = (_COWORK_NOTE,)
FIRST_PARTY_DOORS = ("rest-gateway", "maf", "maf-turn")


def _mask_path(body: dict[str, Any], path: str) -> None:
    *parents, last = path.split(".")
    node: Any = body
    for key in parents:
        node = node.get(key) if isinstance(node, dict) else None
    if isinstance(node, dict) and last in node:
        node[last] = MASK


def scrub(envelope: Mapping[str, Any], *, lane_notes: bool = False) -> dict[str, Any]:
    """A copy of `envelope` with the volatile fields masked (and, across lanes, the lane note removed)."""
    body = copy.deepcopy(dict(envelope))
    body.pop("correlation_id", None)
    for path in VOLATILE_FIELDS:
        _mask_path(body, path)
    for block in body.get("blocks") or ():
        if block.get("kind") == "table" and block.get("rows"):
            for row in block["rows"]:
                if row and row[0] in ATTRIBUTION_ROWS:
                    row[-1] = MASK
    if lane_notes:
        facts = body.get("facts")
        if isinstance(facts, dict) and isinstance(facts.get("notes"), list):
            facts["notes"] = [n for n in facts["notes"] if n not in LANE_NOTES]
        body["blocks"] = [b for b in body.get("blocks") or () if not (b.get("kind") == "callout" and b.get("text") in LANE_NOTES)]
    return body


def canonical(envelope: Mapping[str, Any], *, lane_notes: bool = False) -> str:
    """The envelope as the one string two doors must agree on, byte for byte."""
    return json.dumps(scrub(envelope, lane_notes=lane_notes), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# ------------------------------------------------------------------------- figures in text

_NUMERAL = re.compile(r"(?<![\w.])-?\$?\d[\d,]*(?:\.\d+)?%?")
#: Lines a platform text adds that are identifiers or handovers, not figures: the guard reads digits in a digest as numerals.
_NOT_FIGURES = ("Confirmation token", "Provenance:", "Download", "_Source:", "VERBATIM")


def _value(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace("$", "").replace(",", "").rstrip("%"))
    except InvalidOperation:
        return None


def numerals(text: str) -> set[Decimal]:
    """Every number written in `text`, as a value ($66,500 and 66500.00 are the same number)."""
    lines = [line for line in text.splitlines() if not line.startswith(_NOT_FIGURES)]
    return {v for m in _NUMERAL.findall("\n".join(lines)) if (v := _value(m)) is not None}


def _leaves(value: Any) -> Iterable[Any]:
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _leaves(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _leaves(item)
    elif value is not None and not isinstance(value, bool):
        yield value


def envelope_figures(envelope: Mapping[str, Any]) -> set[Decimal]:
    """Every figure an envelope states: its blocks' text and cells, and every leaf of its facts."""
    found = {v for block in envelope.get("blocks") or () for v in numerals(" ".join([block.get("text", ""), *(c for r in block.get("rows") or () for c in r)]))}
    for leaf in _leaves(envelope.get("facts") or {}):
        found |= {v for v in numerals(str(leaf))} if isinstance(leaf, str) else {Decimal(str(leaf))}
    return found


def platform_markdown(envelope: Mapping[str, Any]) -> list[str]:
    """Each of the platform's blocks as the one renderer writes it: what a reply must contain, character for character."""
    return [render_markdown([block]) for block in blocks_from(envelope)]


# ------------------------------------------------------------------------ the portal's shape

def flat_envelope(envelope: Mapping[str, Any]) -> list[str]:
    """The envelope's blocks as one ordered list of strings (a table's header and cells in reading order)."""
    out: list[str] = []
    for block in envelope.get("blocks") or ():
        out += [block["text"]] if block["text"] else []
        out += [cell for row in block.get("rows") or () for cell in row]
    for warning in envelope.get("warnings") or ():
        out += ["Note", warning]  # the evidence pane shows each warning as a callout titled "Note"
    return out


def flat_evidence(blocks: Iterable[Mapping[str, Any]]) -> list[str]:
    """The portal's evidence blocks in the same order: a title is the heading it replaced, a table starts with its columns."""
    out: list[str] = []
    for block in blocks:
        out += [block["title"]] if block.get("title") else []
        out += [block["text"]] if block.get("text") else []
        out += list(block.get("columns") or [])
        out += [cell for row in block.get("rows") or () for cell in row] if block["kind"] == "table" else list(block.get("rows") or ())
    return out


def scalar_facts(facts: Mapping[str, Any]) -> dict[str, str]:
    """Top-level scalar facts as strings: all the portal's evidence pane is told of the facts."""
    return {str(k): str(v) for k, v in facts.items() if isinstance(v, (str, int, float)) and not isinstance(v, bool)}


def brief_leaves(prompt: str) -> list[Any]:
    """The values in the JSON a portal narrator was handed (the part of its prompt after `JSON:`)."""
    _, _, payload = prompt.partition("\nJSON:\n")
    return list(_leaves(json.loads(payload))) if payload else []


def same_value(a: Any, b: Any) -> bool:
    """Equal as written, or as numbers when both read as numbers (66500 and "66500" are one figure)."""
    if a == b:
        return True
    x, y = _value(str(a)), _value(str(b))
    return x is not None and y is not None and x == y
