"""A stand-in for the customer's model gateway. [AI-03]

An OpenAI-compatible `/v1/chat/completions` (streaming and not, WITH tool calling)
that exists so the whole model path — auth, streaming, fallback, resilience — can
be exercised without the real gateway. Used three ways: in-process by tests
(`create_app` through an ASGI transport), locally (`python scripts/mock-ai-gateway.py`),
and as the PoC's mock App Service (`infra/modules/mock_ai_gateway`).

    auth     MOCK_AUTH = none | api_key | oauth | entra   (the schemes the adapter supports)
    faults   queued per request: latency, 429 + Retry-After, 5xx, hang, a stream cut
             mid-way, malformed SSE — each fires `times` times, then is spent
    script   queued replies (text and/or tool calls); with none queued it echoes
    log      every request (method, path, auth outcome, model, message roles) — never bodies

It is a MOCK: it validates the SHAPE of an Entra token, not its signature, and must
never be enabled in the enterprise profile.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse


@dataclass
class MockConfig:
    auth: str = "none"
    api_key: str = "mock-key"
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer "
    oauth_client_id: str = "mock-client"
    oauth_client_secret: str = "mock-secret"
    entra_audience: str = "api://mock-gateway"
    token_ttl_s: int = 3600


@dataclass
class MockState:
    config: MockConfig
    log: list[dict[str, Any]] = field(default_factory=list)
    responses: deque = field(default_factory=deque)
    faults: deque = field(default_factory=deque)
    tokens: set[str] = field(default_factory=set)


def _entra_ok(token: str, audience: str) -> bool:
    parts = token.split(".")
    if len(parts) != 3:
        return False
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except ValueError:
        return False
    return str(payload.get("aud", "")).rstrip("/") in (audience.rstrip("/"), audience.rstrip("/").removeprefix("api://"))


def _authorized(state: MockState, request: Request) -> bool:
    cfg, header = state.config, request.headers
    if cfg.auth == "none":
        return True
    if cfg.auth == "api_key":
        return header.get(cfg.api_key_header) == cfg.api_key_prefix + cfg.api_key
    token = (header.get("authorization") or "").removeprefix("Bearer ").strip()
    if cfg.auth == "oauth":
        return token in state.tokens
    return cfg.auth == "entra" and _entra_ok(token, cfg.entra_audience)


def _chunk(model: str, delta: dict, finish: str | None = None, usage: dict | None = None) -> str:
    body = {"id": "chatcmpl-mock", "object": "chat.completion.chunk", "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}] if delta or finish else []}
    if usage:
        body["usage"] = usage
    return f"data: {json.dumps(body)}\n\n"


def _tool_fragments(calls: list[dict]) -> list[dict]:
    return [{"index": i, "id": f"call_{i}", "type": "function",
             "function": {"name": c["name"], "arguments": json.dumps(c.get("arguments", {}))}}
            for i, c in enumerate(calls)]


async def _sse(model: str, reply: dict, prompt_tokens: int, usage: bool, fault: dict | None):
    words = (reply.get("text") or "").split(" ")
    cut = (fault or {}).get("after", 2) if (fault or {}).get("kind") == "disconnect_mid_stream" else None
    yield _chunk(model, {"role": "assistant", "content": ""})
    for i, word in enumerate(words if reply.get("text") else []):
        if cut is not None and i >= cut:
            raise ConnectionResetError("mock gateway: connection cut mid-stream")
        yield _chunk(model, {"content": word + (" " if i < len(words) - 1 else "")})
    if (fault or {}).get("kind") == "malformed_sse":
        yield "data: {not json\n\n"
    calls = reply.get("tool_calls") or []
    if calls:
        yield _chunk(model, {"tool_calls": _tool_fragments(calls)})
    yield _chunk(model, {}, "tool_calls" if calls else "stop")
    if usage:
        yield _chunk(model, {}, usage={"prompt_tokens": prompt_tokens, "completion_tokens": len(words), "total_tokens": prompt_tokens + len(words)})
    yield "data: [DONE]\n\n"


def _next(queue: deque) -> dict | None:
    if not queue:
        return None
    item = queue[0]
    item["times"] = item.get("times", 1) - 1
    if item["times"] <= 0:
        queue.popleft()
    return item


def create_app(config: MockConfig | None = None) -> FastAPI:
    state = MockState(config or MockConfig(
        auth=os.getenv("MOCK_AUTH", "none"), api_key=os.getenv("MOCK_API_KEY", "mock-key"),
        entra_audience=os.getenv("MOCK_ENTRA_AUDIENCE", "api://mock-gateway")))
    app = FastAPI(title="mock-ai-gateway")
    app.state.mock = state

    async def _chat(request: Request, model: str | None = None):
        body = await request.json()
        model = model or body.get("model", "mock-model")
        ok = _authorized(state, request)
        state.log.append({"path": request.url.path, "auth_ok": ok, "model": model,
                          "stream": bool(body.get("stream")), "roles": [m.get("role") for m in body.get("messages", [])],
                          "tools": [t["function"]["name"] for t in body.get("tools", [])],
                          "request_id": request.headers.get("x-request-id"), "user_agent": request.headers.get("user-agent")})
        if not ok:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        fault = _next(state.faults)
        if fault and fault["kind"] == "latency":
            await asyncio.sleep(fault.get("seconds", 0.1))
        elif fault and fault["kind"] == "hang":
            await asyncio.sleep(fault.get("seconds", 3600))
        elif fault and fault["kind"] == "status":
            headers = {"Retry-After": str(fault["retry_after"])} if "retry_after" in fault else {}
            return JSONResponse({"error": "mock fault"}, status_code=fault["code"], headers=headers)
        reply = _next(state.responses) or {"text": "Mock reply to: " + next(
            (m.get("content", "") for m in reversed(body.get("messages", [])) if m.get("role") == "user"), "")[:60]}
        prompt_tokens = sum(len(str(m.get("content", "")).split()) for m in body.get("messages", []))
        if body.get("stream"):
            usage = bool((body.get("stream_options") or {}).get("include_usage"))
            return StreamingResponse(_sse(model, reply, prompt_tokens, usage, fault), media_type="text/event-stream")
        calls = reply.get("tool_calls") or []
        message: dict[str, Any] = {"role": "assistant", "content": reply.get("text")}
        if calls:
            message["tool_calls"] = [{"id": f["id"], "type": "function", "function": f["function"]} for f in _tool_fragments(calls)]
        return {"id": "chatcmpl-mock", "model": model, "choices": [{"index": 0, "message": message,
                "finish_reason": "tool_calls" if calls else "stop"}],
                "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": len((reply.get("text") or "").split())}}

    @app.post("/v1/chat/completions")
    async def openai_v1(request: Request):
        return await _chat(request)

    @app.post("/openai/deployments/{deployment}/chat/completions")
    async def azure_style(deployment: str, request: Request):
        return await _chat(request, deployment)

    @app.post("/oauth/token")
    async def token(request: Request):
        form = await request.form()
        cfg = state.config
        if form.get("client_id") != cfg.oauth_client_id or form.get("client_secret") != cfg.oauth_client_secret:
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        issued = secrets.token_urlsafe(24)
        state.tokens.add(issued)
        return {"access_token": issued, "token_type": "Bearer", "expires_in": cfg.token_ttl_s}

    @app.post("/_admin/script")
    async def script(request: Request):
        body = await request.json()
        state.responses.extend(body.get("responses", []))
        state.faults.extend(body.get("faults", []))
        return {"queued": {"responses": len(state.responses), "faults": len(state.faults)}}

    @app.get("/_admin/log")
    def log():
        return state.log

    @app.post("/_admin/reset")
    def reset():
        state.log.clear(), state.responses.clear(), state.faults.clear(), state.tokens.clear()
        return {"reset": True}

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "auth": state.config.auth, "time": time.time()}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("MOCK_HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8089")))
