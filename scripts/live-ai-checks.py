"""Live checks of the model provider chain, run from inside the network. [CH-14]

    python scripts/live-ai-checks.py <scenario> [--agent ReportingAgent]

Run where the deployed mock model gateway is reachable (its inbound rule admits only the integration
subnet), for example from the API app's Kudu command API, with the backend's `application/`, `domain/`,
`infrastructure/` and `agents/` on the path and httpx, opentelemetry-api, azure-identity and
azure-ai-projects installed. It drives the REAL chain (`application.ai_wiring.get_narration_service`): the
settings are the usual `AI_*` / `FOUNDRY_*` environment variables, so the scenario is chosen by the
environment the command is run with, never by code in this file.

    narrate      one narration; prints the provider that answered, the hops, the length of the text
    rate-limit   queues a 429 with Retry-After on the mock first; prints whether the wait was honoured
    hop          queues failures on the mock first (`--faults N`): the chain must move on to the next
                 provider, and the hops must say so
    egress       a prompt carrying a record-token field and a 24-hex record token (the shapes `application/ai/egress.py` refuses):
                 every provider must refuse it

Optional `LIVE_TOKEN_DIR`: a folder holding one file per token scope (the scope with every non-alphanumeric
character replaced by `_`), used instead of a managed identity the command shell does not have. The files are
the operator's own short-lived tokens, written for the run and deleted after; this script reads them and never
prints, logs or stores one.

Prints one JSON object per line and nothing else. No prompt text beyond its length, and no token.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

PROMPT = "Narrate this brief in one sentence: 5 of 5 clients were assessed."
IDENTIFIER_PROMPT = 'Narrate this brief: {"record_token": "9f2c1ab04d7e55a1b3c6d8e0", "weekly_hours": 38.5}'


def install_file_credentials() -> None:
    """Replace `DefaultAzureCredential` by one that reads the operator's tokens from `LIVE_TOKEN_DIR`."""
    folder = os.environ.get("LIVE_TOKEN_DIR")
    if not folder:
        return
    import azure.identity as identity
    from azure.core.credentials import AccessToken

    class FileCredential:
        def get_token(self, *scopes, **_kwargs):
            name = re.sub(r"[^A-Za-z0-9]", "_", scopes[0])
            path = Path(folder) / name
            if not path.exists():
                raise RuntimeError(f"no token file for scope {scopes[0]!r}")
            return AccessToken(path.read_text(encoding="utf-8").strip(), int(time.time()) + 300)

        async def close(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

    identity.DefaultAzureCredential = FileCredential


def emit(**fields) -> None:
    print(json.dumps(fields, sort_keys=True), flush=True)


async def narrate(prompt: str, agent: str) -> dict:
    """Run one narration through the real service; the result says who answered, never what was said."""
    from application.ai_wiring import get_narration_service
    from domain.ai import StreamEnd, TextDelta

    started, text, end = time.monotonic(), "", None
    try:
        async for event in get_narration_service().stream(agent, prompt):
            if isinstance(event, TextDelta):
                text += event.text
            elif isinstance(event, StreamEnd):
                end = event
    except Exception as exc:  # noqa: BLE001 - the outcome IS the finding
        return {"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:160], "ms": round((time.monotonic() - started) * 1000)}
    return {"ok": bool(text), "provider": getattr(end, "provider", None), "hops": list(getattr(end, "hops", ()) or ()),
            "text_chars": len(text), "mock_reply": text.startswith("Mock reply"), "ms": round((time.monotonic() - started) * 1000)}


def mock(path: str, body: dict | None = None):
    """The mock's admin endpoints (no auth): script a fault, read the call log."""
    import httpx

    base = os.environ["AI_GATEWAY_ENDPOINT"].rstrip("/")
    response = httpx.post(base + path, json=body or {}, timeout=20) if body is not None else httpx.get(base + path, timeout=20)
    return response.json()


def summarise_log(entries: list[dict]) -> dict:
    return {"mock_calls": len(entries), "auth_ok": sum(1 for e in entries if e.get("auth_ok")),
            "auth_refused": sum(1 for e in entries if not e.get("auth_ok")), "streamed": sum(1 for e in entries if e.get("stream"))}


async def run(args: argparse.Namespace) -> int:
    install_file_credentials()
    gateway_in_chain = "gateway" in os.environ.get("AI_PROVIDER_CHAIN", "")
    if gateway_in_chain:
        mock("/_admin/reset", {})
    if args.scenario == "rate-limit":
        mock("/_admin/script", {"faults": [{"kind": "status", "code": 429, "retry_after": args.retry_after}]})
    if args.scenario == "hop":
        mock("/_admin/script", {"faults": [{"kind": "status", "code": 503}] * args.faults})
    prompt = IDENTIFIER_PROMPT if args.scenario == "egress" else PROMPT
    result = await narrate(prompt, args.agent)
    log = summarise_log(mock("/_admin/log")) if gateway_in_chain else {}
    emit(scenario=args.scenario, chain=os.environ.get("AI_PROVIDER_CHAIN"), auth=os.environ.get("AI_GATEWAY_AUTH"),
         agent=args.agent, prompt_chars=len(prompt), retry_after_s=args.retry_after if args.scenario == "rate-limit" else None,
         **result, **log)
    return 0 if args.scenario == "egress" or result.get("ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", choices=("narrate", "rate-limit", "hop", "egress"))
    parser.add_argument("--agent", default="ReportingAgent")
    parser.add_argument("--retry-after", type=int, default=2)
    parser.add_argument("--faults", type=int, default=6, help="503s queued on the mock for `hop` (more than the retry attempts)")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
