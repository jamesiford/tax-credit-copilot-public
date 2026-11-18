"""validate-data-map.py, plan-data-map-change.py and generate-data-map.py. [R2.1, R2.4, R2.5]"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHIPPED = ROOT / "docs" / "data" / "data-map.json"


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args], capture_output=True, text=True, cwd=ROOT)


def _map(tmp_path, mutate, name="map.json"):
    doc = json.loads(SHIPPED.read_text(encoding="utf-8"))
    mutate(doc)
    path = tmp_path / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_the_validator_accepts_the_shipped_file():
    done = _run("validate-data-map.py", str(SHIPPED))
    assert done.returncode == 0 and "valid" in done.stdout


def test_the_validator_prints_every_problem(tmp_path):
    def break_it(doc):
        doc["warehouse"]["tables"]["ops.run_manifest"]["table"] = "bad name"
        doc["lakehouse"]["tables"]["Payroll"]["table"] = None

    done = _run("validate-data-map.py", str(_map(tmp_path, break_it)))
    assert done.returncode == 1
    assert "INVALID" in done.stdout and "warehouse.tables.ops.run_manifest.table" in done.stdout


def test_the_plan_for_an_unchanged_map_is_only_the_review_banner(tmp_path):
    done = _run("plan-data-map-change.py", "--current", str(SHIPPED), "--new", str(SHIPPED))
    assert done.returncode == 0
    assert [ln for ln in done.stdout.splitlines() if ln and not ln.startswith("--")] == []


def test_the_plan_lists_renames_as_comments_and_selects_and_nothing_destructive(tmp_path):
    new = _map(tmp_path, lambda d: d["warehouse"]["tables"]["ops.run_manifest"].update(table="runs"))
    done = _run("plan-data-map-change.py", "--current", str(SHIPPED), "--new", str(new))
    assert done.returncode == 0
    assert "sp_rename 'tcc_ops.run_manifest', 'runs'" in done.stdout
    assert not any(w in done.stdout.upper() for w in ("DROP ", "TRUNCATE ", "DELETE "))
    runnable = [ln for ln in done.stdout.splitlines() if ln and not ln.lstrip().startswith("--")]
    assert all(ln.startswith("SELECT") for ln in runnable)


def test_the_draft_generator_modules_load_without_a_database():
    spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "generate-data-map.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    assert gen.build_defaults()["warehouse"]["tables"]
