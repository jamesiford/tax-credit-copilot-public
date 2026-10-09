"""Microsoft Web IQ client — real retrieval for the RulesIngestionAgent.

Thin, dependency-free (urllib) client for the Web IQ v3 REST API. It is the
capability the guardrail (GOV-01 / A5) intends: retrieve GA Jobs Tax Credit
rules from trusted primary sources and cite them, rather than hand-entering
thresholds.

Auth + endpoints (verified against https://webiq.microsoft.ai/documentation):
  Base:  https://api.microsoft.ai/v3
  Auth:  header  x-apikey: <KEY>            (quickest; key from the Web IQ portal)
         or      Authorization: Bearer <JWT>  (Entra client-credentials,
                 scope https://api.microsoft.ai/.default)
  Web search:  POST /search/web   {query, maxResults, contentFormat, ...}
  Browse:      POST /browse       {url, contentFormat, liveCrawl, ...}

The key is NEVER hardcoded — it is read from the environment (``WEBIQ_API_KEY``
or ``WEBIQ_BEARER_TOKEN``). When neither is set, ``is_configured()`` is False and
callers degrade gracefully (no network) so tests + the offline demo stay
deterministic. See ``backend/.env.example``.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_BASE_URL = os.getenv("WEBIQ_BASE_URL", "https://api.microsoft.ai/v3")


class WebIQError(RuntimeError):
    """Raised for non-retryable Web IQ API failures."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Web IQ {status}: {message}")
        self.status = status


@dataclass
class WebIQConfig:
    base_url: str = _BASE_URL
    api_key: str | None = None
    bearer_token: str | None = None

    @classmethod
    def from_env(cls) -> "WebIQConfig":
        return cls(
            base_url=os.getenv("WEBIQ_BASE_URL", _BASE_URL),
            api_key=os.getenv("WEBIQ_API_KEY") or None,
            bearer_token=os.getenv("WEBIQ_BEARER_TOKEN") or None,
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key or self.bearer_token)

    def auth_headers(self) -> dict[str, str]:
        if self.api_key:
            return {"x-apikey": self.api_key}
        if self.bearer_token:
            return {"Authorization": f"Bearer {self.bearer_token}"}
        return {}


def is_configured() -> bool:
    """True when a Web IQ credential is present in the environment."""
    return WebIQConfig.from_env().configured


def runtime_status() -> str:
    """READY when a credential is present; NEEDS_KEY otherwise (for the UI/audit)."""
    return "READY" if is_configured() else "NEEDS_KEY"


def _post(path: str, body: dict[str, Any], *, timeout: float = 20.0) -> dict[str, Any]:
    cfg = WebIQConfig.from_env()
    if not cfg.configured:
        raise WebIQError(401, "no Web IQ credential set (WEBIQ_API_KEY / WEBIQ_BEARER_TOKEN)")
    url = f"{cfg.base_url.rstrip('/')}/{path.lstrip('/')}"
    data = json.dumps(body).encode("utf-8")
    headers = {"content-type": "application/json", **cfg.auth_headers()}
    req = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed trusted host
            payload = json.loads(resp.read().decode("utf-8"))
            status = getattr(resp, "status", 200)
            if status == 202:
                payload["_accepted"] = True  # crawl in progress
            return payload
    except HTTPError as e:  # non-2xx
        try:
            detail = e.read().decode("utf-8")[:300]
        except Exception:  # noqa: BLE001
            detail = e.reason or "http error"
        raise WebIQError(e.code, detail) from e
    except URLError as e:
        raise WebIQError(0, f"network error: {e.reason}") from e


def search_web(
    query: str,
    *,
    max_results: int = 5,
    content_format: str = "passage",
    max_length: int = 8000,
    site: str | None = None,
) -> list[dict[str, Any]]:
    """Search the web (optionally scoped to a `site:`) and return webResults.

    ``content_format='passage'`` returns query-contextual extractions — the most
    useful for pulling the specific threshold/tier language out of a GA page.
    """
    q = f"{query} site:{site}" if site else query
    body = {
        "query": q[:1000],
        "maxResults": max_results,
        "contentFormat": content_format,
        "maxLength": max_length,
    }
    resp = _post("/search/web", body)
    return list(resp.get("webResults", []))


def browse(
    url: str,
    *,
    content_format: str = "markdown",
    max_length: int = 12000,
    live_crawl: str = "fallback",
) -> dict[str, Any]:
    """Retrieve a specific URL's content (grounding) + crawl timestamps.

    ``live_crawl='fallback'`` crawls on-demand if the URL is not already indexed,
    so a freshly-published GA table is still retrievable. A 202 response
    (``_accepted``) means an on-demand crawl is in progress — the caller should
    retry after ``retryAfter``.
    """
    body = {
        "url": url,
        "contentFormat": content_format,
        "maxLength": max_length,
        "liveCrawl": live_crawl,
    }
    return _post("/browse", body)
