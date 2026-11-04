"""The scripts folder is indexed, named by one convention, and the azd-run scripts stay put. [RM-24]

`scripts/README.md` says who runs each script. That is only worth reading if it cannot go stale, so a
script added without a row fails here. Names follow the hyphen convention, with the three exceptions that
Python must import by name. The scripts azd and CI run (and what they call) are pinned to the top level:
a hook, a workflow step or a doc names them by path, and a move would break a deploy with no test failing.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"
README = (SCRIPTS / "README.md").read_text(encoding="utf-8")

#: Underscore names that Python imports by name, and why each may not be hyphenated.
UNDERSCORE_ALLOWED = {
    "sql_common.py": "imported as `sql_common` by the SQL scripts and loaded by tests under that name",
    "branding_icons": "helper package imported by render-icons.py",
    "cowork_plugin": "helper package imported by build-cowork-plugin.py",
}
#: Modules inside a subfolder that a sibling imports by name.
UNDERSCORE_INSIDE = {"portable-rules/flex_rules.py": "crosscheck.py imports it, and the hand-off is a notebook import"}
#: Run by azd or CI, or called by something that is: never moved or renamed.
PINNED_AT_TOP = (
    "postprovision.ps1", "deploy-channel.ps1", "apply-migrations.py", "grant-warehouse-sql.py",
    "seed-operational-store.ps1", "package-app.py", "sql_common.py", "check-whitelabel.ps1",
    "audit-export.py", "whitelabel-allowlist.txt", "vendor-orchestrator.py",
)
HELPER_PACKAGES = {"branding_icons", "cowork_plugin"}


def _entries() -> list[Path]:
    return sorted(p for p in SCRIPTS.iterdir() if p.name != "__pycache__" and p.name != "README.md")


def test_every_script_and_folder_has_a_row_in_the_index():
    missing = []
    for entry in _entries():
        if entry.is_file():
            if f"`{entry.name}`" not in README:
                missing.append(entry.name)
        elif entry.name == "maintainer":
            missing += [f"maintainer/{f.name}" for f in entry.iterdir() if f"`maintainer/{f.name}`" not in README]
        elif f"`{entry.name}/`" not in README:
            missing.append(entry.name + "/")
    assert not missing, f"add a row to scripts/README.md for: {missing}"


def test_the_index_names_nothing_that_does_not_exist():
    stale = []
    for name in re.findall(r"^\| `([^`]+)` \|", README, re.M):
        if not (SCRIPTS / name.rstrip("/")).exists():
            stale.append(name)
    assert not stale, f"scripts/README.md indexes missing entries: {stale}"


def test_scripts_use_the_hyphen_convention():
    offenders = []
    for entry in _entries():
        if "_" in entry.name and entry.name not in UNDERSCORE_ALLOWED:
            offenders.append(entry.name)
        if entry.is_dir() and entry.name not in HELPER_PACKAGES:
            for inner in entry.rglob("*"):
                rel = inner.relative_to(SCRIPTS).as_posix()
                if inner.is_file() and "__pycache__" not in inner.parts and "_" in inner.name \
                        and rel not in UNDERSCORE_INSIDE:
                    offenders.append(rel)
    assert not offenders, f"rename with hyphens (or justify in UNDERSCORE_ALLOWED): {offenders}"


def test_the_scripts_azd_and_ci_run_stay_at_the_top_level():
    for name in PINNED_AT_TOP:
        assert (SCRIPTS / name).is_file(), f"scripts/{name} is run by azd or CI and must not move"


def _references(text: str) -> set[str]:
    return set(re.findall(r"scripts[/\\]([A-Za-z0-9_./\\-]+\.(?:py|ps1|txt))", text))


def test_every_script_a_hook_or_workflow_names_exists_at_that_path():
    sources = [ROOT / "azure.yaml", ROOT / "channel_orchestrator" / "azure.yaml"]
    sources += sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
    broken = []
    for source in sources:
        for ref in _references(source.read_text(encoding="utf-8")):
            if not (SCRIPTS / ref.replace("\\", "/")).exists():
                broken.append(f"{source.name}: scripts/{ref}")
    assert not broken, broken


def test_the_scripts_a_hook_calls_exist_beside_it():
    broken = []
    for hook in ("postprovision.ps1", "deploy-channel.ps1", "seed-operational-store.ps1"):
        text = (SCRIPTS / hook).read_text(encoding="utf-8")
        for called in re.findall(r"Join-Path \$PSScriptRoot '([^']+)'", text):
            if not (SCRIPTS / called).exists():
                broken.append(f"{hook} -> {called}")
    assert not broken, broken


def test_a_script_in_a_subfolder_is_referenced_by_no_hook_workflow_or_dockerfile():
    sub_scripts = [p.relative_to(SCRIPTS).as_posix() for p in (SCRIPTS / "maintainer").iterdir() if p.is_file()]
    watched = [ROOT / "azure.yaml", ROOT / "channel_orchestrator" / "azure.yaml"]
    watched += sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
    watched += sorted(ROOT.glob("**/Dockerfile*"))
    watched = [p for p in watched if "node_modules" not in p.parts and ".venv" not in p.parts]
    hits = [(p.name, s) for p in watched for s in sub_scripts if s.split("/")[-1] in p.read_text(encoding="utf-8")]
    assert not hits, f"a hook-run script belongs at the top level, not in maintainer/: {hits}"
