"""`/modelprobe`: the model call exactly as Microsoft's hosted-agent sample makes it. [CH-14]

The sample (`bring-your-own/responses/hello-world`) obtains its model client with
`AIProjectClient(endpoint=FOUNDRY_PROJECT_ENDPOINT, credential=DefaultAzureCredential()).get_openai_client()`
and calls `responses.create(model=<deployment name>)`. This runs that, reports the base URL the client chose
(a host and path, no credential), the outcome, and how long it took, so it can be set beside `/netcheck`
and beside the orchestrator's own chat-completions client. Offered only with `CHANNEL_DEBUG_WHOAMI`.
Reports no token and no response beyond a character count.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Mapping
from typing import Any

PROMPT = "Reply with the single word: ok"


def _sample_call(endpoint: str, model: str) -> dict[str, Any]:
    """Blocking: the sample's own call. Imports lazily so the orchestrator starts without the SDK."""
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    client = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential()).get_openai_client()
    report: dict[str, Any] = {"base_url": str(getattr(client, "base_url", ""))}
    response = client.responses.create(model=model, input=PROMPT, store=False)
    report["reply_chars"] = len(response.output_text or "")
    return report


async def run_modelprobe(env: Mapping[str, str], *, call: Callable[[str, str], dict[str, Any]] = _sample_call) -> str:
    """The probe's report as JSON text; a failure is reported by type and message, never raised."""
    endpoint = env.get("FOUNDRY_PROJECT_ENDPOINT", "")
    model = env.get("FOUNDRY_MODEL") or env.get("AZURE_AI_MODEL_DEPLOYMENT_NAME") or ""
    report: dict[str, Any] = {"project_endpoint_host": endpoint.split("//")[-1].split("/")[0], "model": model, "path": "AIProjectClient.get_openai_client().responses"}
    if not endpoint or not model:
        return json.dumps({**report, "ok": False, "error": "FOUNDRY_PROJECT_ENDPOINT or the model name is not set"}, indent=2)
    started = time.monotonic()
    try:
        report.update(await asyncio.get_running_loop().run_in_executor(None, call, endpoint, model))
        report["ok"] = True
    except Exception as exc:  # noqa: BLE001 - the failure IS the finding
        cause = exc.__cause__ or exc.__context__
        report.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:200]}",
                      cause=f"{type(cause).__name__}: {str(cause)[:160]}" if cause else None)
    report["ms"] = round((time.monotonic() - started) * 1000)
    return json.dumps(report, indent=2)
