"""The MCP facade: the same tools, for Cowork. [CH-06]

A minimal Streamable-HTTP MCP server (`initialize`, `notifications/initialized`,
`ping`, `tools/list`, `tools/call`) over `POST /mcp`, answering each request with
one JSON body. It is written here rather than taken from the `mcp` SDK because every
call must pass through the gateway's one pipeline — identity, rate limit, writer
check, audit, fact ledger — and the SDK's session manager runs handlers in
session-scoped tasks, away from the request that carries the token. See D-65.

Identity is the same validation as REST (a Cowork user's delegated token); the MCP
session id is the conversation id, so `verify_figures` and the audit see one
conversation across calls. Sessions are in memory and bound to the user who opened
them: another user presenting the id is told it is unknown, and after a restart every
session is unknown, which the protocol defines as "initialise again".

Writes appear as the two-step pair, and the descriptions say so: a model that reads
"returns a preview — nothing is changed until the matching commit tool is called"
will not treat the preview as the change.
"""
from __future__ import annotations

import json
import time
import uuid
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from application.capabilities import catalog
from application.capabilities.catalog import PREVIEW_SENTENCE  # noqa: F401 - the facade's callers read the sentence from here; the catalog owns it
from channel.auth import AuthFailure, CallerAuthenticator
from channel.people import CallerPeople
from channel.pipeline import ToolCall, ToolPipeline
from channel.render import render_error_text, render_tool_text
from channel.tools import offered_tools

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
SESSION_HEADER = "mcp-session-id"
SESSION_TTL_SECONDS = 8 * 3600
MAX_SESSIONS = 5000
_PARSE_ERROR, _INVALID_REQUEST, _METHOD_NOT_FOUND, _INVALID_PARAMS = -32700, -32600, -32601, -32602


@dataclass(frozen=True)
class McpReply:
    """An HTTP answer: a status, an optional JSON body and headers."""

    status: int
    body: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)


def _rpc_error(request_id: Any, code: int, message: str, status: int = 200) -> McpReply:
    return McpReply(status, {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def _rpc_result(request_id: Any, result: Mapping[str, Any], headers: dict[str, str] | None = None) -> McpReply:
    return McpReply(200, {"jsonrpc": "2.0", "id": request_id, "result": dict(result)}, headers or {})


def _parse(raw: bytes) -> dict[str, Any] | McpReply:
    """The one JSON-RPC request in `raw`, or the protocol error that says why it is not."""
    try:
        message = json.loads(raw.decode("utf-8"))
    except ValueError:
        return _rpc_error(None, _PARSE_ERROR, "the body is not JSON", 400)
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return _rpc_error(None, _INVALID_REQUEST, "expected one JSON-RPC 2.0 request", 400)
    return message


def describe(spec: catalog.CapabilitySpec) -> dict[str, Any]:
    """One tool as `tools/list` shows it: schema, honest description, behaviour hints, all from the catalog."""
    return {
        "name": spec.name, "title": spec.name.replace("_", " ").capitalize(), "description": catalog.channel_description(spec),
        "inputSchema": spec.schema, "annotations": catalog.behaviour_hints(spec),
    }


class McpServer:
    """Speaks MCP over a request/response transport, delegating every tool call to the pipeline."""

    def __init__(
        self, authenticator: CallerAuthenticator, pipeline: ToolPipeline, settings: Any, name: str, version: str,
        people: CallerPeople | None = None,
    ) -> None:
        self._auth, self._pipeline, self._settings = authenticator, pipeline, settings
        self._people = people or CallerPeople(None)
        self._info = {"name": name, "version": version}
        self._sessions: OrderedDict[str, tuple[str, float]] = OrderedDict()

    # --------------------------------------------------------------------- sessions

    def _open_session(self, oid: str) -> str:
        now, session = time.monotonic(), uuid.uuid4().hex
        self._sessions[session] = (oid, now)
        while len(self._sessions) > MAX_SESSIONS:
            self._sessions.popitem(last=False)
        return session

    def _session_owner(self, session: str | None) -> str | None:
        held = self._sessions.get(session or "")
        if held is None or time.monotonic() - held[1] > SESSION_TTL_SECONDS:
            self._sessions.pop(session or "", None)
            return None
        return held[0]

    def close(self, headers: Mapping[str, str]) -> McpReply:
        """`DELETE /mcp`: end the caller's own session."""
        try:
            caller = self._auth.authenticate(headers)
        except AuthFailure as exc:
            return McpReply(exc.status, {"error": {"code": exc.code, "message": exc.message}})
        session = headers.get(SESSION_HEADER)
        if self._session_owner(session) != caller.acting.oid:
            return McpReply(404)
        self._sessions.pop(session, None)
        return McpReply(200)

    # --------------------------------------------------------------------- requests

    async def handle(self, headers: Mapping[str, str], raw: bytes, base_url: str) -> McpReply:
        """One JSON-RPC message in, one reply out."""
        message = _parse(raw)
        if isinstance(message, McpReply):
            return message
        session = headers.get(SESSION_HEADER)
        try:
            caller = self._auth.authenticate(headers, conversation_id=session)
        except AuthFailure as exc:
            return McpReply(exc.status, {"error": {"code": exc.code, "message": exc.message}})
        if message.get("id") is None:  # a notification: acknowledged, nothing to answer
            return McpReply(202)
        return await self._dispatch(message, caller, session, headers, base_url)

    async def _dispatch(
        self, message: dict[str, Any], caller: Any, session: str | None, headers: Mapping[str, str], base_url: str,
    ) -> McpReply:
        method, request_id, params = message["method"], message["id"], message.get("params") or {}
        if method == "initialize":
            return self._initialize(request_id, params, caller.acting.oid)
        if self._session_owner(session) != caller.acting.oid:
            return _rpc_error(request_id, _INVALID_REQUEST, "unknown session; initialise again", 404)
        if method == "tools/call":
            return await self._call(request_id, params, caller, headers, base_url)
        if method == "tools/list":
            return _rpc_result(request_id, {"tools": [describe(s) for s in offered_tools(self._settings)]})
        if method == "ping":
            return _rpc_result(request_id, {})
        return _rpc_error(request_id, _METHOD_NOT_FOUND, f"method not found: {method}")

    def _initialize(self, request_id: Any, params: Mapping[str, Any], oid: str) -> McpReply:
        asked = params.get("protocolVersion")
        version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        result = {
            "protocolVersion": version, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": self._info,
            "instructions": "Every figure these tools return is the platform's own. Quote figures exactly as written.",
        }
        return _rpc_result(request_id, result, {"Mcp-Session-Id": self._open_session(oid)})

    async def _call(self, request_id: Any, params: Mapping[str, Any], caller: Any, headers: Mapping[str, str], base_url: str) -> McpReply:
        name, arguments = params.get("name"), params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return _rpc_error(request_id, _INVALID_PARAMS, "tools/call needs a tool name and an arguments object")
        if all(t.name != name for t in offered_tools(self._settings)):
            return _rpc_error(request_id, _INVALID_PARAMS, f"unknown tool: {name}")
        caller = await self._people.enrich(caller)
        outcome = await self._pipeline.run(caller, name, ToolCall(args=arguments, headers=headers))
        failed = outcome.status != 200
        text = render_error_text(outcome.body["error"]) if failed else render_tool_text(outcome.body, base_url)
        return _rpc_result(request_id, {
            "content": [{"type": "text", "text": text}], "structuredContent": outcome.body, "isError": failed,
        })
