"""The draft customer-data detector: what it catches, what it must leave alone, and that it never echoes a value. [F07.3]"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from application.program_drafts import customer_data as cd
from domain.program_drafts import DraftStatus, ProgramDraft
from tests import draft_world as dw

BASE = "/api/v2/program-drafts"


def _draft(pack=None, years=None, name="Zedland Two Jobs Credit") -> ProgramDraft:
    return ProgramDraft(draft_id="d", proposed_code="ZZ_DEMO", name=name, jurisdiction_level="state", state="ZZ", status=DraftStatus.DRAFT,
                        version=1, created_by="a", created_at=None, updated_by="a", updated_at=None, pack=pack, years=years or {})


def _hits(text, names=()):
    return cd.scan_documents(_draft(pack={"notes": text}), names=names)


@pytest.mark.parametrize("text, what", [
    ("employee 123-45-6789 qualified", "social security"),
    ("EIN 12-3456789 on file", "employer identification"),
    ("write to someone@example.org about it", "email"),
    ("call (404) 555-0134 or 404-555-0134 or +1 404.555.0134", "phone"),
    ("account 1234567890123", "long digit string"),
])
def test_it_catches_identifier_shaped_text(text, what):
    findings = _hits(text)
    assert findings and all(f["severity"] == "error" and f["code"] == "customer_data" for f in findings)
    assert any(what in f["message"] for f in findings)
    assert all(f["file"] == "pack" and f["path"] == "/notes" for f in findings)


@pytest.mark.parametrize("text", [
    "applies to tax years 2019 through 2026",
    "credit of $3,500 per job, capped at $10,000,000 in total",
    "O.C.G.A. section 48-7-40.17(b)(2) and Reg. 560-7-8-.34",
    "26 U.S.C. section 51, 3 jobs minimum, 35 hours per week",
    "effective 2023-07-28 through 2024-08-02, version 2023.1",
    "Ga. Comp. R. & Regs. 110-9-1-.02(1)(a)",
    "rate 0.0765 of wages up to 168600",
    "Form 8850, Form 5884, Schedule A, line 12",
])
def test_it_leaves_years_caps_citations_and_section_numbers_alone(text):
    assert _hits(text) == []


def test_numbers_in_a_pack_are_statute_values_and_are_not_scanned():
    assert cd.scan_documents(_draft(pack={"benefit": {"cap": 1234567890123, "per_job": 3500}})) == []


def test_a_client_or_employer_name_in_the_book_is_a_blocking_finding_and_a_short_name_is_ignored():
    assert _hits("the Acme Foods account", names=["Acme Foods"])
    assert _hits("ACME FOODS", names=["Acme Foods"]), "case does not matter"
    assert _hits("the Acme Foods-adjacent clause", names=["Acme Foods"]), "a word boundary, not a substring of a longer word"
    assert _hits("Acme Foodstuffs", names=["Acme Foods"]) == [], "a longer word is not the name"
    assert _hits("the AB clause", names=["AB"]) == [], "a name under four characters would match ordinary text"


def test_it_names_the_field_and_never_repeats_the_matched_value():
    secret, name = "123-45-6789", "Zebra Holdings"
    findings = cd.scan_documents(_draft(pack={"credit": {"notes": f"{secret} {name}"}}, years={"2025": {"source": name}}), names=[name])
    assert {(f["file"], f["path"]) for f in findings} == {("pack", "/credit/notes"), ("year 2025", "/source")}
    assert secret not in repr(findings) and name not in repr(findings)


def test_the_draft_name_is_scanned_too():
    assert [f["file"] for f in cd.scan_documents(_draft(name="Zebra Holdings credit"), names=["Zebra Holdings"])] == ["draft"]


def test_an_unreadable_book_loses_only_the_name_match(monkeypatch, caplog):
    def boom():
        raise RuntimeError("no source")

    monkeypatch.setattr("application.client_book.clients", boom)
    with caplog.at_level("WARNING"):
        assert cd.book_names() == []
    assert any("names unavailable" in r.message for r in caplog.records)
    assert _hits("call 404-555-0134")


@pytest.fixture()
def api(monkeypatch):
    import main
    from bootstrap import program_draft_wiring
    from infrastructure.persistence.sqlite_program_drafts import SqliteProgramDraftRepository

    repo = SqliteProgramDraftRepository(":memory:")
    program_draft_wiring.set_program_draft_repository(repo)
    monkeypatch.setattr(cd, "book_names", lambda: ["Zebra Holdings"])
    yield TestClient(main.app)
    program_draft_wiring.set_program_draft_repository(None)
    repo.close()


def test_validate_blocks_a_draft_with_customer_data_and_the_save_records_the_count(api):
    draft = api.post(BASE, json={"code": dw.CODE, "name": "Zedland Two", "state": dw.STATE, "years": [2024], "actor": "ann"}).json()
    docs, did = dw.documents(), draft["draft_id"]
    docs["pack"]["credit"]["notes"] = "ask Zebra Holdings, contact j.doe@example.org"
    saved = api.put(f"{BASE}/{did}/documents", json={"expected_version": draft["version"], "pack": docs["pack"], "years": docs["years"], "actor": "ann"})
    assert saved.status_code == 200, "a save is allowed so the author can remove it"
    assert api.get(f"{BASE}/{did}").json()["events"][-1]["detail"]["customer_data_findings"] == 2
    result = api.post(f"{BASE}/{did}/validate", json={"actor": "ann"}).json()["validation"]
    leaks = [f for f in result["findings"] if f["code"] == "customer_data"]
    assert result["valid"] is False and len(leaks) == 2
    assert all(f["path"] == "/credit/notes" and f["severity"] == "error" for f in leaks)
    assert "Zebra" not in str(result) and "example.org" not in str(result)
    assert api.post(f"{BASE}/{did}/request-review", json={"actor": "ann"}).status_code == 422
