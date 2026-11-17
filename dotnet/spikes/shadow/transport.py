"""Total async deadlines and streamed byte limits apply before parsing any payload."""
import asyncio
from dataclasses import dataclass

from catalogue import Refused, admitted_case, check_rows, origin, request_path


@dataclass(frozen=True)
class Target:
    address: str
    bearer: str | None = None
    local: bool = False


async def read(client, target: Target, case: str, account: int, year: int) -> dict:
    from contract.exchange import describe_body, selected_headers

    spec = admitted_case(case)
    address = origin(target.address, local=target.local)
    path = request_path(case, account, year, "GA_JTC", "min_max")
    headers = {"Accept-Encoding": "identity"}
    if target.bearer:
        headers["Authorization"] = "Bearer " + target.bearer
    async with asyncio.timeout(spec.seconds):
        async with client.stream("GET", address + path, headers=headers) as reply:
            if ("json" not in reply.headers.get("content-type", "").lower()
                    or reply.headers.get("content-encoding", "identity").lower() != "identity"
                    or len(reply.headers.raw) > 64
                    or sum(len(k) + len(v) for k, v in reply.headers.raw) > 32768):
                raise Refused("response-kind-or-header-bound")
            content = bytearray()
            async for chunk in reply.aiter_bytes():
                if len(content) + len(chunk) > spec.bytes:
                    raise Refused("response-bound")
                content.extend(chunk)
            body = describe_body(reply.headers, bytes(content))
            if body["kind"] != "json":
                raise Refused("invalid-json")
            check_rows(body["value"], spec.rows)
            return {"status": reply.status_code, "headers": selected_headers(reply.headers), "body": body}
