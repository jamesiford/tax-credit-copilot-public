"""The data tools behind the orchestrator's fake gateway: the real capabilities over a SQLite database. [CH-16d]

The orchestrator tests answer most tools with canned envelopes. For the data tools the point is the
LANES, so the reply is the real capability's own envelope (real blocks, real `user_only_facts`), run
through the real `invoke` (schema check, typed failures) over the shared two-client database. What a
test then asserts about a prompt is asserted about the shipped envelope, not about a stand-in.
"""
from __future__ import annotations

from typing import Any

from application.capabilities.invoke import CapabilityFailure, invoke
from application.channel_wiring import set_writer_entitlement
from application.data_wiring import set_data_query_service
from tests.data_caps_fixture import Writers, make_service, person

DATA_TOOLS = frozenset({"data_catalog", "data_query", "data_distinct_values"})
_service = None


def data_reply(tool: str, args: dict[str, Any], oid: str, channel: str = "teams") -> tuple[int, dict[str, Any]]:
    """`(status, body)` exactly as the gateway would forward the API's answer."""
    global _service
    _service = _service or make_service()
    set_data_query_service(_service)  # another test may have cleared it since the last call
    set_writer_entitlement(Writers())
    try:
        return 200, invoke(tool, args, person(oid, channel)).to_dict()
    except CapabilityFailure as failure:
        return failure.status, failure.body()
