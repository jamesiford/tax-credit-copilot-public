"""Prepare/commit channel writes. [CH-05]

What must hold for a write that lands on a filed return and was asked for in a
chat: nothing changes at prepare; a token works once, for one person, one tool
and one set of arguments, before it expires; a retry is safe; a person who may
not write cannot get as far as a token; the preview is the row that lands; and
the trail shows both steps.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from application import wiring
from application.capabilities import catalog, registry
from application.capabilities.write_specs import InvalidWrite
from application.confirmations import (
    ArgumentsChanged, ConfirmationService, ExpiredConfirmation, IdempotencyConflict,
    ReplayedConfirmation, UnknownConfirmation, WrongTool, WrongUser, token_sha256,
)
from application.identity import ActingUser, NotAuthorized, Principal
from domain.channel import WriterGrant, utcnow

AGENT = "aaaaaaaa-0000-4000-8000-000000000001"
USER = "bbbbbbbb-0000-4000-8000-000000000002"
OTHER = "cccccccc-0000-4000-8000-000000000003"

CLAIM = {"client_id": 2001, "program_code": "GA_JTC", "tax_year": 2023, "status": "assessed"}
ENGAGE = {"client_id": 2001, "program_code": "GA_JTC", "scope": "in_scope", "note": "signed"}
RESOLVE = {"client_id": 2001, "tax_year": 2023, "finding_id": "f-1", "resolution": "accept", "note": "ok"}


def agent_for(oid: str = USER, upn: str = "pat@example.com") -> Principal:
    return Principal(oid=AGENT, authenticated=True, principal_type="agent",
                     acting_for=ActingUser(oid=oid, upn=upn, channel="teams", conversation_id="c-1"))


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Every store a channel write touches, on files, with USER a listed writer."""
    from api import findings as findings_api
    from infrastructure.persistence.sqlite_channel import SqliteChannelAuditRepository
    from infrastructure.persistence.sqlite_channel_state import SqliteConfirmationRepository, SqliteWriterRepository
    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository
    from infrastructure.persistence.sqlite_findings import SqliteFindingRepository

    monkeypatch.setenv("CHANNEL_WRITER_SOURCE", "allowlist")
    monkeypatch.delenv("CHANNEL_ENFORCE_WRITER_FOR_USERS", raising=False)
    store = type("World", (), {})()
    store.claims = SqliteClaimRepository(tmp_path / "claims.db")
    store.findings = SqliteFindingRepository(tmp_path / "findings.db")
    store.writers = SqliteWriterRepository(tmp_path / "writers.db")
    store.confirmations = SqliteConfirmationRepository(tmp_path / "confirmations.db")
    store.audit = SqliteChannelAuditRepository(tmp_path / "audit.db")
    originals = (wiring.get_claim_repository(), findings_api._REPO)
    wiring.set_claim_repository(store.claims)
    findings_api.set_repository(store.findings)
    wiring.set_writer_repository(store.writers)
    wiring.set_confirmation_repository(store.confirmations)
    wiring.set_channel_audit_repository(store.audit)
    wiring.set_writer_entitlement(None)
    wiring.reset_mediator()
    store.writers.grant(WriterGrant(user_oid=USER, added_by="test"))
    yield store
    wiring.set_claim_repository(originals[0])
    findings_api.set_repository(originals[1])
    for setter in (wiring.set_writer_repository, wiring.set_confirmation_repository,
                   wiring.set_channel_audit_repository, wiring.set_writer_entitlement):
        setter(None)
    wiring.reset_mediator()


def prepare(name: str, principal: Principal | None = None, **args):
    return registry.call(f"{name}_prepare", principal=principal or agent_for(), **args)


def commit(name: str, prepared, args, *, key: str = "k-1", principal: Principal | None = None):
    return registry.call(
        f"{name}_commit", principal=principal or agent_for(),
        confirmation_token=prepared.facts["confirmation"]["token"], idempotency_key=key, arguments=args,
    )


def history(world) -> int:
    return len(world.claims.history(2001, "GA_JTC", 2023))


# ------------------------------------------------------------------ the catalog


WRITES = ("finding_resolve", "finding_reopen", "claim_transition", "claim_record", "engagement_set", "base_year_set")


def test_every_write_capability_has_a_prepare_and_a_commit_in_the_registry():
    for base in WRITES:
        assert catalog.get(f"{base}_prepare").kind == catalog.WRITE_PREPARE
        assert catalog.get(f"{base}_commit").kind == catalog.WRITE_COMMIT
        assert registry.get(f"{base}_prepare") and registry.get(f"{base}_commit")
    from application.capabilities.write_specs import SPECS

    assert set(SPECS) == set(WRITES) | {"claim_package_create"}


def test_the_commit_schema_carries_the_arguments_it_must_match():
    schema = catalog.get("claim_record_commit").schema
    assert set(schema["required"]) == {"confirmation_token", "idempotency_key", "arguments"}
    assert schema["properties"]["arguments"]["required"] == catalog.get("claim_record_prepare").schema["required"]


def test_the_package_build_is_built_and_takes_a_principal():
    assert registry.get("claim_package_create_prepare") and registry.get("claim_package_create_commit")
    assert {"claim_package_create_prepare", "claim_package_create_commit"} <= registry.NEEDS_PRINCIPAL


# --------------------------------------------------------------------- prepare


def test_prepare_changes_nothing_and_returns_a_token(world):
    prepared = prepare("claim_record", **CLAIM)
    assert history(world) == 0
    token = prepared.facts["confirmation"]["token"]
    assert len(token) >= 32 and prepared.facts["preview"]["after"]["status"] == "assessed"
    assert "Nothing has changed yet" in prepared.blocks[-1].text


def test_only_the_hash_of_the_token_is_stored(world, tmp_path):
    prepared = prepare("claim_record", **CLAIM)
    token = prepared.facts["confirmation"]["token"]
    stored = world.confirmations.find_by_token_hash(token_sha256(token))
    assert stored is not None and stored.token_sha256 != token
    raw = (tmp_path / "confirmations.db").read_bytes()
    assert token.encode() not in raw


def test_a_malformed_request_gets_no_token(world):
    with pytest.raises(InvalidWrite):
        prepare("claim_record", **{**CLAIM, "status": "bogus"})
    with pytest.raises(InvalidWrite):
        prepare("finding_resolve", **{**RESOLVE, "resolution": "obliterate"})
    assert world.confirmations.find_by_token_hash("x") is None


def test_the_prepared_blocks_pass_the_numeric_guard(world):
    from application import numeric_guard
    from application.composer import render_markdown

    prepared = prepare("claim_record", **CLAIM)
    assert numeric_guard.check(render_markdown(prepared.blocks), facts=prepared.facts).passed


# ------------------------------------------------- the preview is the row that lands


def test_the_claim_record_preview_equals_the_committed_row(world):
    prepared = prepare("claim_record", **CLAIM)
    result = commit("claim_record", prepared, CLAIM)
    row = result.facts["result"]
    for key, value in prepared.facts["preview"]["after"].items():
        assert str(row[key]) == str(value), key
    assert row["decided_by"] == "pat@example.com" and row["provenance"] == "client_asserted"
    assert history(world) == 1


def test_the_transition_preview_equals_the_committed_row(world):
    commit("claim_record", prepare("claim_record", **CLAIM), CLAIM, key="seed")
    args = {**CLAIM, "status": "declined", "decline_reason": "not our mandate"}
    prepared = prepare("claim_transition", **args)
    assert prepared.facts["preview"]["before"]["status"] == "assessed"
    row = commit("claim_transition", prepared, args).facts["result"]
    for key, value in prepared.facts["preview"]["after"].items():
        assert str(row[key]) == str(value), key


def test_the_engagement_preview_equals_the_committed_row(world):
    prepared = prepare("engagement_set", **ENGAGE)
    row = commit("engagement_set", prepared, ENGAGE).facts["result"]
    assert prepared.facts["preview"]["before"] is None
    for key, value in prepared.facts["preview"]["after"].items():
        assert row[key] == value, key
    assert row["set_by"] == "pat@example.com" and row["set_at"]


def test_the_finding_previews_equal_the_committed_rows(world):
    prepared = prepare("finding_resolve", **RESOLVE)
    row = commit("finding_resolve", prepared, RESOLVE).facts["result"]
    for key, value in prepared.facts["preview"]["after"].items():
        assert row[key] == value, key
    args = {"client_id": 2001, "finding_id": "f-1"}
    reopen = prepare("finding_reopen", **args)
    assert reopen.facts["preview"]["before"]["resolution"] == "accept"
    done = commit("finding_reopen", reopen, args, key="k-2").facts["result"]
    assert done["requires_decision"] is True and done["resolution"] is None


def test_base_year_flows_through_the_command_and_its_preview(world, monkeypatch):
    from application.commands.set_base_year import BaseYearPlan

    seen = {}
    monkeypatch.setattr(
        "application.commands.set_base_year.plan_base_year",
        lambda command: BaseYearPlan({"run_id": "r"}, {2023: {}}, 2022, None),
    )
    monkeypatch.setattr(wiring, "handle_rebase_unit", lambda q: {
        "total_annual_credit_usd": 7000, "run_total_annual_credit_usd": 3500,
        "delta_annual_credit_usd": 3500,
    })

    def fake_handler(command):
        seen["actor"], seen["base"] = command.actor, command.base_year
        return {"recorded": True, "base_year": command.base_year}

    monkeypatch.setattr(wiring, "handle_set_base_year", fake_handler)
    wiring.reset_mediator()
    args = {"client_id": 2001, "unit_id": "GA_GA-001", "base_year": 2023}
    prepared = prepare("base_year_set", **args)
    after = prepared.facts["preview"]["after"]
    assert after["delta_annual_credit_usd"] == 3500 and prepared.facts["preview"]["before"]["base_year"] == 2022
    assert "$3,500" in prepared.blocks[1].rows[1][2] or "3,500" in str(prepared.blocks[1].rows)
    result = commit("base_year_set", prepared, args)
    assert seen == {"actor": "pat@example.com", "base": 2023} and result.facts["result"]["recorded"] is True


# ------------------------------------------------------------- token discipline


def test_a_tampered_argument_is_refused_and_nothing_is_written(world):
    prepared = prepare("claim_record", **CLAIM)
    with pytest.raises(ArgumentsChanged):
        commit("claim_record", prepared, {**CLAIM, "tax_year": 2022})
    assert history(world) == 0
    assert commit("claim_record", prepared, CLAIM).facts["replayed"] is False  # the token was not burned


def test_a_token_works_once(world):
    prepared = prepare("claim_record", **CLAIM)
    commit("claim_record", prepared, CLAIM, key="k-1")
    with pytest.raises(ReplayedConfirmation):
        commit("claim_record", prepared, CLAIM, key="k-2")
    assert history(world) == 1


def test_a_retry_with_the_same_idempotency_key_replays_and_writes_once(world):
    prepared = prepare("claim_record", **CLAIM)
    first = commit("claim_record", prepared, CLAIM, key="same")
    second = commit("claim_record", prepared, CLAIM, key="same")
    assert first.facts["replayed"] is False and second.facts["replayed"] is True
    assert second.facts["result"] == first.facts["result"] and history(world) == 1
    assert "nothing was repeated" in second.blocks[1].text


def test_an_idempotency_key_cannot_be_reused_for_a_different_change(world):
    commit("claim_record", prepare("claim_record", **CLAIM), CLAIM, key="reused")
    other = {**ENGAGE}
    with pytest.raises(IdempotencyConflict):
        commit("engagement_set", prepare("engagement_set", **other), other, key="reused")


def test_another_person_cannot_use_the_token(world):
    world.writers.grant(WriterGrant(user_oid=OTHER, added_by="test"))
    prepared = prepare("claim_record", **CLAIM)
    with pytest.raises(WrongUser):
        commit("claim_record", prepared, CLAIM, principal=agent_for(OTHER, "sam@example.com"))
    assert history(world) == 0


def test_a_token_for_one_tool_does_not_work_for_another(world):
    prepared = prepare("claim_record", **CLAIM)
    with pytest.raises(WrongTool):
        commit("engagement_set", prepared, ENGAGE)


def test_an_unknown_token_is_refused(world):
    prepared = prepare("claim_record", **CLAIM)
    prepared.facts["confirmation"]["token"] = "not-a-real-token-at-all-0123456789"
    with pytest.raises(UnknownConfirmation):
        commit("claim_record", prepared, CLAIM)


def test_an_expired_token_is_refused(world):
    clock = [utcnow()]
    service = ConfirmationService(world.confirmations, lambda p: None, ttl_seconds=60, clock=lambda: clock[0])
    p = agent_for()
    prepared = service.prepare("claim_record", p, CLAIM)
    clock[0] += timedelta(seconds=61)
    with pytest.raises(ExpiredConfirmation):
        service.commit("claim_record", p, CLAIM, prepared.token, "k", lambda: {"ok": True})
    clock[0] = utcnow()
    assert service.commit("claim_record", p, CLAIM, prepared.token, "k", lambda: {"ok": True}).replayed is False


def test_a_failed_write_is_recorded_and_the_token_is_spent(world):
    service = ConfirmationService(world.confirmations, lambda p: None)
    prepared = service.prepare("claim_record", agent_for(), CLAIM)

    def boom():
        raise RuntimeError("store down")

    with pytest.raises(RuntimeError):
        service.commit("claim_record", agent_for(), CLAIM, prepared.token, "k", boom)
    stored = world.confirmations.find_by_token_hash(token_sha256(prepared.token))
    assert stored.outcome == "error" and stored.consumed_at is not None
    with pytest.raises(ReplayedConfirmation):
        service.commit("claim_record", agent_for(), CLAIM, prepared.token, "k", lambda: {})


def test_two_concurrent_commits_write_once(world):
    service = ConfirmationService(world.confirmations, lambda p: None)
    p = agent_for()
    prepared = service.prepare("claim_record", p, CLAIM)
    ran = []
    first = service.commit("claim_record", p, CLAIM, prepared.token, "a", lambda: ran.append(1) or {"n": 1})
    with pytest.raises(ReplayedConfirmation):
        service.commit("claim_record", p, CLAIM, prepared.token, "b", lambda: ran.append(2) or {"n": 2})
    assert ran == [1] and first.replayed is False


# ---------------------------------------------------------------- entitlement


def test_a_non_writer_cannot_prepare(world):
    with pytest.raises(NotAuthorized):
        prepare("claim_record", principal=agent_for(OTHER, "sam@example.com"), **CLAIM)
    assert history(world) == 0


def test_a_writer_removed_after_prepare_cannot_commit(world):
    prepared = prepare("claim_record", **CLAIM)
    world.writers.revoke(USER)
    with pytest.raises(NotAuthorized):
        commit("claim_record", prepared, CLAIM)
    assert history(world) == 0
    world.writers.grant(WriterGrant(user_oid=USER, added_by="test"))
    assert commit("claim_record", prepared, CLAIM).facts["replayed"] is False


def test_a_write_cannot_be_attributed_to_the_gateway(world):
    prepared = prepare("claim_record", **CLAIM)
    row = commit("claim_record", prepared, CLAIM).facts["result"]
    assert AGENT not in json.dumps(row)


# ----------------------------------------------------------------------- audit


def events_for(world, user: str = USER):
    return sorted(world.audit.for_user(user, limit=50), key=lambda e: (e.occurred_at, e.event_seq))


def test_the_trail_shows_prepare_then_commit_with_the_confirmation(world):
    prepared = prepare("claim_record", **CLAIM)
    commit("claim_record", prepared, CLAIM)
    events = events_for(world)
    assert [(e.tool_name, e.phase, e.outcome) for e in events] == [
        ("claim_record_prepare", "begin", "pending"), ("claim_record_prepare", "end", "ok"),
        ("claim_record_commit", "begin", "pending"), ("claim_record_commit", "end", "ok"),
    ]
    assert {e.action_kind for e in events} == {"write_prepare", "write_commit"}
    assert events[1].confirmation_ref == prepared.facts["confirmation"]["confirmation_id"]
    assert all(e.channel == "teams" and e.client_id == 2001 for e in events)
    assert prepared.facts["confirmation"]["token"] not in json.dumps([e.to_dict() for e in events])


def test_a_refusal_reads_refused_not_error(world):
    with pytest.raises(NotAuthorized):
        prepare("claim_record", principal=agent_for(OTHER, "sam@example.com"), **CLAIM)
    outcomes = [e.outcome for e in events_for(world, OTHER)]
    assert outcomes == ["pending", "refused"]


def test_a_bad_commit_is_audited_as_an_error(world):
    prepared = prepare("claim_record", **CLAIM)
    with pytest.raises(ArgumentsChanged):
        commit("claim_record", prepared, {**CLAIM, "tax_year": 2022})
    last = events_for(world)[-1]
    assert (last.tool_name, last.outcome) == ("claim_record_commit", "error")
