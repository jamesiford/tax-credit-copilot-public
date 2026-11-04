"""The hosting seam is provable: one file touches the hosting package, and the protocols Teams needs stay declared. [RM-12, D-128]

RM-06 found `agent-framework-foundry-hosting` pre-release only (newest `1.0.0b261030`) with no Activity handler, so
the orchestrator keeps its own thin host on the stable `azure-ai-agentserver-responses` package and the swap, if it
ever comes, is one file. Two things keep that true and are pinned here rather than remembered:

1. **The seam.** Only `app/main.py` may import a hosting package; the zip-root `main.py` only starts it; the agent
   framework stays in the `maf_*` modules; the beta hosting package is not a requirement.
2. **The protocols (D-100).** `azure.yaml` declares `activity` on the agent ENDPOINT only. Declared on the container as
   well, the platform posts Teams messages to `/activity/messages`, which this container does not serve, and Teams goes
   silent with no error. The container serves `responses` and nothing else.

The YAML reading is a few lines of indentation walking because this repository's tests carry no YAML dependency.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ORCHESTRATOR = ROOT / "channel_orchestrator"
SEAM = "channel_orchestrator/app/main.py"
HOSTING = ("azure.ai.agentserver", "agent_framework_foundry_hosting")
FRAMEWORK = ("agent_framework",)
SKIPPED_PARTS = {"vendor", "__pycache__", ".venv", ".azure", "node_modules", "tests", ".terraform"}
SERVICE = "tcc-channel-orchestrator"


def python_files(*roots: Path) -> list[Path]:
    return sorted(p for root in roots for p in root.rglob("*.py") if not SKIPPED_PARTS & set(p.relative_to(root).parts))


def imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def uses(path: Path, prefixes: tuple[str, ...]) -> bool:
    """True when `path` imports one of `prefixes` or a package that extends one (`agent_framework` covers `agent_framework_openai`)."""
    return any(m == x or m.startswith((x + ".", x + "_")) for m in imports(path) for x in prefixes)


def importers(prefixes: tuple[str, ...], files: list[Path]) -> list[str]:
    return [rel(p) for p in files if uses(p, prefixes)]


# ------------------------------------------------------------------------ the seam


def test_only_the_seam_imports_a_hosting_package_anywhere_in_the_repository():
    files = python_files(ORCHESTRATOR, ROOT / "backend", ROOT / "scripts")
    assert importers(HOSTING, files) == [SEAM]


def test_the_zip_root_entry_point_only_starts_the_seam():
    root_main = ORCHESTRATOR / "main.py"
    assert imports(root_main) == {"app.main"}, "the zip-root file starts `app.main` and nothing else"
    assert (ORCHESTRATOR / "app" / "main.py").is_file()


def test_the_agent_framework_is_imported_by_the_maf_layer_and_nowhere_else_in_the_orchestrator():
    files = python_files(ORCHESTRATOR)
    users = importers(FRAMEWORK, files)
    assert users and all(Path(u).name.startswith("maf_") and "/app/core/" in u for u in users), users


def test_the_seam_registers_one_handler_and_hands_everything_to_the_host_and_the_wiring():
    path = ORCHESTRATOR / "app" / "main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    handlers = [d for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for d in n.decorator_list
                if "response_handler" in ast.unparse(d)]
    assert len(handlers) == 1, "one Responses handler; Activity is converted by the platform, not served here"
    ours = {m for m in imports(path) if m.split(".")[0] == "app"}
    assert ours == {"app.host", "app.wiring"}, f"the seam reaches the orchestrator only through the host and the wiring: {ours}"
    assert len(path.read_text(encoding="utf-8").splitlines()) <= 60, "a seam that grows is a host that is not swappable in one file"
    assert not importers(FRAMEWORK, [path]), "the seam does not touch the agent framework"


def test_the_pre_release_hosting_package_is_not_a_requirement_and_no_pre_flag_is_used():
    for requirements in (ORCHESTRATOR / "requirements.txt", ROOT / "backend" / "requirements.txt"):
        live = [l.strip() for l in requirements.read_text(encoding="utf-8").splitlines() if l.strip() and not l.lstrip().startswith("#")]
        assert not [l for l in live if re.match(r"agent[-_]framework[-_]foundry[-_]hosting", l, re.IGNORECASE)], requirements
        assert not [l for l in live if l.startswith("--pre") or "--pre " in l], f"{requirements.name} installs pre-releases"
    stable = (ORCHESTRATOR / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^azure-ai-agentserver-responses==\d+\.\d+\.\d+$", stable, re.MULTILINE), "the stable Responses host is pinned"


def test_the_entry_point_azure_and_the_container_image_all_start_the_same_file():
    yaml = (ORCHESTRATOR / "azure.yaml").read_text(encoding="utf-8")
    assert re.search(r"^\s+entryPoint:\s*main\.py\s*$", yaml, re.MULTILINE)
    assert re.search(r'^CMD \["python", "main\.py"\]\s*$', (ORCHESTRATOR / "Dockerfile").read_text(encoding="utf-8"), re.MULTILINE)


@pytest.mark.parametrize("source", [
    "import agent_framework_foundry_hosting",
    "from agent_framework_foundry_hosting import ResponsesHostServer",
    "from azure.ai.agentserver.responses import TextResponse",
    "import azure.ai.agentserver.core",
])
def test_the_import_scan_sees_a_hosting_import_in_any_form(tmp_path, source):
    path = tmp_path / "module.py"
    path.write_text(source + "\n", encoding="utf-8")
    assert uses(path, HOSTING)


def test_the_import_scan_leaves_ordinary_azure_imports_alone(tmp_path):
    path = tmp_path / "module.py"
    path.write_text("import json\nfrom azure.identity import DefaultAzureCredential\nfrom azure.ai.projects import AIProjectClient\n", encoding="utf-8")
    assert not uses(path, HOSTING)


# ---------------------------------------------------- the protocols (the Teams-silencing guard)


def nested(lines: list[str], key: str) -> list[str]:
    """The lines under `key:` where `key` is a direct child of `lines` (the shallowest indent present)."""
    live = [l for l in lines if l.strip() and not l.lstrip().startswith("#")]
    base = min((len(l) - len(l.lstrip()) for l in live), default=0)
    for number, line in enumerate(lines):
        if len(line) - len(line.lstrip()) == base and re.match(rf"^\s*{re.escape(key)}:\s*(#.*)?$", line):
            block = []
            for later in lines[number + 1:]:
                if later.strip() and not later.lstrip().startswith("#") and len(later) - len(later.lstrip()) <= base:
                    break
                block.append(later)
            return block
    raise AssertionError(f"azure.yaml has no `{key}:` block here")


def names_in(block: list[str]) -> list[str]:
    """The protocol names in a list block: `- responses` or `- protocol: responses`."""
    found = []
    for line in block:
        match = re.match(r"^\s*-\s*(?:protocol:\s*)?([A-Za-z0-9_.-]+)\s*(#.*)?$", line)
        if match:
            found.append(match.group(1))
    return found


def protocol_problems(text: str) -> list[str]:
    """Why this azure.yaml would silence Teams, or []. Both rules are D-100."""
    service = nested(nested(text.splitlines(), "services"), SERVICE)
    container, endpoint = names_in(nested(service, "protocols")), names_in(nested(nested(service, "agentEndpoint"), "protocols"))
    problems = []
    if container != ["responses"]:
        problems.append(f"the container's protocols must be exactly ['responses'], not {container}: `activity` there makes the platform "
                        "post Teams messages to /activity/messages, which the container does not serve")
    for needed in ("activity", "responses"):
        if needed not in endpoint:
            problems.append(f"the agent endpoint's protocols lack `{needed}`: {endpoint}")
    return problems


def test_the_real_azure_yaml_declares_activity_on_the_endpoint_only():
    text = (ORCHESTRATOR / "azure.yaml").read_text(encoding="utf-8")
    assert protocol_problems(text) == []
    service = nested(nested(text.splitlines(), "services"), SERVICE)
    assert names_in(nested(service, "protocols")) == ["responses"]
    assert {"activity", "responses"} <= set(names_in(nested(nested(service, "agentEndpoint"), "protocols")))


GOOD = """
services:
  tcc-channel-orchestrator:
    host: azure.ai.agent
    agentEndpoint:
      protocols:
        - responses
        - activity
    container:
      resources:
        cpu: "0.5"
    protocols:
      - protocol: responses
        version: 2.0.0
"""


@pytest.mark.parametrize("text, expected", [
    (GOOD.replace("      - protocol: responses\n        version: 2.0.0\n", "      - protocol: responses\n        version: 2.0.0\n      - protocol: activity\n        version: 1.0.0\n"), "container's protocols"),
    (GOOD.replace("      - protocol: responses\n        version: 2.0.0\n", "      - protocol: activity\n        version: 1.0.0\n"), "container's protocols"),
    (GOOD.replace("      - protocol: responses\n        version: 2.0.0\n", "      - protocol: responses\n        version: 2.0.0\n      - protocol: invocations\n        version: 1.0.0\n"), "container's protocols"),
    (GOOD.replace("        - activity\n", ""), "lack `activity`"),
    (GOOD.replace("        - responses\n", ""), "lack `responses`"),
])
def test_the_guard_catches_each_way_teams_goes_silent(text, expected):
    assert any(expected in problem for problem in protocol_problems(text)), protocol_problems(text)


def test_the_guard_accepts_the_known_good_shape():
    assert protocol_problems(GOOD) == []


def test_a_missing_container_protocols_block_fails_rather_than_passes():
    swapped = GOOD.replace("    protocols:\n      - protocol: responses\n        version: 2.0.0\n", "")
    with pytest.raises(AssertionError, match="no `protocols:` block"):
        protocol_problems(swapped)


# ----------------------------------------------------------------------- the record


def test_the_no_go_and_its_recheck_conditions_are_written_down():
    alignment = (ROOT / "docs" / "m365-channel" / "MAF-ALIGNMENT.md").read_text(encoding="utf-8")
    decisions = (ROOT / "docs" / "m365-channel" / "DECISIONS.md").read_text(encoding="utf-8")
    assert re.search(r"^## D-128 ", decisions, re.MULTILINE)
    start = alignment.index("## Hosting: go / no-go and when to re-check")
    section = alignment[start: alignment.index("\n## ", start + 5)]
    for condition in ("generally available", "Activity", "get_request_context", "azure.yaml", "check_all"):
        assert condition in section, f"the re-check conditions no longer mention {condition!r}"
