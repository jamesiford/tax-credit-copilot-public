"""The OpenAI-compatible gateway path, end to end against the mock. [AI-03]

Everything the customer's gateway might do differently is configuration, so each
configuration is exercised: both URL dialects, streaming and not, tool calling,
and all three authentication schemes. Failure behaviour is pinned too — a rate
limit, a cut stream, a refused credential — because the first week against a real
gateway is mostly failures.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging

import httpx
import pytest

from application.ai.settings import AiSettings
from domain.ai import (
    AgentSpec, ChatMessage, ModelAuth, ModelBadRequest, ModelRateLimited, ModelTimeout, ModelUnavailable,
    ModelUsage, StreamEnd, TextDelta, ToolCall, ToolSpec,
)
from infrastructure.ai.auth import build_authenticator
from infrastructure.ai.chat_model_runtime import ChatModelAgentRuntime
from infrastructure.ai.openai_compatible import OpenAICompatibleChatModel
from infrastructure.ai.openai_wire import build_body, build_headers, build_url, retry_after_seconds
from tests.mock_gateway import gateway, settings

MSGS = [ChatMessage("system", "Narrate."), ChatMessage("user", "Say hello")]


def model(client, **cfg):
    gw = settings(**cfg)
    return OpenAICompatibleChatModel(gw, build_authenticator(gw, client=client), client=client)


def drain(chat, messages=MSGS, **kw):
    async def go():
        return [e async for e in chat.stream(messages, model="mock-model", **kw)]

    return asyncio.run(go())


def text(events):
    return "".join(e.text for e in events if isinstance(e, TextDelta))


# ------------------------------------------------------------------- dialects


def test_the_openai_v1_url_and_body_carry_the_model_in_the_body():
    gw = settings()
    assert build_url(gw, "m") == "https://mock.invalid/v1/chat/completions"
    body = build_body(gw, "m", MSGS, temperature=0.2, tools=[], stream=True)
    assert body["model"] == "m" and body["stream_options"] == {"include_usage": True}


def test_the_azure_deployments_url_carries_the_model_in_the_path_and_not_the_body():
    gw = settings(api_style="azure_deployments", api_version="2024-10-21")
    assert build_url(gw, "gpt 4") == "https://mock.invalid/openai/deployments/gpt%204/chat/completions?api-version=2024-10-21"
    assert "model" not in build_body(gw, "gpt 4", MSGS, temperature=None, tools=[], stream=False)


def test_both_dialects_work_against_the_mock():
    for style in ("openai_v1", "azure_deployments"):
        state, client, _ = gateway()
        state.responses.append({"text": "ok then"})
        assert text(drain(model(client, api_style=style))) == "ok then"
        assert state.log[0]["model"] == "mock-model"


def test_auth_headers_win_a_collision_with_extra_headers_and_extras_are_sent():
    gw = settings(extra_headers={"X-Tenant": "t1", "Authorization": "Bearer wrong"})
    headers = build_headers(gw, {"Authorization": "Bearer right"}, "rid", True)
    assert headers["Authorization"] == "Bearer right" and headers["X-Tenant"] == "t1"
    assert headers["Accept"] == "text/event-stream" and headers["X-Request-Id"] == "rid"


# ------------------------------------------------------------ streaming, usage


def test_streaming_yields_deltas_usage_and_the_end_with_a_finish_reason():
    state, client, _ = gateway()
    state.responses.append({"text": "The credit is recorded"})
    events = drain(model(client), temperature=0.2)
    assert text(events) == "The credit is recorded"
    usage = [e for e in events if isinstance(e, ModelUsage)][0]
    assert usage.input_tokens > 0 and usage.output_tokens == 4
    assert events[-1] == StreamEnd(provider="gateway", model="mock-model", finish_reason="stop")
    entry = state.log[0]
    assert entry["stream"] and entry["roles"] == ["system", "user"] and entry["request_id"]
    assert entry["user_agent"].startswith("tax-credit-copilot/")


def test_non_streaming_mode_reads_one_body():
    state, client, _ = gateway()
    state.responses.append({"text": "whole answer"})
    events = drain(model(client, streaming=False))
    assert text(events) == "whole answer" and state.log[0]["stream"] is False
    assert any(isinstance(e, ModelUsage) for e in events)


# ---------------------------------------------------------------- tool calling


TOOL = ToolSpec("client_situation", "Brief on one client", {"type": "object", "properties": {"client_id": {"type": "integer"}}})


@pytest.mark.parametrize("streaming", [True, False])
def test_tool_calls_come_back_complete_for_the_caller_to_run(streaming):
    state, client, _ = gateway()
    state.responses.append({"tool_calls": [{"name": "client_situation", "arguments": {"client_id": 2001}}]})
    events = drain(model(client, streaming=streaming), tools=[TOOL])
    calls = [e for e in events if isinstance(e, ToolCall)]
    assert [(c.name, json.loads(c.arguments)) for c in calls] == [("client_situation", {"client_id": 2001})]
    assert events[-1].finish_reason == "tool_calls" and state.log[0]["tools"] == ["client_situation"]


def test_a_tool_result_message_is_accepted_on_the_next_turn():
    state, client, _ = gateway()
    state.responses.append({"text": "Done"})
    history = [*MSGS, ChatMessage("assistant", tool_calls=(ToolCall("call_0", "client_situation", "{}"),)),
               ChatMessage("tool", '{"ok": true}', tool_call_id="call_0")]
    assert text(drain(model(client), history)) == "Done"
    assert state.log[0]["roles"] == ["system", "user", "assistant", "tool"]


def test_an_agent_runtime_never_runs_or_forwards_a_tool_call():
    state, client, _ = gateway()
    state.responses.append({"text": "Hi", "tool_calls": [{"name": "x", "arguments": {}}]})
    runtime = ChatModelAgentRuntime(model(client), AiSettings(models={"narrator__gateway": "mock-model"}))

    async def go():
        return [e async for e in runtime.stream(AgentSpec(name="ReportingAgent", instructions="I"), "p")]

    events = asyncio.run(go())
    assert not any(isinstance(e, ToolCall) for e in events) and text(events) == "Hi"
    assert state.log[0]["tools"] == [], "agents hold no tools"


# --------------------------------------------------------------- authentication


def test_api_key_in_a_custom_header_with_a_prefix():
    state, client, _ = gateway(auth="api_key", api_key="s3cret", api_key_header="x-api-key", api_key_prefix="")
    assert text(drain(model(client, auth="api_key", api_key="s3cret", api_key_header="x-api-key", api_key_prefix=""))) != ""
    assert state.log[0]["auth_ok"]


def test_a_wrong_api_key_is_an_auth_error_not_a_retryable_one():
    _, client, _ = gateway(auth="api_key", api_key="right")
    with pytest.raises(ModelAuth):
        drain(model(client, auth="api_key", api_key="wrong"))


class _Clock:
    now = 1000.0

    def __call__(self):
        return self.now


def test_oauth_fetches_once_caches_and_refreshes_before_expiry():
    state, client, _ = gateway(auth="oauth", token_ttl_s=300)
    gw = settings(auth="oauth_client_credentials", oauth_token_url="https://mock.invalid/oauth/token",
                  oauth_client_id="mock-client", oauth_client_secret="mock-secret")
    from infrastructure.ai.auth.oauth_client_credentials import OAuthClientCredentials

    clock = _Clock()
    auth = OAuthClientCredentials(gw, client=client, clock=clock)
    chat = OpenAICompatibleChatModel(gw, auth, client=client)
    drain(chat), drain(chat)
    assert auth.fetches == 1 and all(e["auth_ok"] for e in state.log)
    clock.now += 241  # 300s lifetime less the 60s skew
    drain(chat)
    assert auth.fetches == 2


def test_oauth_concurrent_callers_share_one_refresh():
    _, client, _ = gateway(auth="oauth")
    gw = settings(auth="oauth_client_credentials", oauth_token_url="https://mock.invalid/oauth/token",
                  oauth_client_id="mock-client", oauth_client_secret="mock-secret")
    from infrastructure.ai.auth.oauth_client_credentials import OAuthClientCredentials

    auth = OAuthClientCredentials(gw, client=client)

    async def go():
        return await asyncio.gather(*(auth.headers() for _ in range(8)))

    results = asyncio.run(go())
    assert auth.fetches == 1 and len({r["Authorization"] for r in results}) == 1


def test_oauth_bad_client_credentials_are_an_auth_error():
    _, client, _ = gateway(auth="oauth")
    gw = settings(auth="oauth_client_credentials", oauth_token_url="https://mock.invalid/oauth/token",
                  oauth_client_id="mock-client", oauth_client_secret="WRONG")
    with pytest.raises(ModelAuth):
        drain(OpenAICompatibleChatModel(gw, build_authenticator(gw, client=client), client=client))


def test_a_401_drops_the_cached_oauth_token_so_the_next_call_refetches():
    state, client, _ = gateway(auth="oauth")
    gw = settings(auth="oauth_client_credentials", oauth_token_url="https://mock.invalid/oauth/token",
                  oauth_client_id="mock-client", oauth_client_secret="mock-secret")
    from infrastructure.ai.auth.oauth_client_credentials import OAuthClientCredentials

    auth = OAuthClientCredentials(gw, client=client)
    chat = OpenAICompatibleChatModel(gw, auth, client=client)
    drain(chat)
    state.tokens.clear()  # the gateway rotated its keys
    with pytest.raises(ModelAuth):
        drain(chat)
    assert text(drain(chat)) and auth.fetches == 2


def _jwt(aud: str) -> str:
    seg = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"{seg({'alg': 'none'})}.{seg({'aud': aud})}.sig"


class _FakeCredential:
    def __init__(self, aud):
        self.aud, self.scopes = aud, []

    def get_token(self, scope):
        self.scopes.append(scope)
        return type("T", (), {"token": _jwt(self.aud)})()


def test_entra_token_authenticates_with_the_managed_identity_and_asks_for_the_default_scope():
    state, client, _ = gateway(auth="entra", entra_audience="api://mock-gateway")
    gw = settings(auth="entra_token", entra_audience="api://mock-gateway")
    credential = _FakeCredential("api://mock-gateway")
    chat = OpenAICompatibleChatModel(gw, build_authenticator(gw, credential=credential), client=client)
    assert text(drain(chat))
    assert credential.scopes == ["api://mock-gateway/.default"] and state.log[0]["auth_ok"]


def test_an_entra_token_for_another_audience_is_refused():
    _, client, _ = gateway(auth="entra", entra_audience="api://mock-gateway")
    gw = settings(auth="entra_token", entra_audience="api://other")
    chat = OpenAICompatibleChatModel(gw, build_authenticator(gw, credential=_FakeCredential("api://other")), client=client)
    with pytest.raises(ModelAuth):
        drain(chat)


def test_a_credential_failure_is_an_auth_error():
    class Broken:
        def get_token(self, scope):
            raise RuntimeError("no managed identity")

    gw = settings(auth="entra_token", entra_audience="api://x")
    chat = OpenAICompatibleChatModel(gw, build_authenticator(gw, credential=Broken()))
    with pytest.raises(ModelAuth):
        drain(chat)


# --------------------------------------------------------------------- failures


@pytest.mark.parametrize("fault, expected", [
    ({"kind": "status", "code": 500}, ModelUnavailable),
    ({"kind": "status", "code": 503}, ModelUnavailable),
    ({"kind": "status", "code": 400}, ModelBadRequest),
    ({"kind": "status", "code": 422}, ModelBadRequest),
    ({"kind": "status", "code": 429, "retry_after": 3}, ModelRateLimited),
    ({"kind": "disconnect_mid_stream", "after": 1}, ModelUnavailable),
    ({"kind": "malformed_sse"}, ModelUnavailable),
])
def test_gateway_failures_map_onto_the_taxonomy(fault, expected):
    state, client, _ = gateway()
    state.responses.append({"text": "one two three four"})
    state.faults.append(fault)
    with pytest.raises(expected):
        drain(model(client))


def test_a_rate_limit_carries_retry_after_seconds_and_a_http_date():
    state, client, _ = gateway()
    state.faults.append({"kind": "status", "code": 429, "retry_after": 3})
    with pytest.raises(ModelRateLimited) as caught:
        drain(model(client))
    assert caught.value.retry_after == 3.0
    assert retry_after_seconds("120") == 120.0 and retry_after_seconds(None) is None and retry_after_seconds("nonsense") is None
    assert retry_after_seconds("Wed, 21 Oct 2026 07:28:00 GMT", now=1792567650) == pytest.approx(30.0, abs=1)


@pytest.mark.parametrize("raised, expected", [
    (httpx.ReadTimeout("slow"), ModelTimeout),
    (httpx.ConnectTimeout("slow"), ModelTimeout),
    (httpx.ConnectError("refused"), ModelUnavailable),
    (httpx.RemoteProtocolError("reset"), ModelUnavailable),
])
def test_transport_failures_map_onto_the_taxonomy(raised, expected):
    def handler(request):
        raise raised

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(expected):
        drain(model(client))


def test_an_error_message_never_echoes_the_response_body_or_the_prompt():
    def handler(request):
        return httpx.Response(400, json={"error": "your prompt was: Say hello"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ModelBadRequest) as caught:
        drain(model(client))
    assert "Say hello" not in str(caught.value) and "status 400" in str(caught.value)


def test_a_request_logs_neither_the_prompt_nor_a_header(caplog):
    state, client, _ = gateway(auth="api_key", api_key="TOPSECRETKEY")
    state.responses.append({"text": "fine"})
    with caplog.at_level(logging.DEBUG):
        drain(model(client, auth="api_key", api_key="TOPSECRETKEY"), [ChatMessage("user", "PRIVATE BRIEF TEXT")])
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "TOPSECRETKEY" not in logged and "PRIVATE BRIEF TEXT" not in logged


def test_a_secret_is_not_in_a_repr():
    gw = settings(auth="api_key", api_key="TOPSECRETKEY", oauth_client_secret="ALSOSECRET")
    assert "TOPSECRETKEY" not in repr(gw) and "ALSOSECRET" not in repr(gw)
    assert "TOPSECRETKEY" not in repr(build_authenticator(gw))
