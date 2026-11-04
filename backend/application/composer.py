"""The response composer [ADR-008].

A reply is assembled **in code**, from the platform's `blocks`, with a narrator's
prose around them. The narrator may write the connective sentences; it may not
write a figure. A figure appears in a reply only as a placeholder —
`{{facts.credit.annual_credit_usd}}`, optionally `{{facts.x|money}}` — that this
module substitutes through the one formatter, and every reply is checked twice:

1. **Before substitution**, the narrator's raw words go through
   `numeric_guard.check_raw`. Any digit outside a placeholder that the reader did
   not supply themselves rejects the narration: the model typed a number.
2. **After substitution**, the whole reply goes through `numeric_guard.check`
   against the fact index. That is defence in depth against a formatter bug — the
   first gate trusts the formatter, the second does not.

Between them the narration is also reviewed by `output_policy` [AI-07]: a link, an
address, an identifier shape, a code block, or the narrator presenting itself as
counsel drops the narration exactly as a bad figure does. So does hedging a figure:
`composer_hedging` rejects an approximation qualifier ("about", "roughly", "rounded",
"up to"...) within three tokens of a figure, because every figure shown is exact [CH-15c].

If any fails, the reply is the platform's own blocks and the standing
disclaimer, nothing else. The composer never softens, rounds or patches a
sentence: a rejected narration is dropped whole and the reader sees the engine's
words instead, with the violations returned so the caller can audit them.

**Where the pieces live.** The assembly is here; placeholders (`composer_placeholders`)
and block rendering (`composer_render`) were split out by size and are re-exported
below, so every import path is unchanged.

Standard library only, plus the guard, the formatter, the envelope and the sibling
`composer_*` modules — all standard-library only themselves, and all vendored into
the orchestrator container.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from application import composer_hedging, numeric_guard, output_policy
from application.capabilities.envelope import DISCLAIMER, Block
from application.composer_placeholders import (  # noqa: F401 - re-exported
    PlaceholderError, _mask_placeholders, narrator_brief, placeholders, substitute,
)
from application.composer_render import cards_payload, render_markdown  # noqa: F401 - re-exported
from application.numeric_guard import AllowedContext, FactIndex, GuardResult, Numeral, Violation


@dataclass(frozen=True)
class Composed:
    """A finished reply.

    `text` is Markdown for the channel; `cards_payload` is a neutral structure the
    orchestrator turns into Adaptive Cards (no card JSON lives here). `guard` is the
    verdict that decided what `text` contains, and `narration_used` says whether
    the narrator's prose survived it.
    """

    text: str
    cards_payload: dict[str, Any]
    guard: GuardResult
    narration_used: bool
    blocks_verified: bool = True
    notice: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """The JSON-safe form, for the channel and the audit trail."""
        return {
            "text": self.text, "cards": self.cards_payload, "guard": self.guard.to_dict(),
            "narration_used": self.narration_used, "blocks_verified": self.blocks_verified,
            "notice": self.notice,
        }


def _verdict(violations: Sequence[Violation]) -> GuardResult:
    return GuardResult(numeric_guard.REJECTED if violations else numeric_guard.PASS, tuple(violations))


def _placeholder_violation(message: str) -> Violation:
    return Violation(Numeral(message, 0, 0, "placeholder"), message, stage="narration")


def _policy_violations(narration: str, allowed_hosts: Sequence[str]) -> list[Violation]:
    """Output-policy codes as violations, so the caller audits them with the rest."""
    codes = output_policy.review(narration, allowed_hosts=allowed_hosts).violations
    return [Violation(Numeral(f"output policy: {c}", 0, 0, "output_policy"), f"output policy: {c}", stage="output_policy") for c in codes]


def _hedge_violations(masked: str) -> list[Violation]:
    """One violation per figure the wording hedges; the code, never the words, is what is recorded."""
    message = "narration style: an approximation qualifier next to a figure"
    return [Violation(Numeral(message, 0, 0, "approximation"), message, stage="narration")
            for _ in range(composer_hedging.hedged_figures(masked))]


def _narrate(
    narration: str, index: FactIndex, context: AllowedContext, allowed_hosts: Sequence[str],
) -> tuple[str, FactIndex, list[Violation]]:
    """Screen the model's own words: no typed digit, no hedged figure, every placeholder renderable, policy clean.

    Returns the substituted text ("" when it could not be rendered), the index told
    which paths were percentages, and every violation found.
    """
    masked = _mask_placeholders(narration)
    violations = [*numeric_guard.check_raw(masked, allowed_context=context).violations, *_hedge_violations(masked)]
    try:
        substituted, index = substitute(narration, index)
    except PlaceholderError as exc:
        return "", index, [*violations, _placeholder_violation(str(exc))]
    narrated = substituted.strip()
    return narrated, index, [*violations, *_policy_violations(narrated, allowed_hosts)]


def _blocks_only(
    blocks_md: str, cards: dict[str, Any], disclaimer: str, index: FactIndex, context: AllowedContext,
    violations: Sequence[Violation],
) -> Composed:
    """The platform's own blocks and the disclaimer, after the guard confirms they are clean."""
    fallback = "\n\n".join(p for p in (blocks_md, disclaimer) if p)
    if not blocks_md:
        return Composed(fallback, cards, _verdict(violations), narration_used=False)
    # The blocks are platform-rendered, so they should always pass. If they do
    # not, a formatter is wrong, and the one thing worse than dropping the
    # narration is showing a figure nothing can vouch for.
    blocks_guard = numeric_guard.check(fallback, facts=index, allowed_context=context)
    if blocks_guard.passed:
        return Composed(fallback, cards, _verdict(violations), narration_used=False)
    notice = (
        "The figures in this answer could not be verified against the engine's output, "
        "so none are shown."
    )
    return Composed(
        "\n\n".join((notice, disclaimer)), {"title": None, "body": [], "disclaimer": disclaimer},
        _verdict([*violations, *blocks_guard.violations]),
        narration_used=False, blocks_verified=False, notice=notice,
    )


def compose(
    blocks: Sequence[Block],
    narration: str | None,
    facts: "FactIndex | Mapping[str, Any] | Sequence[Mapping[str, Any]]",
    allowed_context: AllowedContext | None = None,
    *,
    disclaimer: str = DISCLAIMER,
    allowed_hosts: Sequence[str] = (),
) -> Composed:
    """Assemble one reply, or fall back to the platform's blocks alone.

    The narration, when it survives, sits above the blocks; the disclaimer is
    always last. The guard that decided the outcome is returned either way.
    """
    index = FactIndex.coerce(facts)
    context = allowed_context or AllowedContext()
    blocks_md = render_markdown(blocks)
    cards = cards_payload(blocks, disclaimer=disclaimer)

    narrated, violations = "", []
    if narration and narration.strip():
        narrated, index, violations = _narrate(narration, index, context, allowed_hosts)

    if not violations and narrated:
        # 2. The finished reply, against the facts, trusting no formatter.
        full = "\n\n".join(p for p in (narrated, blocks_md, disclaimer) if p)
        final = numeric_guard.check(full, facts=index, allowed_context=context)
        if final.passed:
            return Composed(full, cards, final, narration_used=True)
        violations.extend(final.violations)

    return _blocks_only(blocks_md, cards, disclaimer, index, context, violations)
