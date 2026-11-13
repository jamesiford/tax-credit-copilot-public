"""Program drafts over HTTP: the lifecycle, the validation and review rules, concurrency and the audit trail. [F05.3]

Offline: a private in-memory draft store. Every pack is the fictional `ZZ_DRAFT_JTC` (invented, flagged, not law).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests import draft_world as dw
from tests.test_agent_principal import _agent, acting_header, entra  # noqa: F401 - fixture
from tests.test_auth import mint

BASE = "/api/v2/program-drafts"


@pytest.fixture()
def api(monkeypatch):
    import main
    from bootstrap import program_draft_wiring
    from infrastructure.persistence.sqlite_program_drafts import SqliteProgramDraftRepository

    repo = SqliteProgramDraftRepository(":memory:")
    program_draft_wiring.set_program_draft_repository(repo)
    monkeypatch.setenv("PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER", "true")
    yield TestClient(main.app)
    program_draft_wiring.set_program_draft_repository(None)
    repo.close()


def _create(api, **kw):
    body = {"code": dw.CODE, "name": "Zedland Two Jobs Credit", "state": dw.STATE, "years": [2024, 2025], "actor": "ann", **kw}
    return api.post(BASE, json=body)


def _fill(api, draft, actor="ann", docs=None):
    docs = docs or dw.documents()
    return api.put(f"{BASE}/{draft['draft_id']}/documents", json={
        "expected_version": draft["version"], "pack": docs["pack"], "years": docs["years"], "actor": actor})


def _ready(api):
    draft = _create(api).json()
    filled = _fill(api, draft).json()
    assert api.post(f"{BASE}/{draft['draft_id']}/validate", json={"actor": "ann"}).json()["validation"]["valid"] is True
    return api.post(f"{BASE}/{draft['draft_id']}/request-review", json={"actor": "ann"}).json() | {"filled": filled}


def test_a_new_draft_is_the_scaffold_and_fails_validation_until_filled_in(api):
    created = _create(api)
    assert created.status_code == 201
    draft = created.json()
    assert draft["status"] == "draft" and draft["has_runtime_authority"] is False and draft["verification"] == "not_verified"
    assert sorted(draft["documents"]["years"]) == ["2024", "2025"] and draft["pack_file"] == "zy_draft_jtc.json"
    result = api.post(f"{BASE}/{draft['draft_id']}/validate", json={"actor": "ann"}).json()
    assert result["status"] == "needs_changes" and result["validation"]["valid"] is False
    findings = result["validation"]["findings"]
    assert {"schema", "todo_placeholder", "citation_missing"} <= {f["code"] for f in findings}
    assert all({"file", "path", "message"} <= set(f) for f in findings) and findings[0]["severity"] == "error"
    assert "request_review" not in result["allowed_actions"]


def test_a_filled_draft_validates_clean_but_stays_unverified(api):
    draft = _create(api).json()
    _fill(api, draft)
    after = api.post(f"{BASE}/{draft['draft_id']}/validate", json={"actor": "ann"}).json()
    assert after["status"] == "draft" and after["validation"]["errors"] == 0 and after["validation"]["valid"] is True
    assert after["validation"]["infos"] > 0 and after["validation"]["verification"] == "not_verified"
    assert "request_review" in after["allowed_actions"]


def test_documents_are_checked_against_the_draft_and_each_other(api):
    draft = _create(api).json()
    docs = dw.documents()
    docs["pack"]["credit"]["code"] = "ZZ_OTHER"
    docs["years"]["2025"]["tax_year"] = 2024
    docs["years"]["2024"]["_verified"] = True
    _fill(api, draft, docs=docs)
    codes = {f["code"] for f in api.post(f"{BASE}/{draft['draft_id']}/validate", json={}).json()["validation"]["findings"]}
    assert {"code_mismatch", "year_mismatch", "verified_claim"} <= codes


def test_a_program_already_registered_cannot_be_proposed(api):
    refused = _create(api, code="GA_JTC", state="GA")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "draft_conflict"
    assert _create(api, code="bad code").status_code == 422
    assert _create(api, state="").status_code == 422


def test_one_live_draft_per_code_until_it_is_withdrawn(api):
    first = _create(api).json()
    assert _create(api).status_code == 409
    assert api.post(f"{BASE}/{first['draft_id']}/withdraw", json={"actor": "ann", "reason": "duplicate"}).json()["status"] == "withdrawn"
    assert _create(api).status_code == 201


def test_a_stale_edit_is_a_conflict_and_changes_nothing(api):
    draft = _create(api).json()
    _fill(api, draft)
    stale = _fill(api, draft, docs=dw.documents((2025,)))
    assert stale.status_code == 409
    assert sorted(api.get(f"{BASE}/{draft['draft_id']}").json()["documents"]["years"]) == ["2024", "2025"]


def test_review_needs_a_current_clean_validation(api):
    draft = _create(api).json()
    assert api.post(f"{BASE}/{draft['draft_id']}/request-review", json={}).status_code == 422
    filled = _fill(api, draft).json()
    api.post(f"{BASE}/{draft['draft_id']}/validate", json={})
    changed = dw.documents()
    changed["pack"]["_note"] = "edited after validating"
    _fill(api, api.get(f"{BASE}/{draft['draft_id']}").json(), docs=changed)  # new content makes the validation stale
    stale = api.post(f"{BASE}/{draft['draft_id']}/request-review", json={})
    assert stale.status_code == 422 and "validate the draft first" in stale.json()["detail"]["reason"]
    assert filled["version"] == 2


def test_the_reviewer_must_differ_from_the_author_when_required(api):
    ready = _ready(api)
    assert ready["status"] == "ready_for_review"
    own = api.post(f"{BASE}/{ready['draft_id']}/review", json={"decision": "approve", "actor": "ann"})
    assert own.status_code == 422 and "must differ" in own.json()["detail"]["reason"]
    approved = api.post(f"{BASE}/{ready['draft_id']}/review", json={"decision": "approve", "actor": "bob", "comment": "values checked"})
    body = approved.json()
    assert body["status"] == "approved_for_export" and body["review"]["reviewer"] == "bob"
    assert body["review"]["approved_sha256"] == body["content_sha256"] and "export" in body["allowed_actions"]


def test_a_single_person_may_review_when_the_setting_is_off(api, monkeypatch):
    monkeypatch.setenv("PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER", "false")
    ready = _ready(api)
    assert api.post(f"{BASE}/{ready['draft_id']}/review", json={"decision": "approve", "actor": "ann"}).status_code == 200


def test_changes_requested_send_it_back_with_the_comment_and_it_can_be_edited_again(api):
    ready = _ready(api)
    assert api.post(f"{BASE}/{ready['draft_id']}/review", json={"decision": "request_changes", "actor": "bob"}).status_code == 422
    back = api.post(f"{BASE}/{ready['draft_id']}/review", json={"decision": "request_changes", "actor": "bob", "comment": "cite the rule"}).json()
    assert back["status"] == "needs_changes" and back["review"]["comment"] == "cite the rule" and back["review"]["approved_sha256"] is None
    assert _fill(api, back, actor="ann").status_code == 200


def test_a_draft_under_review_cannot_be_edited_or_validated(api):
    ready = _ready(api)
    assert _fill(api, ready, actor="ann").status_code == 409
    assert api.post(f"{BASE}/{ready['draft_id']}/validate", json={}).status_code == 409


def test_every_event_is_in_the_trail_with_its_actor_in_order(api):
    ready = _ready(api)
    api.post(f"{BASE}/{ready['draft_id']}/review", json={"decision": "approve", "actor": "bob"})
    events = api.get(f"{BASE}/{ready['draft_id']}").json()["events"]
    assert [(e["event_type"], e["actor"]) for e in events] == [
        ("created", "ann"), ("edited", "ann"), ("validated", "ann"), ("review_requested", "ann"), ("approved", "bob")]
    assert [e["seq"] for e in events] == [1, 2, 3, 4, 5] and events[-1]["to_status"] == "approved_for_export"


def test_a_document_that_does_not_fit_the_column_is_a_422_naming_it(api):
    draft = _create(api).json()
    docs = dw.documents()
    docs["pack"]["_note"] = "x" * 9000
    big = _fill(api, draft, docs=docs)
    assert big.status_code == 422 and "pack" in big.json()["detail"]["reason"]


def test_a_draft_is_bounded_in_depth_year_count_and_text_so_it_cannot_overrun_a_parser_or_a_column(api):
    draft = _create(api).json()
    deep: dict = {}
    node = deep
    for _ in range(40):
        node["n"] = {}
        node = node["n"]
    docs = dw.documents()
    docs["pack"]["_note"] = deep
    refused = _fill(api, draft, docs=docs)
    assert refused.status_code == 422 and "deeper" in refused.json()["detail"]["reason"]
    many = dw.documents()
    many["years"] = {str(2000 + i): many["years"]["2024"] for i in range(31)}
    refused = _fill(api, draft, docs=many)
    assert refused.status_code == 422, "more than 30 year packs is refused (pydantic or the lifecycle, either way by name)"
    assert api.post(BASE, json={"code": dw.CODE, "name": "n" * 201, "state": dw.STATE}).status_code == 422
    long_comment = api.post(f"{BASE}/{draft['draft_id']}/review", json={"decision": "request_changes", "comment": "c" * 2001})
    assert long_comment.status_code == 422
    assert api.get(f"{BASE}/{draft['draft_id']}").json()["version"] == draft["version"], "a refused edit changed nothing"


def test_listing_and_unknown_ids(api):
    _create(api)
    page = api.get(BASE).json()
    assert page["total"] == 1 and page["items"][0]["proposed_code"] == dw.CODE and "documents" not in page["items"][0]
    assert api.get(f"{BASE}/nope").status_code == 404
    assert api.get(BASE, params={"status": "withdrawn"}).json()["total"] == 0


def test_nothing_a_draft_does_reaches_the_registry_or_the_rules_folder(api):
    from tools.program_registry import load_registry

    before = [e.code for e in load_registry().entries]
    ready = _ready(api)
    api.post(f"{BASE}/{ready['draft_id']}/review", json={"decision": "approve", "actor": "bob"})
    assert [e.code for e in load_registry().entries] == before
    from application.client_book import programs

    assert dw.CODE not in {p["program_code"] for p in programs()}


def test_an_agent_cannot_write_drafts(entra, api):
    assert api.post(BASE, headers=_agent(acting_header()), json={"code": dw.CODE, "name": "x", "state": dw.STATE}).status_code == 403


def test_a_signed_in_person_reads_the_catalog_and_is_the_actor_on_every_event(entra, api):
    headers = {"Authorization": f"Bearer {mint()}"}
    assert api.get("/api/v2/programs", headers=headers).status_code == 200
    created = api.post(BASE, headers=headers, json={"code": dw.CODE, "name": "x", "state": dw.STATE})
    assert created.status_code == 201
    events = api.get(f"{BASE}/{created.json()['draft_id']}", headers=headers).json()["events"]
    me = api.get("/api/me", headers=headers).json()
    assert events[0]["actor"] not in ("anonymous", "system") and events[0]["actor"] in (me.get("upn"), me.get("oid"))


def test_an_agent_cannot_read_drafts_either(entra, api):
    assert api.get(BASE, headers=_agent(acting_header())).status_code == 403


def test_a_caller_who_is_not_a_writer_is_refused_and_nothing_is_stored():
    from application.authorization import WriterPolicy
    from application.commands.create_program_draft import CreateProgramDraftCommand
    from application.identity import NotAuthorized, Principal
    from application.mediator import Mediator
    from bootstrap.program_handlers import register_program_handlers
    from bootstrap import program_draft_wiring
    from infrastructure.persistence.sqlite_program_drafts import SqliteProgramDraftRepository

    class Nobody:
        def is_writer(self, oid):
            return False

    repo = SqliteProgramDraftRepository(":memory:")
    program_draft_wiring.set_program_draft_repository(repo)
    try:
        mediator = register_program_handlers(Mediator(authorizer=WriterPolicy(Nobody(), enforce_for_users=True)))
        with pytest.raises(NotAuthorized):
            mediator.send(CreateProgramDraftCommand(actor="eve", code=dw.CODE, name="x", state=dw.STATE),
                          Principal(oid="oid-1", upn="eve", authenticated=True))
        assert repo.list_drafts()[1] == 0
        assert mediator.audit.records[-1].outcome == "refused"
    finally:
        program_draft_wiring.set_program_draft_repository(None)
        repo.close()


def _as(upn, oid=None):
    extra = {"oid": oid} if oid else {}
    return {"Authorization": f"Bearer {mint(upn=upn, **extra)}"}


def _submitted_by(api, headers):
    docs = dw.documents()
    draft = api.post(BASE, headers=headers, json={"code": dw.CODE, "name": "Zedland Two Jobs Credit", "state": dw.STATE, "years": [2024, 2025]}).json()
    did = draft["draft_id"]
    api.put(f"{BASE}/{did}/documents", headers=headers, json={"expected_version": draft["version"], "pack": docs["pack"], "years": docs["years"]})
    assert api.post(f"{BASE}/{did}/validate", headers=headers, json={}).json()["validation"]["valid"] is True
    assert api.post(f"{BASE}/{did}/request-review", headers=headers, json={}).status_code == 200
    return did


def test_two_accounts_of_one_object_id_cannot_approve_their_own_draft(entra, api):
    """The second-reviewer rule compares object ids, so a second UPN for the same person does not satisfy it. [F07.3]"""
    did = _submitted_by(api, _as("first.account@example.com"))
    same_person = api.post(f"{BASE}/{did}/review", headers=_as("second.account@example.com"), json={"decision": "approve"})
    assert same_person.status_code == 422 and same_person.json()["detail"]["code"] == "review_refused"
    assert api.get(f"{BASE}/{did}", headers=_as("first.account@example.com")).json()["status"] == "ready_for_review"


def test_a_different_object_id_may_approve_and_both_identities_are_on_the_events(entra, api):
    did = _submitted_by(api, _as("author@example.com"))
    other = api.post(f"{BASE}/{did}/review", headers=_as("reviewer@example.com", oid="oid-of-the-second-person"), json={"decision": "approve"})
    assert other.status_code == 200 and other.json()["status"] == "approved_for_export"
    events = api.get(f"{BASE}/{did}", headers=_as("author@example.com")).json()["events"]
    assert all(e["detail"].get("actor_oid") and e["detail"].get("actor_tenant") for e in events)
    assert events[-1]["detail"]["actor_oid"] == "oid-of-the-second-person"
    assert events[0]["detail"]["actor_oid"] != events[-1]["detail"]["actor_oid"]


def test_events_written_without_a_token_carry_no_identity_and_keep_the_string_rule(api):
    ready = _ready(api)
    events = api.get(f"{BASE}/{ready['draft_id']}").json()["events"]
    assert all("actor_oid" not in e["detail"] for e in events)
    assert api.post(f"{BASE}/{ready['draft_id']}/review", json={"decision": "approve", "actor": "ann"}).status_code == 422
