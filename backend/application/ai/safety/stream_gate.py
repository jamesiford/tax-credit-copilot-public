"""Apply the output policy to a reply that is already streaming. [AI-07]

A reader sees tokens as they arrive, so the policy cannot wait for the end. The gate
holds back the text after the last whitespace — a link or address is not complete
until a space follows it — and reviews everything that WOULD be released, whole,
before releasing it. So:

- what a reader has seen has always passed the policy;
- a pattern that spans chunks ("555", "123", "4567") is caught when it completes,
  before the chunk that completes it is shown;
- once a rule fires the gate stops: nothing further from the model is released.

The honest limit: a pattern that is only recognisable at its end (a phone number's
first digits) may have been shown before the last digits were blocked. The rules that
matter most for leaks — links, addresses, identifiers — are whitespace-delimited and
are held whole.
"""
from __future__ import annotations

from application.ai.ports import OutputPolicy


class OutputGate:
    """Releases streamed text only after the policy has reviewed everything that would be shown."""

    def __init__(self, policy: OutputPolicy) -> None:
        self._policy = policy
        self._released, self._held = "", ""
        self.blocked: tuple[str, ...] = ()

    def feed(self, text: str) -> str:
        """The part of `text` that may be shown now ('' while held or after a block)."""
        if self.blocked:
            return ""
        self._held += text
        boundary = max(self._held.rfind(" "), self._held.rfind("\n"), self._held.rfind("\t"))
        return self._release(boundary + 1)

    def finish(self) -> str:
        """Release whatever is still held, if it passes."""
        return "" if self.blocked else self._release(len(self._held))

    def _release(self, upto: int) -> str:
        if upto <= 0:
            return ""
        chunk = self._held[:upto]
        verdict = self._policy.review(self._released + chunk)
        if not verdict.ok:
            self.blocked, self._held = verdict.violations, ""
            return ""
        self._released += chunk
        self._held = self._held[upto:]
        return chunk
