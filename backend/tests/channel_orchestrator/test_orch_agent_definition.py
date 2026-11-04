"""The orchestrator's declarative definition (`azure.yaml`) matches the documented `azd ai agent` shape. [RM-11]

`azure.yaml` is the agent's definition: the hosted-agent service, its code deployment, its
environment, its endpoint. The extension's current reference (Microsoft Learn, "azure.yaml
reference for hosted agents", read 2026-11-04) names the fields and their limits, and says the
older `agent.manifest.yaml` / `agent.yaml` pair is legacy and rejected by `azd ai agent init`.
These tests hold our file to that reference without running azd (nothing here deploys), and
leave the protocols to `test_orch_hosting_seam.py`, which already guards them (D-100).

The reader below is a few lines of indentation walking, because the test environment carries no
YAML dependency; it understands exactly the shapes this file uses.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ORCHESTRATOR = ROOT / "channel_orchestrator"
AZURE_YAML = ORCHESTRATOR / "azure.yaml"
SERVICE = "tcc-channel-orchestrator"
SECRETISH = re.compile(r"(SECRET|PASSWORD|TOKEN|API_?KEY|CONNECTION_STRING|CREDENTIAL)", re.IGNORECASE)
RUNTIMES = {"python_3_13", "python_3_14"}


def scalar(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def parse(text: str):
    """Maps, lists of scalars and lists of maps, by indentation. Comments and blank lines are ignored."""
    lines = [(len(l) - len(l.lstrip()), l.strip()) for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]

    def block(start: int, indent: int):
        if lines[start][1].startswith("- "):
            items, i = [], start
            while i < len(lines) and lines[i][0] == indent and lines[i][1].startswith("- "):
                body = lines[i][1][2:]
                if ":" in body and not body.startswith(("$", '"')):
                    key, _, value = body.partition(":")
                    item = {key.strip(): scalar(value)}
                    j = i + 1
                    while j < len(lines) and lines[j][0] > indent:
                        k, _, v = lines[j][1].partition(":")
                        item[k.strip()] = scalar(v)
                        j += 1
                    items.append(item)
                    i = j
                else:
                    items.append(scalar(body))
                    i += 1
            return items, i
        mapping, i = {}, start
        while i < len(lines) and lines[i][0] == indent and not lines[i][1].startswith("- "):
            key, _, value = lines[i][1].partition(":")
            if value.strip():
                mapping[key.strip()] = scalar(value)
                i += 1
            elif i + 1 < len(lines) and lines[i + 1][0] > indent:
                mapping[key.strip()], i = block(i + 1, lines[i + 1][0])
            else:
                mapping[key.strip()], i = "", i + 1
        return mapping, i

    return block(0, lines[0][0])[0]


DEFINITION = parse(AZURE_YAML.read_text(encoding="utf-8"))
AGENT = DEFINITION["services"][SERVICE]


def test_the_reader_understands_the_shapes_the_file_uses():
    sample = parse("a:\n  b: 'x'\n  c:\n    - one\n    - protocol: p\n      version: 2.0.0\n  d: ${V=teams}\n")
    assert sample == {"a": {"b": "x", "c": ["one", {"protocol": "p", "version": "2.0.0"}], "d": "${V=teams}"}}


def test_the_project_and_the_agent_are_the_documented_service_hosts():
    assert DEFINITION["name"] == SERVICE
    assert DEFINITION["services"]["foundry-project"]["host"] == "azure.ai.project"
    assert AGENT["host"] == "azure.ai.agent" and AGENT["kind"] == "hosted"
    assert AGENT["name"] == SERVICE, "reusing a name creates a new version of the existing agent; the service key and the agent name agree"
    assert AGENT["uses"] == ["foundry-project"]
    assert AGENT["description"].strip()


def test_the_extension_floor_is_declared_at_the_documented_minimum():
    constraint = DEFINITION["requiredVersions"]["extensions"]["azure.ai.agents"]
    assert constraint.startswith(">=1.0.0-beta.") and int(constraint.rsplit(".", 1)[1]) >= 20


def test_the_code_deployment_is_source_not_an_image_and_points_at_a_real_entry_point():
    config = AGENT["codeConfiguration"]
    assert config["runtime"] in RUNTIMES
    assert config["dependencyResolution"] in {"remote_build", "bundled"}
    assert (ORCHESTRATOR / config["entryPoint"]).is_file(), "the entry point is one filename at the zip root"
    assert "image" not in AGENT, "codeConfiguration and a prebuilt image are mutually exclusive"
    assert (ORCHESTRATOR / "requirements.txt").is_file()


def test_the_container_resources_are_inside_the_documented_range():
    resources = AGENT["container"]["resources"]
    assert 0.25 <= float(resources["cpu"]) <= 4.0
    assert 0.5 <= float(resources["memory"].removesuffix("Gi")) <= 8.0


def test_the_endpoint_authorisation_includes_the_scheme_activity_requires():
    schemes = [entry["type"] for entry in AGENT["agentEndpoint"]["authorizationSchemes"]]
    assert "BotServiceRbac" in schemes and set(schemes) <= {"Entra", "BotServiceRbac"}


def test_there_is_no_identity_block_and_no_legacy_manifest():
    assert "identity" not in AGENT, "each hosted agent gets its own agent identity; an identity block is not declared"
    found = [p for name in ("agent.manifest.yaml", "agent.yaml") for p in ORCHESTRATOR.rglob(name) if ".azure" not in p.parts]
    assert found == [], f"legacy two-file manifests are rejected by the current extension: {found}"


# ------------------------------------------------------------------ the environment


def env_keys() -> list[str]:
    return list(AGENT["env"])


def test_python_startup_is_pinned_as_the_runtime_documentation_requires():
    assert AGENT["env"]["PYTHONNOUSERSITE"] == "1"


def reserved_or_secret(key: str) -> bool:
    platform = {"APPLICATIONINSIGHTS_CONNECTION_STRING", "AZURE_AI_MODEL_DEPLOYMENT_NAME"}
    return key.startswith(("FOUNDRY_", "AGENT_")) or key in platform or bool(SECRETISH.search(key))


#: Declared although the documentation reserves the prefix; worked on the live service (CH-14). F-17 in REMEDIATION-FINDINGS.md.
KNOWN_EXCEPTIONS = {"FOUNDRY_MODEL"}


def test_no_reserved_platform_variable_and_no_secret_is_declared():
    assert not [k for k in env_keys() if k not in KNOWN_EXCEPTIONS and reserved_or_secret(k)], \
        "the platform reserves FOUNDRY_*/AGENT_*, and the orchestrator holds no secret (its identity is the agent's)"


def test_the_one_known_exception_is_still_declared_so_the_list_cannot_go_stale():
    assert KNOWN_EXCEPTIONS <= set(env_keys())


def test_every_value_is_an_azd_reference_or_a_plain_literal():
    for key, value in AGENT["env"].items():
        assert re.fullmatch(r"\$\{[A-Z0-9_]+(=[^}]*)?\}", value) or not re.search(r"https?://|[0-9a-f]{8}-[0-9a-f]{4}-", value), f"{key} carries an endpoint or an identifier"


def test_the_file_names_no_endpoint_tenant_or_secret_outside_its_comments():
    live = "\n".join(l for l in AZURE_YAML.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#"))
    assert not re.search(r"https?://", live)
    assert not re.search(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", live)


def test_every_declared_variable_is_documented_and_read_somewhere():
    documented = (ROOT / "docs" / "architecture" / "ENV-VARS.md").read_text(encoding="utf-8")
    sources = [*(ORCHESTRATOR / "app").rglob("*.py"), *(ROOT / "backend" / "application" / "ai").rglob("*.py")]
    readers = "\n".join(p.read_text(encoding="utf-8") for p in sources if "vendor" not in p.parts)
    for key in env_keys():
        assert f"`{key}`" in documented, f"{key} is not in ENV-VARS.md"
        assert key in readers or key == "PYTHONNOUSERSITE", f"{key} is declared but nothing reads it"


@pytest.mark.parametrize("key, flagged", [
    ("FOUNDRY_PROJECT_ENDPOINT", True), ("AGENT_X_NAME", True), ("AZURE_AI_MODEL_DEPLOYMENT_NAME", True),
    ("SEARCH_API_KEY", True), ("CHANNEL_GATEWAY_AUDIENCE", False), ("TENANT_ID", False), ("LOG_LEVEL", False),
])
def test_the_variable_rule_flags_a_reserved_or_secret_name(key, flagged):
    assert reserved_or_secret(key) is flagged
