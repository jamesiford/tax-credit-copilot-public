"""The channel gateway's deployment wiring, outside Terraform. [CH-07, CH-07b]

What `infra/tests/channel.tftest.hcl` cannot see: azd has no `channel` service (it cannot
make one conditional), the same `backend/` package carries the gateway, postprovision
grants the gateway identity at object level only when the channel is on, `deploy.yml`
stays dispatch-only, and every setting the gateway reads is documented where an
operator looks.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"


def read(*parts: str) -> str:
    return REPO.joinpath(*parts).read_text(encoding="utf-8")


def service_names() -> list[str]:
    """The keys directly under `services:` in azure.yaml (no YAML dependency)."""
    text = read("azure.yaml")
    block = text[text.index("\nservices:"):]
    return re.findall(r"^  ([A-Za-z][\w-]*):\s*$", block, re.MULTILINE)


def service_block(name: str) -> str:
    text = read("azure.yaml")
    match = re.search(rf"^  {name}:\n((?:    .*\n|\s*#.*\n)+)", text, re.MULTILINE)
    assert match, f"azure.yaml has no service {name!r}"
    return match.group(1)


def test_azd_has_exactly_the_api_and_web_services_so_a_default_azd_up_is_unchanged():
    assert service_names() == ["api", "web"]
    assert "project: ./backend" in service_block("api") and "language: python" in service_block("api")
    assert "project: ./frontend" in service_block("web")


def test_nothing_in_infra_or_the_hooks_needs_the_channel_when_the_toggle_is_off():
    terraform = "".join(
        p.read_text(encoding="utf-8") for p in (REPO / "infra").rglob("*.tf") if ".terraform" not in p.parts)
    assert not re.search(r'"azd-service-name"\s*=\s*"channel"', terraform)
    azure = read("azure.yaml")
    hooks = azure[azure.index("\nhooks:"): azure.index("\nservices:")]
    assert "deploy-channel.ps1" in hooks and "postdeploy:" in hooks
    # The only hook that names the channel is the one that exits 0 when it is off.
    assert "postprovision.ps1" in hooks and hooks.count("deploy-channel.ps1") == 2


def test_the_module_starts_the_gateway_with_its_own_script():
    assert "sh startup-channel.sh" in read("infra", "modules", "channel", "main.tf")


def test_the_channel_package_is_the_backend_package_and_carries_the_gateway(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("package_app", REPO / "scripts" / "package-app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    included = set(module.package(BACKEND, tmp_path / "channel.zip"))
    assert {"startup-channel.sh", "channel/main.py", "channel/app.py", "application/channel_wiring.py",
            "application/capabilities/catalog.py", "startup.sh"} <= included
    assert not any(name.startswith(("tests/", ".env")) for name in included)
    with zipfile.ZipFile(tmp_path / "channel.zip") as archive:
        assert "startup-channel.sh" in archive.namelist()


def test_the_startup_script_runs_the_gateway_with_one_worker_and_unix_line_endings():
    script = (BACKEND / "startup-channel.sh").read_bytes()
    assert b"\r" not in script
    text = script.decode("utf-8")
    assert "channel.main:app" in text and "${WEB_CONCURRENCY:-1}" in text and "set -e" in text


def test_postprovision_grants_the_gateway_only_when_the_channel_is_on_and_only_at_object_level():
    script = read("scripts", "postprovision.ps1")
    assert "GATEWAY_IDENTITY_NAME" in script and "--profile gateway" in script
    gated = script[script.index("if (-not [string]::IsNullOrWhiteSpace($env:GATEWAY_IDENTITY_NAME)"): script.rindex("seed-operational-store")]
    assert "grant-warehouse-sql.py" in gated and "--profile gateway" in gated
    sql = (REPO / "scripts" / "grant-warehouse-sql.py").read_text(encoding="utf-8")
    assert "ON OBJECT::" in sql and "INSERT, SELECT" in sql


def test_the_gateway_grant_is_idempotent_object_level_and_names_no_schema():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("grant_warehouse_sql", REPO / "scripts" / "grant-warehouse-sql.py")
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        grant = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(grant)
    finally:
        sys.path.pop(0)
    statements = grant.statements_for("gateway", "id-tcc-channel-abc", "tcc_gold", "tcc_ops")
    assert statements == ["GRANT INSERT, SELECT ON OBJECT::tcc_ops.channel_audit TO [id-tcc-channel-abc];"]
    assert statements == grant.statements_for("gateway", "id-tcc-channel-abc", "tcc_gold", "tcc_ops")
    assert not any("SCHEMA::" in s or "UPDATE" in s or "DELETE" in s for s in statements)


def test_deploy_yml_stays_dispatch_only_and_deploys_the_channel_only_when_it_exists():
    text = read(".github", "workflows", "deploy.yml")
    trigger = text[text.index("\non:"): text.index("\njobs:")]
    assert "workflow_dispatch:" in trigger
    assert not re.search(r"^\s+(push|pull_request|pull_request_target|schedule|workflow_run|release):", trigger, re.MULTILINE)
    assert "CHANNEL_APP_NAME" in text and "GATEWAY_IDENTITY_NAME" in text
    deploy_step = text[text.index("Zip deploy the channel gateway"):]
    assert "env.CHANNEL_APP_NAME != ''" in deploy_step.split("run:")[0]


def test_the_azd_environment_maps_the_scalar_channel_variables_with_safe_defaults():
    mapping = json.loads(read("infra", "main.tfvars.json"))
    assert mapping["enable_m365_channel"] == "${TCC_ENABLE_M365_CHANNEL=false}"
    assert mapping["channel_writer_source"] == "${TCC_CHANNEL_WRITER_SOURCE=allowlist}"
    assert {"channel_gateway_audience", "channel_writer_group_id"} <= set(mapping)


def test_every_new_terraform_variable_is_off_or_empty_by_default():
    variables = read("infra", "variables.tf")
    for name, default in (("enable_m365_channel", "false"), ("channel_gateway_audience", '""'),
                          ("channel_allowed_caller_app_ids", "[]"), ("channel_writer_source", '"allowlist"'),
                          ("channel_writer_group_id", '""'), ("channel_allowed_ip_ranges", "[]")):
        block = re.search(rf'variable "{name}" \{{(.*?)\n\}}', variables, re.DOTALL)
        assert block and re.search(rf"default\s*=\s*{re.escape(default)}", block.group(1)), name


def test_the_api_gets_only_the_writer_settings_for_the_channel_and_only_with_it_on():
    """The API enforces the writer entitlement itself, so it reads the gateway's two writer settings. [CH-13]

    Found live: with the gateway on `either` and the API left on its `allowlist` default, a group-only
    writer passed the gateway and was refused by the API. Nothing else of the channel reaches the API.
    """
    main = read("infra", "main.tf")
    api_settings = main[main.index("api_app_settings"): main.index("web_app_settings")]
    assert set(re.findall(r"CHANNEL_[A-Z_]+", api_settings)) == {"CHANNEL_WRITER_SOURCE", "CHANNEL_WRITER_GROUP_ID"}
    assert "TCC.Agent" not in api_settings
    assert api_settings.index("var.enable_m365_channel") < api_settings.index("CHANNEL_WRITER_SOURCE")


# ------------------------------------------------------------------ the docs


def gateway_env_names() -> set[str]:
    source = (BACKEND / "channel" / "config.py").read_text(encoding="utf-8")
    names = set(re.findall(r'_(?:text|flag)\(env, "([A-Z_]+)"\)', source)) | set(re.findall(r'_number\(env, "([A-Z_]+)"', source))
    names |= set(re.findall(r'"(TENANT_ID|GATEWAY_AUDIENCE|API_BASE_URL|API_AUDIENCE)"', source))
    names |= {"CHANNEL_STORE", "CHANNEL_WRITER_SOURCE", "CHANNEL_WRITER_GROUP_ID", "WEB_CONCURRENCY"}
    return names


@pytest.mark.parametrize("name", sorted(gateway_env_names()))
def test_every_gateway_setting_is_documented_in_the_gateway_section(name):
    text = read("docs", "architecture", "ENV-VARS.md")
    section = text[text.index("## 9a. Channel gateway"): text.index("## 10. Web app")]
    assert f"`{name}`" in section, f"{name} is read by the gateway but missing from ENV-VARS.md section 9a"


def test_the_module_settings_are_all_documented():
    module = read("infra", "modules", "channel", "main.tf")
    block = module[module.index("plain_settings = merge("): module.index("resource \"azurerm_user_assigned_identity\"")]
    names = set(re.findall(r"^\s+([A-Z][A-Z_]+)\s+=", block, re.MULTILINE)) | {"CHANNEL_ALLOWED_CALLER_APP_IDS", "CHANNEL_WRITER_GROUP_ID"}
    text = read("docs", "architecture", "ENV-VARS.md")
    section = text[text.index("## 9a. Channel gateway"): text.index("## 10. Web app")]
    missing = sorted(n for n in names if f"`{n}`" not in section and n not in section)
    assert not missing, missing


def test_the_connectivity_matrix_names_every_channel_path_and_the_c4_model_the_gateway():
    matrix = read("docs", "architecture", "CONNECTIVITY-MATRIX.md")
    for row in ("CH1", "CH2", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8", "CH9"):
        assert f"| {row} |" in matrix
    model = json.loads(read("docs", "architecture", "c4", "model.json"))
    containers = {n["id"] for n in model["views"]["containers"]["nodes"]}
    assert {"c-gateway", "c-orch", "c-m365"} <= containers
    edges = {(e["from"], e["to"]) for e in model["views"]["containers"]["edges"]}
    assert {("c-orch", "c-gateway"), ("c-m365", "c-gateway"), ("c-gateway", "c-api"), ("c-gateway", "c-wh")} <= edges
    assert "x-m365" in {n["id"] for n in model["views"]["context"]["nodes"]}


def test_no_raster_image_was_added_to_the_architecture_docs():
    images = [p for p in (REPO / "docs" / "architecture").rglob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".bmp")]
    assert images == []
