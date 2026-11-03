"""The gateway's HTTP surface. [CH-06]

Thin: authenticate, bound the body, dispatch to the pipeline, shape the response.
Nothing else is routed (the app serves no docs or schema; `channel_route_inventory.json`
pins the list), so the public surface is exactly what is registered here.

    GET    /channel/health            liveness, no credentials
    GET    /channel/ready             readiness, no credentials
    GET    /channel/v1/tools          the tools this caller may use
    POST   /channel/v1/tools/{tool}   run one tool
    GET    /channel/v1/downloads/{t}  a claim package, by ticket (a token is optional)
    POST   /mcp                       the MCP facade (Cowork)
    GET    /mcp                       405: this server never opens a stream to the client
    DELETE /mcp                       end the caller's MCP session
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError

from channel.auth import AuthFailure, Caller
from channel.config import MAX_REQUEST_BYTES
from channel.pipeline import ToolCall, error_outcome
from channel.tools import offered_tools
from channel.wiring import Services


class ToolRequest(BaseModel):
    """The body of a tool call; the same shape the API takes."""

    args: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=200)
    confirmation_token: str | None = Field(default=None, max_length=500)


def _json(status: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content=body, headers=headers or {})


def _refusal(exc: AuthFailure) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else {}
    return _json(exc.status, {"error": {"code": exc.code, "message": exc.message, "retryable": False}}, headers)


def _headers(request: Request) -> dict[str, str]:
    return {k.lower(): v for k, v in request.headers.items()}


async def _bounded_body(request: Request) -> bytes | None:
    """The body, or None when it is larger than the cap (checked before and while reading)."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_REQUEST_BYTES:
        return None
    data = b""
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_REQUEST_BYTES:
            return None
    return data


def _too_large() -> JSONResponse:
    message = f"the body exceeds {MAX_REQUEST_BYTES} bytes"
    return _json(413, {"error": {"code": "request_too_large", "message": message, "retryable": False}})


def _mcp_response(reply: Any) -> Response:
    if reply.body is None:
        return Response(status_code=reply.status, headers=reply.headers)
    return JSONResponse(status_code=reply.status, content=reply.body, headers=reply.headers)


class GatewayRoutes:
    """The handlers, bound to the composed services."""

    def __init__(self, services: Services) -> None:
        self._s = services

    def _authenticate(self, request: Request) -> Caller:
        return self._s.authenticator.authenticate(_headers(request))

    def health(self) -> dict[str, str]:
        """Liveness: the process serves."""
        return {"status": "ok"}

    def ready(self) -> dict[str, Any]:
        """Readiness: configuration was accepted and the app is built."""
        return {"ready": True, "store": self._s.settings.channel_store}

    def tools(self, request: Request) -> JSONResponse:
        """The catalog this caller may use."""
        try:
            self._authenticate(request)
        except AuthFailure as exc:
            return _refusal(exc)
        return _json(200, {"tools": [t.to_dict() for t in offered_tools(self._s.settings)]})

    async def run_tool(self, tool: str, request: Request) -> JSONResponse:
        """Run one tool for the authenticated caller through the pipeline."""
        try:
            caller = self._authenticate(request)
        except AuthFailure as exc:
            return _refusal(exc)
        raw = await _bounded_body(request)
        if raw is None:
            return _too_large()
        try:
            call = ToolRequest.model_validate_json(raw or b"{}")
        except ValidationError:
            message = "the body must be {args, idempotency_key?, confirmation_token?}"
            out = error_outcome(422, "invalid_request", message, caller.acting.correlation_id or "")
            return _json(out.status, out.body)
        outcome = await self._s.pipeline.run(
            caller, tool, ToolCall(call.args, call.idempotency_key, call.confirmation_token, _headers(request)),
        )
        return _json(outcome.status, outcome.body, outcome.headers)

    async def download(self, ticket: str, request: Request) -> Response:
        """A claim package by ticket; a token, when given, must be the ticket's person's."""
        caller = None
        if request.headers.get("authorization"):
            try:
                caller = self._authenticate(request)
            except AuthFailure as exc:
                return _refusal(exc)
        address = request.client.host if request.client else "unknown"
        result = await self._s.downloads.serve(ticket, caller, address)
        if result.error is not None:
            return _json(result.status, result.error, result.headers)
        others = {k: v for k, v in result.headers.items() if k.lower() != "content-type"}
        return Response(result.data, media_type=result.headers.get("content-type"), headers=others)

    async def mcp_post(self, request: Request) -> Response:
        """One MCP JSON-RPC message."""
        raw = await _bounded_body(request)
        if raw is None:
            return _too_large()
        return _mcp_response(await self._s.mcp.handle(_headers(request), raw, str(request.base_url)))

    def mcp_get(self) -> Response:
        """No server-to-client stream is offered."""
        return Response(status_code=405, headers={"Allow": "POST, DELETE"})

    def mcp_delete(self, request: Request) -> Response:
        """End the caller's own MCP session."""
        return _mcp_response(self._s.mcp.close(_headers(request)))


def build_router(services: Services) -> APIRouter:
    """The router: every route the gateway serves, and no other."""
    routes, router = GatewayRoutes(services), APIRouter()
    router.add_api_route("/channel/health", routes.health, methods=["GET"])
    router.add_api_route("/channel/ready", routes.ready, methods=["GET"])
    router.add_api_route("/channel/v1/tools", routes.tools, methods=["GET"])
    router.add_api_route("/channel/v1/tools/{tool}", routes.run_tool, methods=["POST"])
    router.add_api_route("/channel/v1/downloads/{ticket}", routes.download, methods=["GET"])
    router.add_api_route("/mcp", routes.mcp_post, methods=["POST"])
    router.add_api_route("/mcp", routes.mcp_get, methods=["GET"])
    router.add_api_route("/mcp", routes.mcp_delete, methods=["DELETE"])
    return router
