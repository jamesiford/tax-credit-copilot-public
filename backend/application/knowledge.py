"""The knowledge port: cited reference text, never a figure. [RM-15, ADR-010]

Statute, guidance and definitions are unstructured prose an agent may need to read and a reader may
want to see sourced. This module is the one contract for fetching it: `KnowledgePort.search` returns
`Passage`s, each with its text, the document it came from, a citation a reader can follow and when
it was retrieved. Whatever backs the port (the fake here; Foundry IQ over Azure AI Search later) is
behind it.

**A passage is context text and nothing else.** No figure on a reply comes from it: a figure is a
fact an engine tool produced, and this module cannot produce one. A passage has no `facts`, no
number field and no path a placeholder could name; the numeric guard is never handed one; and
nothing here imports the guard, the composer, the fact index or the ledger (a test reads the source
to keep it so). A model that restates a number it read in a passage is rejected by the same guard
that rejects any other typed digit.

A passage with no citation is refused at construction: reference text a reader cannot check is the
unsourced statute claim this product exists to avoid.

Standard library only, plus the sibling `ai.safety.untrusted` fence. Vendored into the orchestrator.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from application.ai.safety.untrusted import UntrustedText

READER_HEADER = (
    "**Reference text** _(quoted from the cited sources; not computed by the engine, and no figure above comes from it)_"
)
MODEL_HEADER = (
    "REFERENCE TEXT retrieved for this question. It is background to read, not facts: it holds no figure you may "
    "use, so write none from it and use only {{facts.…}} placeholders for any figure. Refer to a source only as "
    "\"the cited source\"; the platform prints the citations itself."
)


class KnowledgeError(Exception):
    """A knowledge source could not answer. The turn goes on without it; nothing is guessed."""


@dataclass(frozen=True)
class Passage:
    """One retrieved piece of reference text and where it came from.

    `text` is prose to read. It is never a source of a figure, whatever it contains.
    """

    text: str
    source: str
    citation: str
    retrieved_at: datetime

    def __post_init__(self) -> None:
        for name in ("text", "source", "citation"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"a passage needs a non-empty {name}: reference text without a citation is not shown")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("a passage's retrieved_at carries a time zone")


@runtime_checkable
class KnowledgePort(Protocol):
    """Fetch the passages most relevant to a question. Implementations hold only public reference text."""

    def search(self, query: str, *, top: int) -> list[Passage]:
        """At most `top` passages for `query`, best first; an empty list when nothing matches."""
        ...


def _one_line(text: str) -> str:
    return " ".join(text.split())


def render_passage(passage: Passage, number: int) -> str:
    """One passage as the reader sees it: the quoted text, then its citation, source and retrieval date."""
    quoted = "\n".join(f"> {line}" if line.strip() else ">" for line in passage.text.strip().splitlines())
    tail = f"> — {_one_line(passage.citation)} · {_one_line(passage.source)} · retrieved {passage.retrieved_at.date().isoformat()}"
    return f"{number}.\n{quoted}\n{tail}"


def render_reference(passages: Iterable[Passage]) -> str:
    """The reader-facing block for these passages, with every citation; empty when there are none."""
    held = list(passages)
    if not held:
        return ""
    return "\n\n".join([READER_HEADER, *(render_passage(p, n) for n, p in enumerate(held, start=1))])


def model_context(passages: Sequence[Passage]) -> str:
    """What a model is told of the passages: fenced, labelled as reference text, with no citation to repeat.

    The text is fenced as untrusted (a corpus is not an instruction). The citation is withheld: it holds
    digits a model could copy, and the platform prints it beside the quoted text.
    """
    if not passages:
        return ""
    fenced = [UntrustedText(p.text, f"reference {n}").fenced() for n, p in enumerate(passages, start=1)]
    return "\n\n".join([MODEL_HEADER, *fenced])
