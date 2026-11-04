"""The gateway's per-user token bucket, which now lives in `application.rate_limit`. [CH-06, CH-16c]

Kept as a re-export so the gateway's imports and tests are unchanged while the data-query
budget (in the API process) shares the one implementation.
"""
from __future__ import annotations

from application.rate_limit import MAX_KEYS, RateLimiter

__all__ = ["MAX_KEYS", "RateLimiter"]
