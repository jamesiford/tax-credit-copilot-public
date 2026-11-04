"""RM-10b: the write path is a MAF Workflow (prepare, the reader's reply, commit), and every guarantee of the old path holds. [CH-08, RM-10b]

The behaviour is the write goldens' (`golden/writes.json`, `writes_more.json`, `known_issues.json`), which were not
edited and run on the workflow. What is pinned here is what the goldens cannot see: the SHAPE of the graph (a model
can start it only at prepare; commit accepts only what the confirmation step makes), that a paused write resumes on
a freshly built graph, that its checkpoint lives in memory only, and that a framework fault never reads as a held
preview, a silent cancel or a retried commit.
"""
from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path

import pytest
from agent_framework import InMemoryCheckpointStorage, Workflow

from app.core import maf_write_flow, replies
from app.core.maf_write_flow import build_write_flow
from app.core.maf_write_steps import Approved, PrepareRequest, WriteContext
from app.core.state import PausedWrite, PendingWrite
from app.core.writes import CommitOutcome
from application.capabilities import catalog
from orch_harness import OTHER_OID, USER_OID, FakeClock, FakeGateway, build_rig, identity

APP = Path(__file__).resolve().parents[3] / "channel_orchestrator" / "app"
ASK = "Mark Cascade's GA_JTC engagement as in scope"
PREPARE = [{"tools": [{"tool": "engagement_set_prepare", "args": {"program_code": "GA_JTC", "scope": "in_scope"}}]}, {"text": "Here is the preview."}]


def state_of(rig, who=None) -> object:
    return rig.pipeline._store.get((who or identity()).key)


async def prepared(rig=None):
    rig = rig or build_rig(list(PREPARE))
    return rig, await rig.say(ASK)


def commit_calls(rig):
    return [c for c in rig.gateway.calls if c.tool.endswith("_commit")]


# ------------------------------------------------------------------ the shape


def graph():
    return build_write_flow(WriteContext(FakeGateway().client(), identity(), FakeClock()), InMemoryCheckpointStorage())


def test_the_graph_is_prepare_then_the_request_step_then_commit_and_nothing_else():
    flow = graph()
    assert list(flow.executors) == ["prepare", "await_confirmation", "commit"] and flow.get_start_executor().id == "prepare"
    edges = {(e.source_id, e.target_id) for g in flow.edge_groups for e in g.edges if not e.source_id.startswith("internal:")}
    assert edges == {("prepare", "await_confirmation"), ("await_confirmation", "commit")}
    assert sorted(e.id for e in flow.get_output_executors()) == ["await_confirmation", "commit"]


def test_the_only_thing_that_can_start_the_workflow_is_a_prepare_request_so_commit_is_unreachable_from_outside():
    flow = graph()
    assert flow.input_types == [PrepareRequest]
    with pytest.raises(Exception):
        asyncio.run(flow.run(Approved(PendingWrite("engagement_set_prepare", {}, "tok", 1e12))))


def test_the_prepare_step_refuses_anything_that_is_not_a_preview():
    for name in ("engagement_set_commit", "client_trend"):
        rig = build_rig([])

        class Turn:
            gateway, who, clock, confirm_ttl_seconds, flow = rig.pipeline._gateway, identity(), FakeClock(), 300, None

            def deadline(self):
                raise AssertionError("no deadline is needed for a tool that is not a preview")

            async def forward(self, spec, args):
                raise AssertionError("nothing may be sent for a tool that is not a preview")

        reply = asyncio.run(maf_write_flow.prepare_write(Turn(), catalog.BY_NAME[name], {}))
        assert not reply.ok and reply.error_code == "write_flow_failed" and rig.gateway.calls == []


def test_the_workflow_holds_no_model_and_no_tool_and_stores_nothing_on_disk():
    allowed = {"Executor", "WorkflowContext", "handler", "register_checkpoint_type", "response_handler", "FunctionInvocationContext",
               "InMemoryCheckpointStorage", "Workflow", "WorkflowBuilder"}
    for name in ("maf_write_steps.py", "maf_write_flow.py"):
        tree = ast.parse((APP / "core" / name).read_text(encoding="utf-8"))
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("agent_framework") for a in n.names}
        assert imported <= allowed, f"{name} reaches past the workflow primitives: {imported - allowed}"


# ------------------------------------------------------------ pause and resume


def test_a_prepare_pauses_the_workflow_in_memory_and_sends_nothing_but_the_preview():
    async def go():
        rig, reply = await prepared()
        held = state_of(rig).write
        assert reply.kind == "answer" and "Reply **confirm**" in reply.text
        assert isinstance(held, PausedWrite) and isinstance(held.storage, InMemoryCheckpointStorage)
        assert rig.gateway.tools_called() == ["client_resolve", "engagement_set_prepare"] and commit_calls(rig) == []
        assert "tok-1" not in repr(held) and "tok-1" not in reply.text
        assert await held.storage.list_checkpoints(workflow_name="tcc-write")

    asyncio.run(go())


def test_the_confirmation_resumes_on_a_freshly_built_graph_and_the_commit_is_sent_once_as_the_person_who_confirmed():
    built: list[Workflow] = []
    original = maf_write_flow.build_write_flow

    def spy(*args, **kwargs):
        built.append(original(*args, **kwargs))
        return built[-1]

    async def go():
        maf_write_flow.build_write_flow = spy
        try:
            rig, _ = await prepared()
            reply = await rig.say("confirm")
        finally:
            maf_write_flow.build_write_flow = original
        assert reply.kind == "commit" and "Done. The change is recorded under your name." in reply.text
        assert len(built) == 2 and built[0] is not built[1], "the graph that resumed is not the one that paused"
        (sent,) = commit_calls(rig)
        prepare = next(c for c in rig.gateway.calls if c.tool == "engagement_set_prepare")
        assert sent.args == prepare.args, "the arguments that were previewed are the arguments that are committed"
        assert sent.body["confirmation_token"] == "tok-1" and re.fullmatch(r"[0-9a-f]{32}", sent.body["idempotency_key"])
        assert sent.headers["x-acting-user-oid"] == USER_OID
        assert state_of(rig).write is None, "cleared: a second confirm finds nothing"
        assert (await rig.say("confirm")).kind == "commit_refused" and len(commit_calls(rig)) == 1

    asyncio.run(go())


def test_somebody_elses_confirm_finds_nothing_and_does_not_touch_the_owners_preview():
    async def go():
        rig = build_rig(list(PREPARE), gateway=FakeGateway(writers={USER_OID, OTHER_OID}))
        await prepared(rig)
        other = await rig.say("confirm", identity(OTHER_OID, name="Sam Reader"))
        assert other.kind == "commit_refused" and replies.NOTHING_PENDING in other.text and commit_calls(rig) == []
        assert state_of(rig).write is not None
        assert (await rig.say("confirm")).kind == "commit"

    asyncio.run(go())


def test_a_confirmation_at_the_expiry_is_refused_and_one_second_before_it_is_not():
    for advance, kind in ((299, "commit"), (300, "commit_refused")):
        async def go(advance=advance, kind=kind):
            rig, _ = await prepared()
            rig.clock.now += advance
            reply = await rig.say("confirm")
            assert reply.kind == kind
            assert (replies.EXPIRED in reply.text) is (kind == "commit_refused") and len(commit_calls(rig)) == (kind == "commit")

        asyncio.run(go())


@pytest.mark.parametrize("code", ["confirmation_expired", "confirmation_replayed", "confirmation_wrong_user", "confirmation_unknown", "not_authorized"])
def test_every_refusal_the_gateway_gives_a_commit_is_reported_and_never_retried(code):
    async def go():
        gateway = FakeGateway()
        gateway.overrides["engagement_set_commit"] = lambda _args: (409, {"error": {"code": code, "message": code, "retryable": False}})
        rig, _ = await prepared(build_rig(list(PREPARE), gateway=gateway))
        reply = await rig.say("confirm")
        assert reply.kind == "commit_refused" and reply.text == replies.commit_failure(code, code)
        assert (await rig.say("confirm")).kind == "commit_refused" and len(commit_calls(rig)) == 1

    asyncio.run(go())


# ------------------------------------------------------ cancel, drop and faults


def test_cancel_resumes_the_workflow_with_a_refusal_so_it_ends_and_nothing_is_sent():
    async def go():
        rig, _ = await prepared()
        reply = await rig.say("cancel")
        assert reply.kind == "cancel" and reply.text == replies.CANCELLED and commit_calls(rig) == []
        assert state_of(rig).write is None
        assert (await rig.say("cancel")).text == replies.NOTHING_PENDING

    asyncio.run(go())


def test_any_other_message_cancels_the_frameworks_pending_request_and_says_the_change_was_dropped():
    dropped: list[list[str]] = []
    original = Workflow.cancel_pending_requests

    async def spy(self, request_ids, **kwargs):
        dropped.append(list(request_ids))
        return await original(self, request_ids, **kwargs)

    async def go():
        Workflow.cancel_pending_requests = spy
        try:
            rig, _ = await prepared()
            rig.chat.script.extend([{"tools": [{"tool": "client_trend", "args": {}}]}, {"text": "The table shows each year."}])
            reply = await rig.say("Actually, how has Cascade trended?")
        finally:
            Workflow.cancel_pending_requests = original
        assert "earlier was dropped" in reply.text and len(dropped) == 1 and len(dropped[0]) == 1
        assert (await rig.say("confirm")).kind == "commit_refused" and commit_calls(rig) == []

    asyncio.run(go())


def test_a_framework_fault_while_dropping_never_blocks_the_answer_or_leaves_the_change_confirmable():
    async def go():
        rig, _ = await prepared()
        original = maf_write_flow.build_write_flow

        def broken(*args, **kwargs):
            raise RuntimeError("the checkpoint store is gone")

        maf_write_flow.build_write_flow = broken
        try:
            rig.chat.script.extend([{"tools": [{"tool": "client_trend", "args": {}}]}, {"text": "The table shows each year."}])
            reply = await rig.say("Actually, how has Cascade trended?")
        finally:
            maf_write_flow.build_write_flow = original
        assert reply.kind == "answer" and "earlier was dropped" in reply.text
        assert (await rig.say("confirm")).kind == "commit_refused" and commit_calls(rig) == []

    asyncio.run(go())


def test_a_framework_fault_while_confirming_says_the_outcome_is_unknown_and_is_not_retried():
    async def go():
        rig, _ = await prepared()
        original = maf_write_flow._resume

        async def broken(*args, **kwargs):
            raise RuntimeError("the workflow could not be resumed")

        maf_write_flow._resume = broken
        try:
            reply = await rig.say("confirm")
        finally:
            maf_write_flow._resume = original
        assert reply.kind == "commit_refused" and "can't say whether it was made" in reply.text and "won't retry" in reply.text
        assert state_of(rig).write is None and (await rig.say("confirm")).kind == "commit_refused" and commit_calls(rig) == []

    asyncio.run(go())


def test_a_framework_fault_while_preparing_is_an_error_and_not_a_preview_that_can_be_confirmed():
    async def go():
        rig = build_rig(list(PREPARE))
        original = maf_write_flow.build_write_flow

        def broken(*args, **kwargs):
            raise RuntimeError("could not build")

        maf_write_flow.build_write_flow = broken
        try:
            reply = await rig.say(ASK)
        finally:
            maf_write_flow.build_write_flow = original
        assert "Reply **confirm**" not in reply.text and state_of(rig).write is None
        assert (await rig.say("confirm")).kind == "commit_refused" and commit_calls(rig) == []

    asyncio.run(go())


def test_a_refused_preview_never_pauses_a_workflow():
    async def go():
        rig = build_rig(list(PREPARE), gateway=FakeGateway(writers=set()))
        reply = await rig.say(ASK)
        assert reply.kind == "failure" and "not entitled" in reply.text and state_of(rig).write is None

    asyncio.run(go())


def test_the_model_can_name_a_preview_but_never_a_commit_and_a_read_never_starts_a_workflow():
    async def go():
        rig = build_rig([{"tools": [{"tool": "engagement_set_commit", "args": {}}, {"tool": "client_trend", "args": {}}]}, {"text": "ok"}])
        reply = await rig.say("How has Cascade trended?")
        assert list(reply.refused) == ["engagement_set_commit"] and state_of(rig).write is None and commit_calls(rig) == []

    asyncio.run(go())


def test_the_confirmation_state_is_the_frameworks_checkpoint_and_not_a_second_copy_of_the_change():
    assert set(PausedWrite.__dataclass_fields__) == {"storage", "checkpoint_id", "request_id"}
    assert "pending" not in __import__("app.core.state", fromlist=["ConversationState"]).ConversationState.__dataclass_fields__
    outcome = CommitOutcome("x", False)
    assert outcome.runs == ()
