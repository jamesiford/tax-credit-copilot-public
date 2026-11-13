"""Per-caller limits on the requests that write or compute on demand. [F07.3]

The policy: one token bucket per (kind of request, caller), sized by `RATE_LIMIT_PER_MINUTE`, built on the same `RateLimiter` the
channel gateway uses. Only a signed-in caller is counted: with nobody signed in (`AUTH_MODE=none`, local development) there is no
caller. For the channel gateway the caller is the person it acts for, never its own service principal. The API layer turns a
refusal into a 429; this module knows nothing about HTTP.
"""
from __future__ import annotations

from application.identity import Principal
from application.rate_limit import RateLimiter
from config import get_settings

_limiters: dict[int, RateLimiter] = {}


def _limiter(per_minute: int) -> RateLimiter:
    """The shared bucket set for this per-minute limit, built on first use."""
    if per_minute not in _limiters:
        _limiters[per_minute] = RateLimiter(per_minute)
    return _limiters[per_minute]


def reset() -> None:
    """Forget every bucket (tests)."""
    _limiters.clear()


def seconds_to_wait(kind: str, principal: Principal) -> int:
    """0 when the request may proceed (and is counted); else how many seconds until it would."""
    per_minute = get_settings().limits.per_minute
    if per_minute < 1 or not principal.authenticated:
        return 0
    allowed, wait = _limiter(per_minute).allow(f"{kind}:{principal.effective_oid or principal.actor}")
    return 0 if allowed else wait
