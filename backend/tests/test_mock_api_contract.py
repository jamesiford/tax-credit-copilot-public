"""The sweep mock API serves the shapes the backend serves. [F07.2]

`frontend/tools/mock_programs.py` stands in for the program and draft endpoints so the browser sweeps can render the Program
manager. A mock that drifts from the API proves a page against a shape that no longer exists, so every payload it builds is
compared here, key for key, with the backend's response models (recursively, through nested models and lists of models).
"""

from __future__ import annotations

import importlib.util
import sys
import typing
from pathlib import Path

import pytest
from pydantic import BaseModel

from api import program_draft_models as D
from api import programs as P

_TOOLS = Path(__file__).resolve().parents[2] / "frontend" / "tools"


@pytest.fixture()
def mock():
    sys.path.insert(0, str(_TOOLS))
    try:
        spec = importlib.util.spec_from_file_location("mock_programs_under_test", _TOOLS / "mock_programs.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(_TOOLS))
    return module


def _model_of(annotation) -> type[BaseModel] | None:
    """The BaseModel inside `Model`, `Model | None` or `list[Model]`, else None."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in typing.get_args(annotation):
        found = _model_of(arg)
        if found is not None:
            return found
    return None


def drift(model: type[BaseModel], payload, where: str = "$") -> list[str]:
    """Every difference in keys between a payload and a model, and a failed validation, with its place."""
    problems: list[str] = []
    if not isinstance(payload, dict):
        return [f"{where}: expected an object"]
    fields = model.model_fields
    for key in sorted(set(payload) - set(fields)):
        problems.append(f"{where}.{key}: the mock sends a key the backend model does not have")
    for key in sorted(set(fields) - set(payload)):
        problems.append(f"{where}.{key}: the backend model has a key the mock does not send")
    for key, info in fields.items():
        nested = _model_of(info.annotation)
        value = payload.get(key)
        if nested is None or value is None:
            continue
        for index, item in enumerate(value if isinstance(value, list) else [value]):
            problems += drift(nested, item, f"{where}.{key}" + (f"[{index}]" if isinstance(value, list) else ""))
    return problems


def test_the_drift_check_catches_an_extra_and_a_missing_key():
    assert drift(P.Jurisdiction, {"level": "state"}) == ["$.code: the backend model has a key the mock does not send"]
    assert drift(P.Jurisdiction, {"level": "state", "code": "GA", "extra": 1}) == ["$.extra: the mock sends a key the backend model does not have"]


def test_the_catalog_and_every_program_detail_match_the_backend_models(mock):
    catalog = mock.route("GET", "/api/v2/programs", {}, b"")
    assert drift(P.CatalogOut, catalog) == []
    P.CatalogOut.model_validate(catalog)
    for row in catalog["programs"]:
        detail = mock.route("GET", f"/api/v2/programs/{row['code']}", {}, b"")
        assert drift(P.ProgramDetail, detail) == [], row["code"]
        P.ProgramDetail.model_validate(detail)


def test_the_catalog_has_two_programs_in_one_state_and_says_nothing_is_verified(mock):
    programs = mock.route("GET", "/api/v2/programs", {}, b"")["programs"]
    in_ga = [p for p in programs if p["state"] == "GA" and p["calculable"]]
    assert len(in_ga) == 2
    assert {p["verification"] for p in programs} == {"not_verified"}


def _call(mock, method, path, body=None):
    import json

    result = mock.route(method, path, {}, json.dumps(body).encode() if body is not None else b"")
    return result if isinstance(result, tuple) else (200, result)


def test_every_draft_payload_matches_the_backend_models_through_the_whole_lifecycle(mock):
    status, page = _call(mock, "GET", "/api/v2/program-drafts")
    assert status == 200 and drift(D.DraftsPage, page) == []
    assert {d["status"] for d in page["items"]} >= {"draft", "ready_for_review", "approved_for_export"}

    status, created = _call(mock, "POST", "/api/v2/program-drafts", {"code": "ZZ_SWEEP", "name": "Sweep", "state": "NC"})
    assert status == 201 and drift(D.DraftOut, created) == []
    base = f"/api/v2/program-drafts/{created['draft_id']}"

    _, edited = _call(mock, "PUT", f"{base}/documents", {"expected_version": created["version"], "pack": {"credit": {"name": "Sweep"}}, "years": {}})
    assert drift(D.DraftOut, edited) == []
    status, stale = _call(mock, "PUT", f"{base}/documents", {"expected_version": 1, "pack": {}, "years": {}})
    assert status == 409 and stale["detail"]["code"] == "draft_conflict"

    for action, body in (("validate", {}), ("request-review", {}), ("review", {"decision": "approve"}), ("withdraw", {})):
        status, out = _call(mock, "POST", f"{base}/{action}", body)
        assert status == 200 and drift(D.DraftOut, out) == [], action
        D.DraftOut.model_validate(out)

    approved = next(d for d in page["items"] if d["status"] == "approved_for_export")
    _, preview = _call(mock, "POST", f"/api/v2/program-drafts/{approved['draft_id']}/preview", {})
    assert drift(D.PreviewOut, preview) == [] and preview["persisted"] is False
    _, manifest = _call(mock, "GET", f"/api/v2/program-drafts/{approved['draft_id']}/export/manifest")
    assert drift(D.ManifestOut, manifest) == []
    D.ManifestOut.model_validate(manifest)


def test_a_draft_list_item_is_a_summary_and_has_no_documents(mock):
    _, page = _call(mock, "GET", "/api/v2/program-drafts")
    assert all("documents" not in item for item in page["items"])
    assert all(item["has_runtime_authority"] is False and item["verification"] == "not_verified" for item in page["items"])


def test_the_run_batch_mock_matches_the_backend_models(mock):
    from api import run_batches as R

    sys.path.insert(0, str(_TOOLS))
    try:
        spec = importlib.util.spec_from_file_location("mock_run_batches_under_test", _TOOLS / "mock_run_batches.py")
        batches = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(batches)
    finally:
        sys.path.remove(str(_TOOLS))
    page = batches.route("GET", "/api/v2/run-batches", {}, b"")
    assert drift(R.BatchesPage, page) == []
    first = page["items"][0]
    assert drift(R.BatchOut, batches.route("GET", f"/api/v2/run-batches/{first['batch_id']}", {}, b"")) == []
    assert drift(R.ItemsPage, batches.route("GET", f"/api/v2/run-batches/{first['batch_id']}/items", {}, b"")) == []
