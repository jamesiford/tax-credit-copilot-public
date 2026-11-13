"""The draft preview: priced by the engine's own functions, on synthetic data, writing nothing. [F05.4]

The equivalence test installs the SAME documents as a real program in a temporary rules folder and runs the real assessment over
the same rows: the preview must agree with it to the cent. The no-write test fails if the preview touches any service but the
draft store, changes the draft or its trail, or leaves a file behind.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from application.assessment import assess_client
from tests import draft_world as dw
from tests.two_program_world import RULES, tree_digest
from tools.preview_sample import sample_rows

BASE = "/api/v2/program-drafts"
#: Services the request edge asks for before any handler runs (who is calling), not the preview itself.
EDGE = ("client_authorizer", "token_validator", "mediator")


@pytest.fixture()
def api(monkeypatch):
    import main
    from bootstrap import program_draft_wiring
    from infrastructure.persistence.sqlite_program_drafts import SqliteProgramDraftRepository

    repo = SqliteProgramDraftRepository(":memory:")
    program_draft_wiring.set_program_draft_repository(repo)
    client = TestClient(main.app)
    client.repo = repo
    yield client
    program_draft_wiring.set_program_draft_repository(None)
    repo.close()


def _draft(api, docs=None):
    draft = api.post(BASE, json={"code": dw.CODE, "name": "Zedland Two", "state": dw.STATE, "years": [2024], "actor": "ann"}).json()
    docs = docs or dw.documents()
    return api.put(f"{BASE}/{draft['draft_id']}/documents", json={
        "expected_version": draft["version"], "pack": docs["pack"], "years": docs["years"]}).json()


def test_the_preview_is_labelled_and_names_its_data(api):
    draft = _draft(api)
    out = api.post(f"{BASE}/{draft['draft_id']}/preview", json={}).json()
    assert out["label"] == "Preview, not verified, not for filing" and out["unverified"] is True and out["unverified_flags"] > 0
    assert out["dataset"]["kind"] == "synthetic_sample" and "synthetic" in out["dataset"]["description"].lower()
    assert [y["tax_year"] for y in out["years"]] == [2024, 2025] and out["persisted"] is False and out["wrote_nothing"] is True
    assert out["years"][0]["is_base_year"] is True and out["years"][0]["qualifying_jobs"] == 0


def test_the_preview_agrees_with_the_real_assessment_of_the_same_documents(api, tmp_path, monkeypatch):
    draft = _draft(api)
    previewed = {y["tax_year"]: y for y in api.post(f"{BASE}/{draft['draft_id']}/preview", json={}).json()["years"]}
    rules = tmp_path / "rules"
    shutil.copytree(RULES, rules)
    docs = dw.documents()
    (rules / "zy_draft_jtc.json").write_text(json.dumps(docs["pack"]), encoding="utf-8")
    for year, doc in docs["years"].items():
        (rules / "zy_draft_jtc").mkdir(exist_ok=True)
        (rules / "zy_draft_jtc" / f"{year}.json").write_text(json.dumps(doc), encoding="utf-8")
    manifest = rules / "registry" / "programs.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["programs"].append({"code": dw.CODE, "name": "x", "jurisdiction": {"level": "state", "code": dw.STATE}, "state": dw.STATE,
                             "pack_file": "zy_draft_jtc.json", "lifecycle": "described",
                             "engine_profile": {"credit_model": "per_net_new_job", "headcount_model": "one_zero"}})
    manifest.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("RULES_DIR", str(rules))
    real = assess_client(7777, sample_rows(dw.STATE), program_code=dw.CODE, tax_years=[2025])["assessed"]
    assert len(real) == 1
    assert float(real[0]["identified_usd"]) == previewed[2025]["annual_credit_usd"]
    assert real[0]["average_headcount"] == previewed[2025]["average_headcount"]
    assert real[0]["base_average_headcount"] == previewed[2025]["prior_average_headcount"]
    assert previewed[2025]["qualifying_jobs"] > 0, "the sample must exercise the net-new path or this proves little"


def test_a_preview_writes_nothing_and_touches_no_other_service(api, monkeypatch):
    import application.services as services

    draft = _draft(api)
    before = (api.repo.get(draft["draft_id"]), api.repo.events(draft["draft_id"]), tree_digest(RULES))
    real_resolve = services.resolve

    def only_drafts(name):
        assert name in ("program_draft_repository", *EDGE), f"the preview reached for {name!r}"
        return real_resolve(name)

    monkeypatch.setattr(services, "resolve", only_drafts)
    assert api.post(f"{BASE}/{draft['draft_id']}/preview", json={}).status_code == 200
    assert (api.repo.get(draft["draft_id"]), api.repo.events(draft["draft_id"]), tree_digest(RULES)) == before


def test_a_draft_that_does_not_validate_or_has_no_year_is_refused(api):
    skeleton = api.post(BASE, json={"code": dw.CODE, "name": "x", "state": dw.STATE, "years": [2024]}).json()
    refused = api.post(f"{BASE}/{skeleton['draft_id']}/preview", json={})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "preview_refused"
    assert "validate and fix" in refused.json()["detail"]["reason"]


def test_a_year_the_sample_does_not_cover_is_declined_by_name(api):
    docs = dw.documents((2024, 2019))
    draft = _draft(api, docs)
    out = api.post(f"{BASE}/{draft['draft_id']}/preview", json={}).json()
    assert [d["tax_year"] for d in out["declined"]] == [2019] and out["declined"][0]["reason"] == "no_payroll"
    assert [y["tax_year"] for y in out["years"]] == [2024]


def test_a_customer_source_is_refused_unless_a_setting_allows_it(api, monkeypatch):
    monkeypatch.setenv("DATA_CLASSIFICATION", "customer")  # the suite pins synthetic; a customer environment is what is refused
    draft = _draft(api)
    body = {"dataset": "client", "client_id": 7777}
    refused = api.post(f"{BASE}/{draft['draft_id']}/preview", json=body)
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "customer_data_refused"
    monkeypatch.setenv("PROGRAM_PREVIEW_ALLOW_CUSTOMER_DATA", "true")
    monkeypatch.setattr("application.source_ports.load_pay_periods", lambda account_id=None: sample_rows(dw.STATE))
    monkeypatch.setattr("application.client_book.clients_checked", lambda: [{"account_id": 7777}])
    allowed = api.post(f"{BASE}/{draft['draft_id']}/preview", json=body)
    assert allowed.status_code == 200 and allowed.json()["dataset"]["kind"] == "client" and allowed.json()["persisted"] is False


def test_a_client_preview_needs_a_known_client_the_caller_may_act_for(api, monkeypatch):
    """Allowing customer data is not permission to read any client: the client authorizer still decides, and an unknown id is no tenant."""
    draft = _draft(api)
    monkeypatch.setenv("PROGRAM_PREVIEW_ALLOW_CUSTOMER_DATA", "true")
    monkeypatch.setattr("application.client_book.clients_checked", lambda: [{"account_id": 7777}, {"account_id": 8888}])
    reads = []
    monkeypatch.setattr("application.source_ports.load_pay_periods", lambda account_id=None: reads.append(account_id) or sample_rows(dw.STATE))

    class Denies8888:
        def is_authorized(self, principal, client_id):
            return client_id != 8888

    monkeypatch.setattr("application.services.get_client_authorizer", lambda: Denies8888())
    url = f"{BASE}/{draft['draft_id']}/preview"
    assert api.post(url, json={"dataset": "client", "client_id": 9999}).status_code == 422
    assert api.post(url, json={"dataset": "client", "client_id": 8888}).status_code == 403
    assert reads == [], "no payroll was read for a client that is unknown or not permitted"
    assert api.post(url, json={"dataset": "client", "client_id": 7777}).status_code == 200


def test_the_preview_code_never_writes_to_a_folder():
    source = (Path(__file__).resolve().parent.parent / "application" / "program_drafts" / "preview.py").read_text(encoding="utf-8")
    for needle in ("write_text", "open(", "mkdir", "record(", "save(", "create("):
        assert needle not in source, f"preview.py must not call {needle}"
