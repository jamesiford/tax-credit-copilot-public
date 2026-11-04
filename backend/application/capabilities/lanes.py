"""The two lanes a tool result travels in: the person's, and the person-plus-model's. [CH-16d, ADR-009]

A data query can return one employee's hours or a record token. Those values belong to the
person who asked, in the channel they asked from; they are never something a model should be
handed. That is enforced here, on the envelope, rather than by each caller remembering:

- a `Block` carries an `audience` (`both` or `user`);
- a result lists the top-level `facts` keys derived from person-level values in
  `user_only_facts`;
- `model_facts` and `model_blocks` are the ONLY projection a model-facing caller (the
  orchestrator, the narrator) may read, and they drop the user lane.

They work on the envelope's wire form (a dict) because that is what the orchestrator and the
gateway hold. Anything not recognisably `both` is treated as `user`: an unknown word fails
closed, so a producer newer than its consumer can never widen the audience by accident.

Standard library only: this file is copied into the orchestrator container with the envelope.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

BOTH = "both"
USER = "user"

#: The refusal a caller whose model reads tool text (Copilot Cowork, or any caller that is not Teams or Copilot
#: Chat) gets for a result that lists individual employees, from the API and from the gateway alike, so the
#: person is told the same thing wherever it is caught.
EMPLOYEE_LEVEL_CODE = "employee_level_not_available"
EMPLOYEE_LEVEL_MESSAGE = (
    "That answer would list individual employees, and Copilot Cowork (or any client other than Teams or Microsoft "
    "365 Copilot Chat) cannot carry employee-level rows to its model unless you are entitled to make changes. Ask "
    "for a count or an average by location, month or year "
    "instead, or ask in Teams, where the rows are shown to you alone."
)

#: How many entries of a `rows` list a model is shown the NAMES of. The person sees every row
#: the capability rendered; the narrator cannot usefully cite more than this, and a list of
#: five hundred rows would be most of a prompt.
MODEL_ROW_LIMIT = 50


def is_user_block(block: Mapping[str, Any]) -> bool:
    """True for a block only the person may read. A missing audience is `both`; any other word is `user`."""
    return block.get("audience", BOTH) != BOTH


def has_user_lane(envelope: Mapping[str, Any]) -> bool:
    """Whether the result carries anything a model must not be handed."""
    return bool(envelope.get("user_only_facts")) or any(is_user_block(b) for b in envelope.get("blocks") or ())


def model_blocks(envelope: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The envelope's blocks a model may read: everything not marked for the person alone."""
    return [dict(b) for b in envelope.get("blocks") or () if not is_user_block(b)]


def _hidden_keys(envelope: Mapping[str, Any], facts: Mapping[str, Any]) -> set[str]:
    hidden = {str(k) for k in envelope.get("user_only_facts") or ()}
    if facts.get("audience", BOTH) != BOTH:
        hidden.add("rows")  # a producer that said "user" but forgot to name its rows is still obeyed
    return hidden


def model_facts(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """The envelope's facts as a model may be shown them.

    Person-level keys are removed, and a long `rows` list is cut to `MODEL_ROW_LIMIT`. This
    does not change what the person is shown, which is rendered from the full envelope.
    """
    facts = dict(envelope.get("facts") or {})
    for key in _hidden_keys(envelope, facts):
        facts.pop(key, None)
    rows = facts.get("rows")
    if isinstance(rows, list) and len(rows) > MODEL_ROW_LIMIT:
        facts["rows"] = rows[:MODEL_ROW_LIMIT]
    return facts
