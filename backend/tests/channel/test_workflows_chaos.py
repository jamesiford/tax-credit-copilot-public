"""When things go wrong between the person and the engine. [CH-11]

Each failure below is one a real deployment has: the API is slow or gone, a caller is too
fast or sends too much, a confirmation is replayed, tampered with or too old, a writer is
removed in the middle of a conversation. What must hold is the same each time: the answer is
a structured error with a stable code (never a stack, never an estimate), the audit trail
closes the call, and nothing is written that should not be.

The last tests are about the guard itself: a capability whose figures disagree with its own
words is caught, and the one thing a value-matching guard cannot see is pinned rather than hidden.
"""
from __future__ import annotations

import time
from typing import Any

import httpx
import pytest

from bootstrap import wiring
from application.capabilities import registry
from application.capabilities.envelope import Block, Provenance, ToolResult
from domain.channel import WriterGrant
from gateway_harness import agent_headers, user_headers, user_token
from test_capabilities_envelope import unexplained_numerals
from workflow_harness import (  # noqa: F401 - fixtures
    OTHER_OID, PAYROLL_CLIENT, THIRD_OID, USER_OID, McpSurface, build_flow, entra, flow, gold, money_mutations,
    platform_text, service, surface, world,
)

ENGAGE = {"client_id": 2001, "program_code": "GA_JTC", "scope": "in_scope", "note": "signed"}
TRANSITION = {"client_id": PAYROLL_CLIENT, "program_code": "GA_JTC", "tax_year": 2024, "status": "proposed"}


class Flaky(httpx.AsyncBaseTransport):
    """The road to the API, with one fault injected for requests to a path containing `needle`."""

    def __init__(self, inner: httpx.AsyncBaseTransport, needle: str, fault: Exception) -> None:
        self.inner, self.needle, self.fault = inner, needle, fault

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self.needle in request.url.path:
            raise self.fault
        return await self.inner.handle_async_request(request)


def ends(flow, tool: str, oid: str = USER_OID):
    return [e for e in flow.events(oid) if e.tool_name == tool and e.phase in ("end", "single")]


# ------------------------------------------------------------------ the API misbehaves


def test_a_slow_capability_is_a_structured_timeout_and_the_trail_closes(flow, surface, monkeypatch):
    monkeypatch.setenv("CAPABILITY_TIMEOUT_SECONDS", "1")
    monkeypatch.setitem(registry.FUNCTIONS, "client_trend", lambda client_id: time.sleep(1.3))
    reply = surface.call("client_trend", {"client_id": 2001})
    assert not reply.ok and reply.error_code == "timeout" and reply.body["error"]["retryable"] is True
    assert [e.outcome for e in ends(flow, "client_trend")] == ["error"]


@pytest.mark.parametrize(("fault", "code"), [(httpx.ReadTimeout("slow"), "timeout"), (httpx.ConnectError("no route"), "api_unreachable")],
                         ids=["no-answer", "no-route"])
def test_a_broken_road_to_the_api_is_a_structured_error_and_the_trail_closes(tmp_path, world, service, gold, request, monkeypatch, fault, code):
    from application import client_book
    from workflow_harness import BOOK, PAYROLL_ROW, UNASSESSED_ROW, seed_claims

    monkeypatch.setattr(client_book, "clients", lambda: [*BOOK, PAYROLL_ROW, UNASSESSED_ROW])
    seed_claims()
    request.getfixturevalue("entra")
    import main

    broken = build_flow(tmp_path, world, Flaky(httpx.ASGITransport(app=main.app), "client_trend", fault))
    for kind in ("rest", "mcp"):
        reply = broken.surface(kind).call("client_trend", {"client_id": 2001})
        assert not reply.ok and reply.error_code == code and reply.body["error"]["retryable"] is True
        assert broken.surface(kind).call("book_rank").ok, "one broken tool does not take the others down"
    assert [e.outcome for e in ends(broken, "client_trend")] == ["error", "error"]


# --------------------------------------------------------------------- callers misbehave


def test_a_caller_that_is_too_fast_is_slowed_and_only_that_caller(flow, tmp_path, world):
    limited = build_flow(tmp_path, world, rate_limit_per_minute=3)
    fast, calm = limited.surface("rest"), limited.surface("rest", OTHER_OID)
    assert all(fast.call("book_rank").ok for _ in range(3))
    refused = fast.call("book_rank")
    assert not refused.ok and refused.error_code == "rate_limited" and refused.body["error"]["retryable"] is True
    assert calm.call("book_rank").ok, "the limit is per person"
    assert [e.outcome for e in ends(limited, "book_rank") if e.phase == "single"] == ["refused"]


def test_an_oversized_request_is_refused_before_anything_runs(flow):
    big = {"args": {"draft_text": "x" * 70_000}}
    rest = flow.gw.client.post("/channel/v1/tools/verify_figures", json=big, headers=agent_headers())
    assert rest.status_code == 413 and rest.json()["error"]["code"] == "request_too_large"
    mcp = flow.gw.client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"arguments": big["args"]}},
                              headers=user_headers(user_token()))
    assert mcp.status_code == 413
    assert not [e for e in flow.events() if e.tool_name == "verify_figures"], "nothing was run, so nothing is recorded as run"


# ------------------------------------------------------------- confirmations misbehave


def writes_made(flow) -> int:
    return len(flow.history(PAYROLL_CLIENT, "GA_JTC", 2024))


def test_a_retried_commit_is_a_replay_and_writes_once(flow, surface):
    before = writes_made(flow)
    prepared = surface.call("claim_transition_prepare", TRANSITION)
    first = surface.commit("claim_transition", TRANSITION, prepared.token, "retry-1")
    again = surface.commit("claim_transition", TRANSITION, prepared.token, "retry-1")
    assert first.ok and first.facts["replayed"] is False and again.ok and again.facts["replayed"] is True
    assert writes_made(flow) == before + 1


def test_a_used_token_cannot_be_spent_again_under_a_new_key(flow, surface):
    prepared = surface.call("claim_transition_prepare", TRANSITION)
    assert surface.commit("claim_transition", TRANSITION, prepared.token, "key-a").ok
    before = writes_made(flow)
    second = surface.commit("claim_transition", TRANSITION, prepared.token, "key-b")
    assert not second.ok and second.error_code == "confirmation_replayed" and writes_made(flow) == before


def test_a_commit_for_other_arguments_is_refused_whatever_the_token(flow, surface):
    prepared = surface.call("engagement_set_prepare", ENGAGE)
    changed = {**ENGAGE, "scope": "out_of_scope"}
    refused = surface.commit("engagement_set", changed, prepared.token, "swap-1")
    assert not refused.ok and refused.error_code.startswith("confirmation_")
    assert flow.world.claims.engagements(2001) == []
    wrong_tool = surface.commit("claim_transition", TRANSITION, prepared.token, "swap-2")
    assert not wrong_tool.ok and wrong_tool.error_code.startswith("confirmation_")


def test_a_token_belongs_to_the_person_it_was_made_for(flow, surface):
    flow.world.writers.grant(WriterGrant(user_oid=THIRD_OID, added_by="test"))
    prepared = surface.call("engagement_set_prepare", ENGAGE)
    thief = flow.surface("rest", THIRD_OID)
    refused = thief.commit("engagement_set", ENGAGE, prepared.token, "theft-1")
    assert not refused.ok and refused.error_code == "confirmation_wrong_user" and flow.world.claims.engagements(2001) == []
    assert surface.commit("engagement_set", ENGAGE, prepared.token, "mine-1").ok, "the rightful owner's token survived the attempt"


def test_a_preview_that_has_waited_too_long_cannot_be_confirmed(flow, surface, monkeypatch):
    monkeypatch.setattr("application.deployment.confirm_ttl_seconds", lambda env=None: 1)
    prepared = surface.call("engagement_set_prepare", ENGAGE)
    time.sleep(1.2)
    late = surface.commit("engagement_set", ENGAGE, prepared.token, "late-1")
    assert not late.ok and late.error_code == "confirmation_expired" and flow.world.claims.engagements(2001) == []


def test_a_writer_removed_mid_conversation_is_refused_at_the_next_commit(flow, surface):
    prepared = surface.call("engagement_set_prepare", ENGAGE)
    assert prepared.ok
    assert flow.world.writers.revoke(USER_OID)
    refused = surface.commit("engagement_set", ENGAGE, prepared.token, "revoked-1")
    assert not refused.ok and refused.error_code == "not_authorized" and flow.world.claims.engagements(2001) == []
    assert not surface.call("engagement_set_prepare", ENGAGE).ok, "and cannot ask for a new preview either"
    assert surface.call("book_rank").ok, "reading is unaffected"
    assert [e.outcome for e in ends(flow, "engagement_set_commit")] == ["refused"]


# ------------------------------------------------------------------- the guard itself


def corrupted() -> ToolResult:
    """Facts say 31500.00; the words say $31,600.00. The kind of divergence a formatter bug would cause."""
    return ToolResult(
        tool="client_eligibility", facts={"credit": {"annual_credit_usd": "31500.00"}, "tax_year": 2023},
        blocks=(Block("paragraph", text="The annual credit is $31,600.00 for TY2023."),), provenance=Provenance(run_id="run-1"),
    )


def test_the_envelope_scan_catches_words_that_disagree_with_their_facts(monkeypatch):
    assert unexplained_numerals(corrupted(), {2023}) != []
    honest = ToolResult(tool="x", facts={"credit": "31500.00"}, blocks=(Block("paragraph", text="The annual credit is $31,500.00."),))
    assert unexplained_numerals(honest, set()) == []


def test_a_document_quoting_the_corrupted_words_fails_the_figure_check_end_to_end(flow, surface, monkeypatch):
    monkeypatch.setitem(registry.FUNCTIONS, "client_eligibility", lambda *a, **k: corrupted())
    reply = surface.call("client_eligibility", {"client_id": 2001, "tax_year": 2023})
    assert reply.ok and "$31,600.00" in reply.text, "the platform does not second-guess its own capability at this point"
    verdict = surface.verify(platform_text(reply))
    assert verdict.facts["status"] == "rejected" and "$31,600.00" in {v["token"] for v in verdict.facts["violations"]}
    assert surface.verify("The annual credit is $31,500.00 for TY2023.").facts["status"] == "pass", "the fact it really holds"


def test_the_figure_check_forgets_with_the_process_and_says_no_rather_than_yes(flow, surface):
    text = platform_text(surface.call("client_situation", {"client_id": 2001}))
    assert surface.verify(text).facts["status"] == "pass"
    flow.gw.ledger._items.clear()
    assert surface.verify(text).facts["status"] == "rejected", "a figure that cannot be traced is reported, never waved through"


def test_known_limit_a_wrong_figure_equal_to_another_real_figure_is_not_seen(flow, surface):
    """The guard matches VALUES. '$1' beside a real count of 1 is a figure it cannot call wrong. Documented, not hidden."""
    book = surface.call("book_rank")
    assert 1 in {c["position"] for c in book.facts["clients"]}
    assert surface.verify("The identified credit is $1.").facts["status"] == "pass"
    assert surface.verify("The identified credit is $31,501.").facts["status"] == "rejected"
    assert money_mutations("$140,000 and 1 and $0") == ["$140,001 and 1 and $0"], "the helper leaves collisions out for that reason"

