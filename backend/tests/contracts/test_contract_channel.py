"""The channel stores' contracts: audit, agent actions, writers, confirmations. [CH-03]

One suite over every adapter: SQLite always, the Warehouse with
`TCC_FABRIC_TESTS=1`. What it pins is what the rest of the system relies on —
that the trail is append-only, that a crash leaves a visible `pending`, that a
confirmation can be consumed exactly once, and that a removal is a stamp.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from domain.channel import (
    AgentActionAudit, ChannelAuditEvent, Confirmation, WriterGrant, collapse,
)

T0 = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def _event(user: str, audit_id: str, *, seq=1, phase="single", outcome="ok", at=T0, **kw) -> ChannelAuditEvent:
    values = dict(
        audit_id=audit_id, event_seq=seq, phase=phase, correlation_id=kw.pop("correlation_id", f"c-{audit_id}"),
        channel="teams", user_oid=user, identity_assurance="channel-asserted", tool_name="book_rank",
        action_kind="read", outcome=outcome, occurred_at=at, request_summary="limit=8",
        request_sha256="a" * 64, user_display_name="Test User", tenant_id="tenant-x",
    )
    values.update(kw)
    return ChannelAuditEvent(**values)


# ----------------------------------------------------------------- audit trail


def test_an_event_round_trips(channel_audit_repo, user_prefix, client_ids):
    user, client = f"{user_prefix}u1", client_ids()
    channel_audit_repo.append(_event(
        user, "a1", client_id=client, tax_year=2023, tool_name="client_eligibility",
        run_id="run-9", trail_sha256="b" * 64, numeric_guard="pass", elapsed_ms=42,
        is_deterministic_path=False, error="boom", user_upn="u1@example.com",
    ))
    [got] = channel_audit_repo.for_user(user)
    assert (got.audit_id, got.phase, got.tool_name, got.client_id, got.tax_year) == (
        "a1", "single", "client_eligibility", client, 2023)
    assert (got.run_id, got.trail_sha256, got.numeric_guard, got.elapsed_ms) == ("run-9", "b" * 64, "pass", 42)
    assert got.is_deterministic_path is False and got.error == "boom" and got.user_upn == "u1@example.com"
    assert got.request_sha256 == "a" * 64 and got.tenant_id == "tenant-x"
    assert abs(got.occurred_at - T0) < timedelta(seconds=1)


def test_an_event_that_names_no_client_is_recorded_too(channel_audit_repo, user_prefix):
    user = f"{user_prefix}u2"
    channel_audit_repo.append(_event(user, "a2"))
    assert [e.client_id for e in channel_audit_repo.for_user(user)] == [None]


def test_the_by_user_read_is_newest_first_filtered_and_limited(channel_audit_repo, user_prefix):
    user, other = f"{user_prefix}u3", f"{user_prefix}u4"
    for n in range(5):
        channel_audit_repo.append(_event(
            user, f"s{n}", at=T0 + timedelta(minutes=n),
            tool_name="client_trend" if n % 2 else "book_rank",
        ))
    channel_audit_repo.append(_event(other, "x", at=T0))

    everything = channel_audit_repo.for_user(user)
    assert [e.audit_id for e in everything] == ["s4", "s3", "s2", "s1", "s0"]
    assert [e.audit_id for e in channel_audit_repo.for_user(user, limit=2)] == ["s4", "s3"]
    window = channel_audit_repo.for_user(user, since=T0 + timedelta(minutes=1), until=T0 + timedelta(minutes=4))
    assert [e.audit_id for e in window] == ["s3", "s2", "s1"]
    assert {e.tool_name for e in channel_audit_repo.for_user(user, tool="client_trend")} == {"client_trend"}
    assert {e.user_oid for e in channel_audit_repo.for_user(other)} == {other}


def test_a_begin_without_an_end_is_visible_and_pending(channel_audit_repo, user_prefix):
    """The crash case: the process died after the write was announced."""
    user = f"{user_prefix}u5"
    channel_audit_repo.append(_event(
        user, "w1", seq=1, phase="begin", outcome="pending", action_kind="write_commit",
        tool_name="claim_transition_commit",
    ))
    channel_audit_repo.append(_event(user, "w2", seq=1, phase="begin", outcome="pending", action_kind="write_commit", at=T0 + timedelta(minutes=1)))
    channel_audit_repo.append(_event(user, "w2", seq=2, phase="end", outcome="ok", action_kind="write_commit", at=T0 + timedelta(minutes=2)))

    entries = {e.audit_id: e for e in collapse(channel_audit_repo.for_user(user))}
    assert entries["w1"].outcome == "pending" and entries["w1"].finished_at is None
    assert entries["w2"].outcome == "ok" and len(entries["w2"].events) == 2


def test_by_correlation_returns_one_turn_across_tools_oldest_first(channel_audit_repo, user_prefix):
    user = f"{user_prefix}u6"
    corr = f"corr-{user_prefix}"
    channel_audit_repo.append(_event(user, "t2", correlation_id=corr, at=T0 + timedelta(seconds=5), tool_name="client_trend"))
    channel_audit_repo.append(_event(user, "t1", correlation_id=corr, at=T0, tool_name="book_rank"))
    channel_audit_repo.append(_event(user, "t3", correlation_id="other", at=T0))
    assert [e.audit_id for e in channel_audit_repo.by_correlation(corr)] == ["t1", "t2"]


def test_the_audit_port_has_no_update_or_delete(channel_audit_repo):
    public = {n for n, _ in inspect.getmembers(channel_audit_repo, inspect.ismethod) if not n.startswith("_")}
    assert not {n for n in public if n.startswith(("update", "delete", "remove", "set_", "purge"))}
    assert {"append", "for_user", "by_correlation"} <= public


def test_the_domain_refuses_an_incoherent_event():
    with pytest.raises(ValueError, match="pending"):
        _event("u", "bad", phase="end", seq=2, outcome="pending")
    with pytest.raises(ValueError, match="begin"):
        _event("u", "bad", phase="begin", outcome="ok")
    with pytest.raises(ValueError, match="channel"):
        _event("u", "bad", channel="fax")
    with pytest.raises(ValueError, match="tax_year"):
        _event("u", "bad", tax_year=23)


# ---------------------------------------------------------------- agent actions


def test_an_agent_action_round_trips(agent_action_repo, user_prefix):
    name = f"{user_prefix}NarratorAgent"
    agent_action_repo.append(AgentActionAudit(
        action_id=f"{user_prefix}act1", agent_name=name, occurred_at=T0, agent_version="3",
        model_deployment="gpt-x", prompt_hash="c" * 64, tool_calls='["book_rank"]',
        input_summary="intent=book", output_summary="status=ok", user_upn="u@example.com",
        is_deterministic_path=False, client_id=None, run_id="run-1",
    ))
    [got] = agent_action_repo.recent(agent_name=name)
    assert (got.agent_version, got.model_deployment, got.prompt_hash) == ("3", "gpt-x", "c" * 64)
    assert got.tool_calls == '["book_rank"]' and got.is_deterministic_path is False
    assert got.user_upn == "u@example.com" and got.run_id == "run-1"


# ---------------------------------------------------------------------- writers


def test_a_writer_is_live_until_removed_and_removal_is_a_stamp(writer_repo, user_prefix):
    oid = f"{user_prefix}w1"
    assert writer_repo.is_writer(oid) is False
    writer_repo.grant(WriterGrant(user_oid=oid, added_by="operator@example.com", display_name="W One", added_at=T0))
    assert writer_repo.is_writer(oid) is True
    assert [g.display_name for g in writer_repo.live() if g.user_oid == oid] == ["W One"]

    assert writer_repo.revoke(oid, at=T0 + timedelta(hours=1)) is True
    assert writer_repo.is_writer(oid) is False
    assert writer_repo.revoke(oid) is False, "nothing live to remove"
    assert not [g for g in writer_repo.live() if g.user_oid == oid]


def test_re_adding_a_removed_writer_inserts_a_new_live_row(writer_repo, user_prefix):
    oid = f"{user_prefix}w2"
    writer_repo.grant(WriterGrant(user_oid=oid, added_by="a", added_at=T0))
    writer_repo.revoke(oid, at=T0 + timedelta(minutes=1))
    writer_repo.grant(WriterGrant(user_oid=oid, added_by="b", added_at=T0 + timedelta(minutes=2)))
    live = [g for g in writer_repo.live() if g.user_oid == oid]
    assert [g.added_by for g in live] == ["b"] and writer_repo.is_writer(oid)


def test_granting_twice_leaves_exactly_one_live_row(writer_repo, user_prefix):
    oid = f"{user_prefix}w3"
    writer_repo.grant(WriterGrant(user_oid=oid, added_by="a", added_at=T0))
    writer_repo.grant(WriterGrant(user_oid=oid, added_by="b", added_at=T0 + timedelta(minutes=1)))
    assert len([g for g in writer_repo.live() if g.user_oid == oid]) == 1


# ---------------------------------------------------------------- confirmations


def _confirmation(user: str, cid: str, **kw) -> Confirmation:
    values = dict(
        confirmation_id=cid, token_sha256="d" * 63 + cid[-1], user_oid=user, tool_name="claim_transition_commit",
        args_sha256="e" * 64, expires_at=T0 + timedelta(minutes=10), created_at=T0,
    )
    values.update(kw)
    return Confirmation(**values)


def test_a_confirmation_is_found_by_its_token_hash_and_stores_only_the_hash(confirmation_repo, user_prefix):
    cid = f"{user_prefix}c1"
    item = _confirmation(f"{user_prefix}u", cid)
    confirmation_repo.create(item)
    got = confirmation_repo.find_by_token_hash(item.token_sha256)
    assert got is not None and got.confirmation_id == cid and got.consumed_at is None
    assert got.args_sha256 == "e" * 64 and abs(got.expires_at - item.expires_at) < timedelta(seconds=1)
    assert confirmation_repo.find_by_token_hash("0" * 64) is None
    assert "token" not in {f for f in Confirmation.__dataclass_fields__ if f != "token_sha256" and "token" in f}


def test_a_confirmation_can_be_consumed_exactly_once(confirmation_repo, user_prefix):
    cid = f"{user_prefix}c2"
    confirmation_repo.create(_confirmation(f"{user_prefix}u", cid))
    assert confirmation_repo.consume(cid, T0 + timedelta(minutes=1), "idem-1") is True
    assert confirmation_repo.consume(cid, T0 + timedelta(minutes=2), "idem-2") is False
    got = confirmation_repo.find_by_token_hash("d" * 63 + cid[-1])
    assert got.consumed_at is not None and got.idempotency_key == "idem-1"


def test_a_recorded_result_replays_by_idempotency_key(confirmation_repo, user_prefix):
    user, cid = f"{user_prefix}u", f"{user_prefix}c3"
    confirmation_repo.create(_confirmation(user, cid))
    assert confirmation_repo.find_by_idempotency_key(user, "k-1") is None
    confirmation_repo.consume(cid, T0, "k-1")
    assert confirmation_repo.find_by_idempotency_key(user, "k-1") is None, "no result recorded yet"
    confirmation_repo.record_result(cid, "ok", '{"claim_id": "x"}')
    got = confirmation_repo.find_by_idempotency_key(user, "k-1")
    assert got is not None and got.result_json == '{"claim_id": "x"}' and got.outcome == "ok"
    assert confirmation_repo.find_by_idempotency_key(f"{user_prefix}someone-else", "k-1") is None
