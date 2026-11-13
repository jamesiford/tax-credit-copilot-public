"""Per-caller request limits for the routes that write or compute on request. [F07.3]

One knob, `RATE_LIMIT_PER_MINUTE`: how many draft saves, previews, exports and batch starts each signed-in caller may make
per minute (each kind counted on its own, as a token bucket: a burst up to the limit passes, a steady stream above it does not). `0` turns the limit off. The default is generous enough that a person typing in the
draft editor (which saves a moment after the last edit) never meets it, and tight enough that a script cannot hammer the store.
The limit is kept per process, so with scale-out the effective ceiling is this number times the instance count; it is a
safeguard against runaway callers, not a quota. It does not apply when nobody is signed in (`AUTH_MODE=none`, local only).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from config_values import tuned_int


@dataclass(frozen=True)
class LimitSettings:
    """Requests per caller per minute for each limited kind of request; 0 is off."""
    per_minute: int = 60


def parse_limits(environ: Mapping[str, str]) -> LimitSettings:
    """`RATE_LIMIT_PER_MINUTE` (default 60, 0 disables; an unparseable value is the default)."""
    return LimitSettings(per_minute=tuned_int(environ, "RATE_LIMIT_PER_MINUTE", 60, 0))
