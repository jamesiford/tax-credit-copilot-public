"""App Service packages honour .webappignore, in CI exactly as under azd. [HOST-6]"""
from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path, PurePosixPath

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture
def pkg():
    spec = importlib.util.spec_from_file_location("package_app", SCRIPTS / "package-app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tree(root: Path, files: list[str]) -> None:
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")


def test_private_and_local_files_never_reach_the_zip(pkg, tmp_path):
    root = tmp_path / "backend"
    _tree(root, [
        "main.py", "api/app.py", "startup.sh", ".env", ".env.example",
        "data/payroll/One.csv", "data/reference_output/x.json", "data/operational.db",
        "data/payroll_pay_periods.csv", "tests/test_x.py", "api/__pycache__/a.pyc", ".venv/lib/x.py",
    ])
    (root / ".webappignore").write_text(
        (Path(__file__).resolve().parents[1] / ".webappignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    included = set(pkg.package(root, tmp_path / "api.zip"))
    assert {"main.py", "api/app.py", "startup.sh", "data/payroll_pay_periods.csv"} <= included
    for private in (".env", ".env.example", "data/payroll/One.csv", "data/reference_output/x.json",
                    "data/operational.db", "tests/test_x.py", "api/__pycache__/a.pyc", ".venv/lib/x.py",
                    ".webappignore"):
        assert private not in included, private
    with zipfile.ZipFile(tmp_path / "api.zip") as archive:
        assert set(archive.namelist()) == included


@pytest.mark.parametrize(
    "path, pattern, expected",
    [
        ("data/payroll/One.csv", "data/payroll/", True),
        ("x/data/payroll/One.csv", "data/payroll/", False),
        ("a/node_modules/m.js", "node_modules/", True),
        ("deep/file.pyc", "*.pyc", True),
        ("deep/file.py", "*.pyc", False),
    ],
)
def test_pattern_semantics(pkg, path, pattern, expected):
    assert pkg.excluded(PurePosixPath(path), [pattern]) is expected
