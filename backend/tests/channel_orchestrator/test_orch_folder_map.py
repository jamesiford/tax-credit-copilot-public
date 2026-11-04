"""The orchestrator README's folder map names every module, and explains the two entry points. [RM-25]

`channel_orchestrator/main.py` and `channel_orchestrator/app/main.py` look like a duplicate and are not: the
first is the zip-root launcher that `azure.yaml` (`entryPoint: main.py`) and the Dockerfile name, the second is
the hosting seam. The README says so, and this keeps the claim true: both entry points still name the root
file, so deleting it as "redundant" would fail here before it failed a deploy.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ORCHESTRATOR = ROOT / "channel_orchestrator"
README = (ORCHESTRATOR / "README.md").read_text(encoding="utf-8")


def _modules() -> list[str]:
    return sorted(
        p.stem for p in (ORCHESTRATOR / "app").rglob("*.py")
        if "vendor" not in p.parts and "__pycache__" not in p.parts and p.stem != "__init__"
    )


def test_every_module_under_app_is_in_the_folder_map():
    mapped = README.split("## Folder map", 1)[1].split("## Two", 1)[0]
    missing = []
    for stem in sorted(set(_modules())):
        if stem.startswith("maf_"):
            ok = re.search(rf"\b{stem}\b", mapped)
        else:
            ok = re.search(rf"(?<![A-Za-z_]){stem}(?![A-Za-z_])", mapped)
        if not ok:
            missing.append(stem)
    assert not missing, f"add these modules to channel_orchestrator/README.md: {missing}"


def test_the_readme_explains_the_two_main_files():
    section = README.split("## Two `main.py` files", 1)[1]
    assert "entryPoint" in section and "Dockerfile" in section and "test_orch_hosting_seam.py" in section


def test_the_root_main_is_the_entry_point_the_deployments_name():
    azure = (ORCHESTRATOR / "azure.yaml").read_text(encoding="utf-8")
    dockerfile = (ORCHESTRATOR / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"entryPoint:\s*main\.py", azure)
    assert 'CMD ["python", "main.py"]' in dockerfile and "COPY main.py" in dockerfile
    assert (ORCHESTRATOR / "main.py").is_file() and (ORCHESTRATOR / "app" / "main.py").is_file()
