"""`OutputPolicy` port over the stdlib rules in `application/output_policy.py`. [AI-07]"""
from __future__ import annotations

from collections.abc import Iterable

from application import output_policy
from domain.ai import OutputVerdict


class RuleOutputPolicy:
    """Pattern rules over a finished (or so-far) narration. Codes only, never the text."""

    def __init__(self, allowed_hosts: Iterable[str] = ()) -> None:
        self._allowed = tuple(allowed_hosts)

    def review(self, text: str) -> OutputVerdict:
        result = output_policy.review(text, allowed_hosts=self._allowed)
        return OutputVerdict(result.ok, result.violations)
