"""The export bundle: deterministic, hashed, committable, and never written into the source tree. [F05.5]

The end-to-end test extracts a bundle into a copy of the rules folder, adds its registry entry (the human step) and proves the
program then validates and shows as calculable for exactly its authored years: nothing before that step makes it so.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import zipfile

import pytest
from fastapi.testclient import TestClient

from application.client_book import programs
from tests import draft_world as dw
from tests.two_program_world import RULES, tree_digest
from tools.pack_validation import validate_all

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


def _approved(api):
    draft = api.post(BASE, json={"code": dw.CODE, "name": "Zedland Two", "state": dw.STATE, "years": [2024], "actor": "ann"}).json()
    docs, did = dw.documents(), draft["draft_id"]
    api.put(f"{BASE}/{did}/documents", json={"expected_version": draft["version"], "pack": docs["pack"], "years": docs["years"], "actor": "ann"})
    api.post(f"{BASE}/{did}/validate", json={"actor": "ann"})
    api.post(f"{BASE}/{did}/request-review", json={"actor": "ann"})
    return api.post(f"{BASE}/{did}/review", json={"decision": "approve", "actor": "bob", "comment": "ok"}).json()


def _zip(response) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(response.content))


def test_only_an_approved_draft_can_be_exported(api):
    draft = api.post(BASE, json={"code": dw.CODE, "name": "x", "state": dw.STATE}).json()
    assert api.post(f"{BASE}/{draft['draft_id']}/export", json={}).status_code == 409
    assert api.get(f"{BASE}/{draft['draft_id']}/export/manifest").status_code == 409


def test_the_bundle_holds_the_files_at_their_final_paths_with_hashes_that_verify(api):
    did = _approved(api)["draft_id"]
    out = api.post(f"{BASE}/{did}/export", json={"actor": "ann"})
    assert out.status_code == 200 and out.headers["content-type"] == "application/zip" and out.headers["x-verification"] == "not_verified"
    assert hashlib.sha256(out.content).hexdigest() == out.headers["x-bundle-sha256"]
    archive = _zip(out)
    assert sorted(archive.namelist()) == sorted([
        "COMMIT-CHECKLIST.md", "manifest.json", "registry-patch.json", "review-record.json", "validation-report.json",
        "rules/zy_draft_jtc.json", "rules/zy_draft_jtc/2024.json", "rules/zy_draft_jtc/2025.json"])
    manifest = json.loads(archive.read("manifest.json"))
    for entry in manifest["files"]:
        assert hashlib.sha256(archive.read(entry["path"])).hexdigest() == entry["sha256"]
    assert manifest["verification"] == "not_verified" and manifest["has_runtime_authority"] is False
    assert json.loads(archive.read("registry-patch.json"))["programs"][0]["lifecycle"] == "described"
    record = json.loads(archive.read("review-record.json"))
    assert record["reviewer"] == "bob" and [h["event"] for h in record["history"]][-1] == "approved"
    checklist = archive.read("COMMIT-CHECKLIST.md").decode()
    assert "neither the author nor the reviewer" in checklist and "PROPOSAL" in checklist and "changelog" in checklist.lower()


def test_the_same_draft_always_exports_the_same_bytes(api):
    did = _approved(api)["draft_id"]
    first, second = api.post(f"{BASE}/{did}/export", json={}), api.post(f"{BASE}/{did}/export", json={})
    assert first.content == second.content
    manifest = api.get(f"{BASE}/{did}/export/manifest").json()
    assert manifest["bundle_sha256"] == first.headers["x-bundle-sha256"] and manifest["bundle_bytes"] == len(first.content)
    assert api.get(f"{BASE}/{did}").json()["export"]["bundle_sha256"] == manifest["bundle_sha256"]


def test_exporting_is_audited_and_changes_only_the_status(api):
    approved = _approved(api)
    api.post(f"{BASE}/{approved['draft_id']}/export", json={"actor": "carol"})
    got = api.get(f"{BASE}/{approved['draft_id']}").json()
    assert got["status"] == "exported" and got["content_sha256"] == approved["content_sha256"] and got["export"]["exported_at"]
    last = got["events"][-1]
    assert (last["event_type"], last["actor"], last["to_status"]) == ("exported", "carol", "exported") and last["detail"]["first_export"] is True
    assert api.post(f"{BASE}/{approved['draft_id']}/withdraw", json={}).status_code == 409, "an exported draft cannot be withdrawn"


def test_a_deployed_app_never_writes_into_the_rules_folder(api, monkeypatch):
    before = tree_digest(RULES)
    did = _approved(api)["draft_id"]
    assert api.post(f"{BASE}/{did}/export", json={}).status_code == 200
    assert tree_digest(RULES) == before
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("PROGRAM_EXPORT_ALLOW_LOCAL_WRITE", "true")
    refused = api.post(f"{BASE}/{did}/export", json={"write_local": True})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "local_write_refused" and tree_digest(RULES) == before


def test_local_write_is_off_by_default_and_never_overwrites(api, tmp_path, monkeypatch):
    rules = tmp_path / "rules"
    shutil.copytree(RULES, rules)
    monkeypatch.setenv("RULES_DIR", str(rules))
    did = _approved(api)["draft_id"]
    assert api.post(f"{BASE}/{did}/export", json={"write_local": True}).json()["detail"]["code"] == "local_write_refused"
    monkeypatch.setenv("PROGRAM_EXPORT_ALLOW_LOCAL_WRITE", "true")
    ok = api.post(f"{BASE}/{did}/export", json={"write_local": True})
    assert ok.status_code == 200 and ok.headers["x-wrote-local-files"] == "3"
    assert (rules / "zy_draft_jtc.json").is_file() and (rules / "zy_draft_jtc" / "2025.json").is_file()
    assert "ZY_DRAFT_JTC" not in (rules / "registry" / "programs.json").read_text(encoding="utf-8"), "the registry entry is the human step"
    assert api.post(f"{BASE}/{did}/export", json={"write_local": True}).status_code == 409


def test_committing_the_bundle_is_what_makes_the_program_calculable(api, tmp_path, monkeypatch):
    did = _approved(api)["draft_id"]
    archive = _zip(api.post(f"{BASE}/{did}/export", json={}))
    rules = tmp_path / "rules"
    shutil.copytree(RULES, rules)
    monkeypatch.setenv("RULES_DIR", str(rules))
    assert dw.CODE not in {p["program_code"] for p in programs()}, "an approved, exported draft changes nothing by itself"
    for name in archive.namelist():
        if name.startswith("rules/"):
            target = rules / name[len("rules/"):]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    manifest = rules / "registry" / "programs.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["programs"] += json.loads(archive.read("registry-patch.json"))["programs"]
    manifest.write_text(json.dumps(data), encoding="utf-8")
    assert [r.file for r in validate_all() if not r.ok] == []
    row = next(p for p in programs() if p["program_code"] == dw.CODE)
    assert row["calculable"] is True and row["authored_years"] == [2024, 2025] and row["placeholder_years"] == [2024, 2025]
