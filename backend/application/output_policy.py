"""Rules a model's prose must satisfy before a reader sees it. [AI-07]

Standard library only, so it can be vendored beside `numeric_guard` and `composer`
into the orchestrator container (Prompt 4). The numeric guard decides whether a
FIGURE is the engine's; this decides whether the WORDS are ones the product is
willing to say. Both run on every channel narration, and the portal chat applies
this one as the reply streams (`application/ai/safety/stream_gate.py`).

A violation is a short code, never the offending text: the text is what must not be
repeated into a log, a span or an error message.

| code               | what it catches                                                    |
| ------------------ | ------------------------------------------------------------------ |
| `url`              | a link to a host not on the allow-list (default: none)             |
| `email`            | an email address                                                   |
| `phone`            | a North-American-shaped phone number                               |
| `ssn_shape`        | `123-45-6789`                                                      |
| `ein_shape`        | `12-3456789`                                                       |
| `code_fence`       | a fenced code block (the product never needs one in prose)         |
| `legal_advice`     | the assistant presenting itself as counsel, or guaranteeing an     |
|                    | outcome the engine cannot know (audit safety, entitlement)         |

What this does NOT do: judge tone, fact-check prose, or understand intent. It is a
set of patterns, fast and predictable, on purpose; a rule that can be explained to
an auditor in one sentence is one that can be trusted to keep doing it.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

_URL = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>()\[\]\"']+")
_EMAIL = re.compile(r"(?i)[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")
_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_EIN = re.compile(r"(?<!\d)\d{2}-\d{7}(?!\d)")
_FENCE = re.compile(r"```|~~~")
_LEGAL = re.compile(
    r"(?i)\b(?:"
    r"as your (?:tax |legal )?(?:attorney|lawyer|advis[eo]r|cpa|accountant)"
    r"|(?:this|that|it) (?:is|constitutes) (?:formal )?(?:legal|tax) advice"
    r"|i (?:advise|recommend) (?:that )?you (?:to )?(?:file|claim|amend)"
    r"|you (?:should|must|need to) (?:file|claim|amend)\b"
    r"|you (?:are|will be) (?:legally )?(?:entitled|guaranteed)"
    r"|(?:guarantee[sd]?|guaranteed) (?:the |a |your )?(?:credit|refund|approval|outcome)"
    r"|(?:safe|protected) from (?:an )?audit|(?:will|can)(?: not|'t|not) be audited|no (?:risk|chance) of (?:an )?audit"
    r")"
)

#: Hosts the model may link to, as suffixes. Empty: the engine's own blocks carry
#: every link a reader needs, so prose with a URL is the model adding one.
DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = ()


@dataclass(frozen=True)
class PolicyResult:
    violations: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.violations


def _host_allowed(url: str, allowed: Sequence[str]) -> bool:
    host = (urlsplit(url if "://" in url else f"https://{url}").hostname or "").lower()
    return any(host == a or host.endswith("." + a) for a in (h.lower().lstrip(".") for h in allowed))


def _url_violations(text: str, allowed: Sequence[str]) -> list[str]:
    return ["url"] if any(not _host_allowed(m, allowed) for m in _URL.findall(text)) else []


_SIMPLE: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("email", _EMAIL), ("phone", _PHONE), ("ssn_shape", _SSN), ("ein_shape", _EIN),
    ("code_fence", _FENCE), ("legal_advice", _LEGAL),
)


def review(text: str, *, allowed_hosts: Iterable[str] = DEFAULT_ALLOWED_HOSTS) -> PolicyResult:
    """Every rule `text` breaks, as codes in a fixed order. Empty text is fine."""
    allowed = tuple(allowed_hosts)
    found = _url_violations(text, allowed) + [code for code, rule in _SIMPLE if rule.search(text)]
    return PolicyResult(tuple(found))
