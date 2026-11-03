"""The channel gateway as a caller: app-only tokens, the acting-user header,
writer entitlement and the Authorization stage. [CH-04]

An agent principal is a service, so the properties worth proving are the ones
that stop it acquiring a person's rights: it cannot present both token shapes,
it cannot name a user from another tenant, it cannot write without a named user
who is entitled, and a write is attributed to that user, never to the bot.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from application import wiring
from application.acting_user import ActingUserError, encode, parse_acting_user
from application.authorization import WriterPolicy
from application.identity import ANONYMOUS, ActingUser, NotAuthorized, Policy, Principal
from application.mediator import Command, Mediator
from infrastructure.auth.entra import (
    AuthorizationFailed,
    EntraTokenValidator,
    issuer_for,
)
from infrastructure.auth.writers import EitherEntitlement, EntraGroupEntitlement
from tests.test_auth import API_CLIENT_ID, AUDIENCE, TENANT, FakeJwks, _KEY, mint

AGENT_OID = "aaaaaaaa-0000-4000-8000-000000000001"
USER_OID = "bbbbbbbb-0000-4000-8000-000000000002"
OTHER_OID = "cccccccc-0000-4000-8000-000000000003"
GROUP_ID = "dddddddd-0000-4000-8000-000000000004"


def mint_app(*, roles=("TCC.Agent",), **extra) -> str:
    """An app-only token: no `scp`, no user name, `sub` equal to `oid`."""
    now = int(time.time())
    claims = {
        "aud": API_CLIENT_ID, "iss": issuer_for(TENANT), "iat": now, "nbf": now, "exp": now + 3600,
        "oid": AGENT_OID, "sub": AGENT_OID, "tid": TENANT, "roles": list(roles), "idtyp": "app",
        **extra,
    }
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": "test-key"})


def acting_header(**overrides) -> str:
    payload = {"oid": USER_OID, "tid": TENANT, "name": "Pat Writer", "upn": "pat@example.com",
               "channel": "teams", "conversation_id": "conv-1", "correlation_id": "corr-1"}
    payload.update(overrides)
    return encode({k: v for k, v in payload.items() if v is not None})


def _validator() -> EntraTokenValidator:
    return EntraTokenValidator(tenant_id=TENANT, api_audience=AUDIENCE, jwks_client=FakeJwks())


# ------------------------------------------------------------- the token


def test_an_app_only_token_is_an_agent_principal():
    principal = _validator().validate(mint_app())
    assert principal.is_agent and principal.authenticated and principal.oid == AGENT_OID
    assert principal.scopes == () and "TCC.Agent" in principal.roles


def test_an_agent_is_identified_without_idtyp_by_its_subject_equal_to_its_oid():
    token = mint_app(idtyp=None)
    assert _validator().validate(token).is_agent


def test_a_delegated_token_is_still_a_user():
    principal = _validator().validate(mint())
    assert not principal.is_agent and principal.principal_type == "user" and principal.acting_for is None


@pytest.mark.parametrize(
    "token, why",
    [
        (mint_app(roles=()), "TCC.Agent"),
        (mint_app(roles=("TCC.User",)), "TCC.User"),
        (mint_app(roles=("TCC.Agent", "TCC.User")), "TCC.User"),
        (mint_app(scp="user_impersonation"), "mixes"),
        (mint(roles=("TCC.User", "TCC.Agent")), "TCC.Agent"),
        (mint(idtyp="app"), "mixes"),
    ],
    ids=["no-role", "user-role-only", "both-roles", "app-with-scope", "user-with-agent-role", "user-flagged-app"],
)
def test_a_token_that_mixes_or_misses_the_shapes_is_refused(token, why):
    with pytest.raises(AuthorizationFailed, match=why):
        _validator().validate(token)


# ------------------------------------------------------------ the header


def test_a_valid_header_names_the_person():
    user = parse_acting_user(acting_header(), TENANT)
    assert user.oid == USER_OID and user.actor == "pat@example.com"
    assert user.display_name == "Pat Writer" and user.assurance == "channel-asserted"
    assert (user.channel, user.conversation_id, user.correlation_id) == ("teams", "conv-1", "corr-1")


def test_a_user_with_no_upn_is_attributed_by_object_id():
    assert parse_acting_user(acting_header(upn=None), TENANT).actor == USER_OID


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "!!!not-base64!!!",
        encode({"oid": USER_OID}),                                   # no tid
        encode({"oid": USER_OID, "tid": "00000000-0000-0000-0000-0000000000bb"}),  # another tenant
        encode({"oid": "not-a-guid", "tid": TENANT}),
        encode({"oid": USER_OID, "tid": TENANT, "name": "x" * 300}),
        encode({"oid": USER_OID, "tid": TENANT, "assurance": "trust-me"}),
        encode({"oid": USER_OID, "tid": TENANT, "channel": "carrier-pigeon"}),
        encode({"oid": USER_OID, "tid": TENANT, "name": {"a": 1}}),
        "W10",                                                       # a JSON list, not an object
        "A" * 4000,
    ],
    ids=["none", "empty", "blank", "garbage", "no-tid", "other-tenant", "bad-oid", "long-name",
         "assurance", "channel", "name-type", "list", "oversize"],
)
def test_a_malformed_or_foreign_header_is_refused(value):
    with pytest.raises(ActingUserError):
        parse_acting_user(value, TENANT)


# ------------------------------------------------------------- the edge


@pytest.fixture
def entra(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.setenv("AUTH_TENANT_ID", TENANT)
    monkeypatch.setenv("API_AUDIENCE", AUDIENCE)
    wiring.set_token_validator(_validator())
    yield
    wiring.set_token_validator(None)
    wiring.set_client_authorizer(None)


@pytest.fixture
def api():
    import main

    return TestClient(main.app)


def _agent(header: str | None = None, token: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token or mint_app()}"}
    if header is not None:
        headers["X-TCC-Acting-User"] = header
    return headers


def test_me_reports_the_agent_and_who_it_acts_for(entra, api):
    body = api.get("/api/me", headers=_agent(acting_header())).json()
    assert body["principal_type"] == "agent"
    assert body["acting_for"]["oid"] == USER_OID and body["acting_for"]["name"] == "Pat Writer"
    assert body["acting_for"]["assurance"] == "channel-asserted"


@pytest.mark.parametrize("header", [None, "garbage!", acting_header(oid="nope")], ids=["absent", "garbage", "bad-oid"])
def test_an_agent_request_without_a_valid_user_is_400(entra, api, header):
    assert api.get("/api/me", headers=_agent(header)).status_code == 400


def test_an_agent_naming_another_tenants_user_is_400(entra, api):
    other = acting_header(tid="00000000-0000-0000-0000-0000000000bb")
    assert api.get("/api/me", headers=_agent(other)).status_code == 400


def test_a_user_cannot_act_for_someone_by_header(entra, api):
    headers = {"Authorization": f"Bearer {mint()}", "X-TCC-Acting-User": acting_header(oid=OTHER_OID)}
    body = api.get("/api/me", headers=headers).json()
    assert body["principal_type"] == "user" and body["acting_for"] is None
    assert body["oid"] != OTHER_OID


def test_health_and_ready_need_neither_token_nor_header(entra, api):
    assert api.get("/api/health").status_code == 200
    assert api.get("/api/ready").status_code == 200


def test_the_agent_may_not_read_the_audit_trail(entra, api):
    denied = api.get("/api/audit/channel", params={"user_oid": USER_OID}, headers=_agent(acting_header()))
    assert denied.status_code == 403
    allowed = api.get("/api/audit/channel", params={"user_oid": USER_OID}, headers={"Authorization": f"Bearer {mint()}"})
    assert allowed.status_code == 200


# --------------------------------------------------- writes through the edge


@pytest.fixture
def writable(tmp_path, entra, monkeypatch):
    """A finding store, a writer allow-list, and a mediator built under this env."""
    from api import findings as findings_api
    from infrastructure.persistence.sqlite_channel_state import SqliteWriterRepository
    from infrastructure.persistence.sqlite_findings import SqliteFindingRepository

    monkeypatch.delenv("CHANNEL_ENFORCE_WRITER_FOR_USERS", raising=False)
    monkeypatch.setenv("CHANNEL_WRITER_SOURCE", "allowlist")
    original = findings_api._REPO
    findings = SqliteFindingRepository(tmp_path / "findings.db")
    writers = SqliteWriterRepository(tmp_path / "writers.db")
    findings_api.set_repository(findings)
    wiring.set_writer_repository(writers)
    wiring.set_writer_entitlement(None)
    wiring.reset_mediator()
    try:
        yield writers
    finally:
        findings.close()
        findings_api.set_repository(original)
        wiring.set_writer_repository(None)
        wiring.set_writer_entitlement(None)
        wiring.reset_mediator()


RESOLVE = {"client_id": 1001, "tax_year": 2023, "resolution": "accept"}


def _grant(writers, oid=USER_OID):
    from domain.channel import WriterGrant

    writers.grant(WriterGrant(user_oid=oid, added_by="test"))


def test_an_agent_write_for_a_non_writer_is_403_and_recorded_as_refused(writable, api):
    response = api.post("/api/findings/f-1/resolve", headers=_agent(acting_header()), json=RESOLVE)
    assert response.status_code == 403
    refused = [r for r in wiring.get_mediator().audit.records if r.outcome == "refused"]
    assert [r.request for r in refused] == ["ResolveFindingCommand"]


def test_an_agent_write_for_a_writer_lands_attributed_to_the_person(writable, api):
    _grant(writable)
    response = api.post("/api/findings/f-1/resolve", headers=_agent(acting_header()), json=RESOLVE)
    assert response.status_code == 200, response.text
    assert response.json()["decided_by"] == "pat@example.com"
    ok = [r for r in wiring.get_mediator().audit.records if r.outcome == "ok"]
    assert ok and ok[-1].actor == "pat@example.com" and ok[-1].attributed


def test_a_caller_supplied_name_cannot_override_the_acting_user(writable, api):
    _grant(writable)
    body = {**RESOLVE, "decided_by": "Somebody Else"}
    response = api.post("/api/findings/f-2/resolve", headers=_agent(acting_header()), json=body)
    assert response.json()["decided_by"] == "pat@example.com"


def test_an_agent_cannot_borrow_a_writers_rights_with_its_own_oid(writable, api):
    _grant(writable, AGENT_OID)  # the bot's own id on the list must not matter
    response = api.post("/api/findings/f-3/resolve", headers=_agent(acting_header()), json=RESOLVE)
    assert response.status_code == 403


def test_reopen_and_base_year_are_writer_gated_too(writable, api):
    assert api.post("/api/findings/f-1/reopen", headers=_agent(acting_header()), json=RESOLVE).status_code == 403
    from application.commands.resolve_finding import ReopenFindingCommand
    from application.commands.set_base_year import SetBaseYearCommand

    for command in (ReopenFindingCommand, SetBaseYearCommand):
        assert command.policy is Policy.WRITER


def test_a_signed_in_person_still_writes_without_being_listed(writable, api):
    token = {"Authorization": f"Bearer {mint()}"}
    assert api.post("/api/findings/f-4/resolve", headers=token, json=RESOLVE).status_code == 200


def test_enforcement_for_users_refuses_a_person_who_is_not_listed(writable, api, monkeypatch):
    monkeypatch.setenv("CHANNEL_ENFORCE_WRITER_FOR_USERS", "true")
    wiring.reset_mediator()
    token = {"Authorization": f"Bearer {mint()}"}
    assert api.post("/api/findings/f-5/resolve", headers=token, json=RESOLVE).status_code == 403


# ------------------------------------------------ the stage, without HTTP


@dataclass(frozen=True)
class _Write(Command):
    policy = Policy.WRITER


@dataclass(frozen=True)
class _Open(Command):
    pass


class _Roster:
    def __init__(self, *oids):
        self.oids = set(oids)

    def is_writer(self, oid):
        return oid in self.oids


def _agent_for(oid=USER_OID, upn="pat@example.com") -> Principal:
    return Principal(oid=AGENT_OID, authenticated=True, principal_type="agent",
                     acting_for=ActingUser(oid=oid, upn=upn))


def _mediator(policy: WriterPolicy | None) -> Mediator:
    mediator = Mediator(authorizer=policy)
    mediator.register(_Write, lambda c: "done")
    mediator.register(_Open, lambda c: "done")
    return mediator


def test_a_policy_with_no_authorizer_is_refused_not_waved_through():
    with pytest.raises(NotAuthorized, match="no authorizer"):
        _mediator(None).send(_Write(actor="x"), principal=ANONYMOUS)


def test_a_command_without_a_policy_needs_no_authorizer():
    assert _mediator(None).send(_Open(actor="x"), principal=ANONYMOUS) == "done"


def test_the_stage_is_not_a_no_op():
    mediator = _mediator(WriterPolicy(_Roster()))
    with pytest.raises(NotAuthorized):
        mediator.send(_Write(actor="pat@example.com"), principal=_agent_for())
    assert mediator.audit.records[-1].outcome == "refused"


def test_an_agent_with_no_acting_user_is_refused():
    bare = Principal(oid=AGENT_OID, authenticated=True, principal_type="agent")
    with pytest.raises(NotAuthorized, match="name the user"):
        _mediator(WriterPolicy(_Roster(USER_OID))).send(_Write(actor="x"), principal=bare)


def test_a_command_authored_by_someone_else_is_refused_for_an_agent():
    mediator = _mediator(WriterPolicy(_Roster(USER_OID)))
    with pytest.raises(NotAuthorized, match="author"):
        mediator.send(_Write(actor="somebody-else"), principal=_agent_for())
    assert mediator.send(_Write(actor="pat@example.com"), principal=_agent_for()) == "done"


def test_the_ambient_principal_is_used_when_a_router_forgets_to_pass_one():
    from application.identity import set_ambient_principal

    mediator = _mediator(WriterPolicy(_Roster()))
    set_ambient_principal(_agent_for())
    try:
        with pytest.raises(NotAuthorized):
            mediator.send(_Write(actor="pat@example.com"))
    finally:
        set_ambient_principal(None)


def test_anonymous_and_users_pass_unless_enforced():
    open_ = _mediator(WriterPolicy(_Roster()))
    assert open_.send(_Write(actor="a"), principal=ANONYMOUS) == "done"
    strict = _mediator(WriterPolicy(_Roster(USER_OID), enforce_for_users=True))
    with pytest.raises(NotAuthorized):
        strict.send(_Write(actor="a"), principal=ANONYMOUS)
    person = Principal(oid=USER_OID, upn="pat@example.com", authenticated=True)
    assert strict.send(_Write(actor="pat@example.com"), principal=person) == "done"


# ------------------------------------------------ the entitlement sources


def _graph(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _group(handler, clock=None) -> EntraGroupEntitlement:
    return EntraGroupEntitlement(
        GROUP_ID, token_provider=lambda: "t", client=_graph(handler), clock=clock or _Clock(),
    )


def test_group_membership_grants_and_non_membership_denies():
    member = _group(lambda r: httpx.Response(200, json={"value": [GROUP_ID.upper()]}))
    stranger = _group(lambda r: httpx.Response(200, json={"value": []}))
    assert member.is_writer(USER_OID) and not stranger.is_writer(USER_OID)


def test_the_graph_call_names_the_group_and_carries_the_token():
    seen = {}

    def handler(request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], request.content
        return httpx.Response(200, json={"value": []})

    _group(handler).is_writer(USER_OID)
    assert seen["url"].endswith(f"/users/{USER_OID}/checkMemberGroups") and seen["auth"] == "Bearer t"
    assert GROUP_ID.encode() in seen["body"]


@pytest.mark.parametrize(
    "reply",
    [
        lambda r: httpx.Response(500),
        lambda r: httpx.Response(403, json={"error": "Authorization_RequestDenied"}),
        lambda r: httpx.Response(200, json={"unexpected": True}),
        lambda r: httpx.Response(200, text="not json"),
        lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")),
    ],
    ids=["500", "403", "no-value", "not-json", "network"],
)
def test_every_graph_failure_fails_closed(reply):
    assert _group(reply).is_writer(USER_OID) is False


def test_an_answer_is_cached_for_a_minute_and_a_failure_is_not():
    calls, clock = [], _Clock()

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"value": [GROUP_ID]})

    group = _group(handler, clock)
    assert group.is_writer(USER_OID) and group.is_writer(USER_OID)
    assert len(calls) == 1
    clock.now = 61
    group.is_writer(USER_OID)
    assert len(calls) == 2

    failing = _group(lambda r: httpx.Response(500), clock)
    failing.is_writer(USER_OID)
    failing.is_writer(USER_OID)  # not cached: asks again


def test_a_group_entitlement_without_a_group_id_is_refused_at_construction():
    with pytest.raises(ValueError):
        EntraGroupEntitlement("", token_provider=lambda: "t")


def test_either_grants_on_any_source_and_survives_a_broken_one():
    class Broken:
        def is_writer(self, oid):
            raise RuntimeError("boom")

    assert EitherEntitlement((Broken(), _Roster(USER_OID))).is_writer(USER_OID)
    assert not EitherEntitlement((Broken(), _Roster())).is_writer(USER_OID)


@pytest.mark.parametrize("source, expected", [("allowlist", True), ("entra_group", False), ("either", True)])
def test_the_source_setting_selects_the_entitlement(monkeypatch, tmp_path, source, expected):
    from infrastructure.persistence.sqlite_channel_state import SqliteWriterRepository

    monkeypatch.setenv("CHANNEL_WRITER_SOURCE", source)
    monkeypatch.setenv("CHANNEL_WRITER_GROUP_ID", GROUP_ID)
    writers = SqliteWriterRepository(tmp_path / "w.db")
    _grant(writers)
    wiring.set_writer_repository(writers)
    wiring.set_writer_entitlement(None)
    try:
        entitlement = wiring.get_writer_entitlement()
        if source != "allowlist":
            group = entitlement if source == "entra_group" else entitlement.sources[1]
            group.token_provider = lambda: "t"
            group.client = _graph(lambda r: httpx.Response(200, json={"value": []}))
        assert entitlement.is_writer(USER_OID) is expected
    finally:
        wiring.set_writer_repository(None)
        wiring.set_writer_entitlement(None)


def test_an_unknown_writer_source_is_refused(monkeypatch):
    from application.deployment import writer_source

    monkeypatch.setenv("CHANNEL_WRITER_SOURCE", "everyone")
    with pytest.raises(ValueError):
        writer_source()


# ------------------------------------------------------- engagement actor


def test_an_engagement_records_who_set_it(tmp_path, writable, api):
    from api import claims as claims_api
    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository

    _grant(writable)
    repo = SqliteClaimRepository(tmp_path / "claims.db")
    original = wiring.get_claim_repository()
    claims_api.set_repository(repo)
    try:
        response = api.put(
            "/api/claims/engagement", headers=_agent(acting_header()),
            json={"client_id": 1001, "program_code": "GA_JTC", "scope": "in_scope"},
        )
    finally:
        claims_api.set_repository(original)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["set_by"] == "pat@example.com" and body["set_at"]
    assert repo.engagements(1001)[0].set_by == "pat@example.com"


@pytest.mark.parametrize(
    "path, body",
    [
        ("/api/ingestion/2023/exceptions/x1/resolve", {"resolution": "accept", "reviewer": "Spoofed"}),
        ("/api/onezero/employee/e1/review", {"status": "validated", "reviewer": "Spoofed"}),
    ],
)
def test_a_reviewer_field_cannot_override_an_authenticated_identity(entra, api, path, body):
    response = api.post(path, headers={"Authorization": f"Bearer {mint()}"}, json=body)
    assert response.status_code == 200, response.text
    text = response.text
    assert "analyst@example.com" in text and "Spoofed" not in text


# ------------------------------------------------ routes the agent may not use


def _inventory_as_concrete_paths() -> list[str]:
    import json
    import pathlib
    import re as _re

    raw = json.loads((pathlib.Path(__file__).parent / "route_inventory.json").read_text(encoding="utf-8"))
    routes = raw["routes"] if isinstance(raw, dict) else raw
    return [_re.sub(r"\{[^}]+\}", "7", r) for r in routes]


def test_every_forbidden_write_pattern_still_matches_a_real_route():
    from api.auth import AGENT_FORBIDDEN_WRITES

    concrete = _inventory_as_concrete_paths()
    for pattern in AGENT_FORBIDDEN_WRITES:
        assert any(pattern.match(route) for route in concrete), f"{pattern.pattern} matches no route"


def test_an_agent_is_refused_a_person_only_write_and_a_person_is_not(entra, api):
    body = {"resolution": "accept", "reviewer": "x"}
    path = "/api/ingestion/2023/exceptions/x1/resolve"
    assert api.post(path, headers=_agent(acting_header()), json=body).status_code == 403
    assert api.post(path, headers={"Authorization": f"Bearer {mint()}"}, json=body).status_code == 200


# ------------------------------------------------------- scripts/channel-writers


def _writers_cli():
    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "channel-writers.py"
    spec = importlib.util.spec_from_file_location("channel_writers", path)
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(module)
    return module


def test_the_writers_cli_adds_lists_and_removes(tmp_path, capsys):
    from infrastructure.persistence.sqlite_channel_state import SqliteWriterRepository

    cli, writers = _writers_cli(), SqliteWriterRepository(tmp_path / "w.db")
    assert cli.main(["add", USER_OID, "--name", "Pat Writer", "--by", "ops"], writers=writers) == 0
    assert writers.is_writer(USER_OID)
    assert cli.main(["add", USER_OID], writers=writers) == 0  # idempotent
    assert "already a writer" in capsys.readouterr().out
    assert cli.main(["list"], writers=writers) == 0
    assert "Pat Writer" in capsys.readouterr().out
    assert cli.main(["remove", USER_OID], writers=writers) == 0
    assert not writers.is_writer(USER_OID)
    assert cli.main(["remove", USER_OID], writers=writers) == 2  # nobody to remove


def test_the_writers_cli_refuses_a_non_guid(tmp_path):
    from infrastructure.persistence.sqlite_channel_state import SqliteWriterRepository

    assert _writers_cli().main(["add", "pat"], writers=SqliteWriterRepository(tmp_path / "w.db")) == 2


# ------------------------------------------- no command escapes the decision

#: Commands that declare no policy, and why. Adding one here is the decision
#: that it is open to any authenticated caller; it must not happen by omission.
_OPEN_COMMANDS = {
    "AssessClientCommand": "forbidden to the agent at the edge (AGENT_FORBIDDEN_WRITES); engine-computed",
    "RunClientCalculationCommand": "forbidden to the agent at the edge; a run, not a decision",
}


def test_every_registered_command_declares_a_policy_or_is_named_open():
    mediator = wiring.build_mediator()
    commands = {t for t in mediator._handlers if issubclass(t, Command)}
    undecided = {t.__name__ for t in commands if t.policy is None} - set(_OPEN_COMMANDS)
    assert not undecided, f"declare policy = Policy.WRITER or name them open with a reason: {sorted(undecided)}"
    assert set(_OPEN_COMMANDS) <= {t.__name__ for t in commands}, "a named-open command no longer exists"
