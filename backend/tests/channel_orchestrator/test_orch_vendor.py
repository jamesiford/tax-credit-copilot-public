"""The vendoring script: a computed closure, a verifiable copy, and a copy that stands alone. [CH-08]"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "vendor-orchestrator.py"


@pytest.fixture
def vendor():
    spec = importlib.util.spec_from_file_location("vendor_orchestrator_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_seed_exists_and_the_closure_stays_inside_the_allowed_layers(vendor):
    closure = vendor.closure()
    assert set(vendor.SEEDS) <= set(closure)
    for name in closure:
        assert name.startswith(vendor.ALLOWED_PREFIXES) or name in vendor.PARENT_PACKAGES, name
    assert (ROOT / "backend" / vendor.DATA_FILES[0]).exists()


def test_the_closure_is_standard_library_only_outside_the_model_access_adapters(vendor):
    """The script raises on anything else; this pins that the real tree satisfies it today."""
    files = vendor.files_to_copy()
    outside_ai = [p for p in files if p.endswith(".py") and not p.startswith("infrastructure/ai/")]
    assert outside_ai and not [p for p in outside_ai if "import httpx" in (ROOT / "backend" / p).read_text(encoding="utf-8")]


def test_write_then_check_agree_and_writing_twice_changes_nothing(vendor, tmp_path, monkeypatch):
    monkeypatch.setattr(vendor, "TARGET", tmp_path / "tcc_shared")
    first = vendor.write()
    second = vendor.write()
    assert first == second and vendor.check() == []
    listed = {str(p.relative_to(vendor.TARGET)).replace("\\", "/") for p in vendor.TARGET.rglob("*") if p.is_file()}
    assert listed == set(first) | {"MANIFEST.json"}


def test_check_reports_a_changed_a_missing_and_an_unneeded_file(vendor, tmp_path, monkeypatch):
    monkeypatch.setattr(vendor, "TARGET", tmp_path / "tcc_shared")
    vendor.write()
    (vendor.TARGET / "application" / "composer.py").write_text("# tampered\n", encoding="utf-8")
    (vendor.TARGET / "application" / "numeric_guard.py").unlink()
    manifest = json.loads((vendor.TARGET / "MANIFEST.json").read_text(encoding="utf-8"))
    manifest["application/not_needed.py"] = "0" * 64
    (vendor.TARGET / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    problems = "\n".join(vendor.check())
    assert "application/composer.py differs" in problems and "application/numeric_guard.py differs" in problems
    assert "application/not_needed.py is in the copy but no longer needed" in problems


def test_check_says_so_when_there_is_no_copy(vendor, tmp_path, monkeypatch):
    monkeypatch.setattr(vendor, "TARGET", tmp_path / "missing")
    assert "does not exist" in vendor.check()[0]


def test_a_module_that_reaches_a_forbidden_layer_or_package_stops_the_copy(vendor, tmp_path, monkeypatch):
    backend = tmp_path / "backend"
    for package in ("application", "api"):
        (backend / package).mkdir(parents=True)
        (backend / package / "__init__.py").write_text('"""p"""\n', encoding="utf-8")
    (backend / "application" / "reaches_api.py").write_text("from api import thing\n", encoding="utf-8")
    (backend / "application" / "uses_requests.py").write_text("import requests\n", encoding="utf-8")
    (backend / "application" / "fine.py").write_text("import json\n", encoding="utf-8")
    monkeypatch.setattr(vendor, "BACKEND", backend)
    assert "application.fine" in vendor.closure(("application.fine",))
    with pytest.raises(vendor.VendorError, match="outside the layers"):
        vendor.closure(("application.reaches_api",))
    with pytest.raises(vendor.VendorError, match="third-party"):
        vendor.closure(("application.uses_requests",))


def test_the_vendored_copy_runs_on_its_own_without_the_backend(tmp_path):
    """A subprocess whose path holds only the orchestrator: the shared modules must come from the copy."""
    code = (
        "import app, application, domain\n"
        "assert 'tcc_shared' in application.__file__ and 'tcc_shared' in domain.__file__, application.__file__\n"
        "import app.core.turn, app.core.planner, app.wiring, app.host\n"
        "from application.composer import compose\n"
        "from application.capabilities.envelope import Block\n"
        "ok = compose([Block('paragraph', text='fine')], 'no digits here', {})\n"
        "bad = compose([Block('paragraph', text='fine')], 'typed 12345', {})\n"
        "assert ok.narration_used and not bad.narration_used and bad.guard.status == 'rejected'\n"
        "print('standalone ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=120,
        env={"PYTHONPATH": str(ROOT / "channel_orchestrator"), "PATH": "", "SYSTEMROOT": "C:\\Windows"} if sys.platform == "win32"
        else {"PYTHONPATH": str(ROOT / "channel_orchestrator")},
    )
    assert result.returncode == 0 and "standalone ok" in result.stdout, result.stderr[-2000:]
