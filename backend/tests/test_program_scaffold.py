"""The validation CLI and the scaffolder. [ADR-013, F04.5]"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.program_registry import load_registry

REPO = Path(__file__).resolve().parents[2]
RULES = REPO / "backend" / "rules"


@pytest.fixture()
def rules(tmp_path, monkeypatch):
    target = tmp_path / "rules"
    shutil.copytree(RULES, target)
    monkeypatch.setenv("RULES_DIR", str(target))
    return target


def _run(script: str, *args: str, rules_dir: Path):
    env = {**os.environ, "RULES_DIR": str(rules_dir), "PYTHONUTF8": "1"}
    return subprocess.run([sys.executable, str(REPO / "scripts" / script), *args], capture_output=True, text=True, env=env, cwd=REPO)


def test_validate_all_exits_zero_on_the_shipped_packs_and_json_is_parseable(rules):
    ok = _run("validate-rule-pack.py", "--all", "--json", rules_dir=rules)
    assert ok.returncode == 0 and all(r["ok"] for r in json.loads(ok.stdout))


def test_validate_exits_one_on_an_invalid_pack_and_two_on_bad_usage(rules):
    pack = json.loads((rules / "ga_jtc.json").read_text(encoding="utf-8"))
    del pack["benefit"]
    (rules / "ga_jtc.json").write_text(json.dumps(pack), encoding="utf-8")
    assert _run("validate-rule-pack.py", str(rules / "ga_jtc.json"), rules_dir=rules).returncode == 1
    assert _run("validate-rule-pack.py", rules_dir=rules).returncode == 2


def test_a_scaffolded_program_is_a_flagged_draft_that_fails_validation_and_is_not_calculable(rules):
    made = _run("new-program.py", "program", "--code", "ZZ_SCAFFOLD", "--state", "ZZ", "--name", "Scaffold", "--slug", "jtc", rules_dir=rules)
    assert made.returncode == 0, made.stderr
    pack = json.loads((rules / "zz_jtc.json").read_text(encoding="utf-8"))
    assert pack["one_zero"]["min_weekly_hours"] is None and pack["one_zero"]["_prototype_verify"] is True
    entry = load_registry().get("ZZ_SCAFFOLD")
    assert entry.lifecycle == "draft" and entry.status([]) == "draft"
    report = _run("validate-rule-pack.py", str(rules / "zz_jtc.json"), rules_dir=rules)
    assert report.returncode == 1 and "schema" in report.stdout
    assert _run("new-program.py", "program", "--code", "ZZ_SCAFFOLD", "--state", "ZZ", "--name", "x", "--slug", "jtc", rules_dir=rules).returncode == 1


def test_a_year_skeleton_is_a_draft_file_the_engine_cannot_read_and_copies_no_statute(rules):
    from tools.credit_math import authored_years

    done = _run("new-program.py", "year", "--pack", "ga_jtc.json", "--year", "2030", rules_dir=rules)
    assert done.returncode == 0, done.stderr
    skeleton = json.loads((rules / "ga_jtc" / "2030.draft.json").read_text(encoding="utf-8"))
    assert skeleton["tax_year"] == 2030 and skeleton["one_zero"]["min_weekly_wages"] is None
    assert skeleton["benefit"]["amount_per_qualifying_job_usd"] is None and "eligibility" not in skeleton
    assert 2030 not in authored_years("ga_jtc.json")
    assert _run("new-program.py", "year", "--pack", "ga_jtc.json", "--year", "2030", rules_dir=rules).returncode == 1
    assert _run("new-program.py", "year", "--pack", "ga_jtc.json", "--year", "2031", "--dry-run", rules_dir=rules).returncode == 0
    assert not (rules / "ga_jtc" / "2031.draft.json").exists()
