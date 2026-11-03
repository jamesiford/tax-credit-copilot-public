"""`scripts/publish-m365.ps1`, run for real against a fake `az`. [CH-09]

The script puts an agent in Microsoft 365 and Teams through one REST flow, and the dangerous parts are all
in what it sends: a PATCH that REPLACES the agent endpoint's protocols and schemes (so it must merge, not
replace), a scope that decides who may call the agent, a tenant-wide publish that needs an admin, and a success
message that must never be printed unless a titleId came back. Each is asserted on the requests the script
makes, captured by a fake `az` first on PATH (`tests/publish_shim.py`); nothing reaches Azure, and every
identifier is a placeholder. Needs PowerShell 7, like the azd hook.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from tests import publish_shim as shim

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "publish-m365.ps1"

pytestmark = pytest.mark.skipif(shim.PWSH is None, reason="PowerShell 7 (pwsh) is not installed")


def run(tmp_path, *extra, scenario=None, whatif=False):
    fake = shim.install(tmp_path, scenario)
    arguments = [shim.PWSH, "-NoProfile", "-NonInteractive", "-File", str(SCRIPT), *shim.required_arguments(),
                 "-OutputDir", str(tmp_path / "out"), *extra, *(["-WhatIf"] if whatif else [])]
    done = subprocess.run(arguments, capture_output=True, text=True, env=fake.environment(), timeout=180)
    return fake, done


def said(done) -> str:
    return done.stdout + done.stderr


def sequence(fake) -> list[str]:
    out = []
    for call in fake.calls():
        args = call["args"]
        out.append(f"rest {args[args.index('--method') + 1]}" if args[:1] == ["rest"] else " ".join(args[:2]))
    return out


# --------------------------------------------------------------------------- the flow


def test_the_shared_flow_makes_the_documented_requests_in_order(tmp_path):
    fake, done = run(tmp_path)
    assert done.returncode == 0, said(done)
    assert sequence(fake) == ["provider show", "account show", "account show", "rest get", "rest put", "rest put",
                              "rest patch", "rest post", "rest post"]
    assert "Published version 1.0.0 (titleId T_example-title-id)" in done.stdout
    assert "Your agents" in done.stdout, "the next steps say where the agent appears and how to share it"
    assert "manifest: name=Example agent" in done.stdout and (tmp_path / "out" / "appPackage.zip").exists()


def test_the_bot_is_single_tenant_private_and_points_at_the_agents_activity_route(tmp_path):
    fake, _ = run(tmp_path)
    bot, channel = fake.rest("put")
    assert bot["url"].startswith(f"https://management.azure.com/subscriptions/{shim.SUBSCRIPTION}/resourceGroups/{shim.GROUP}"
                                 f"/providers/Microsoft.BotService/botServices/{shim.BOT}?api-version=2022-09-15")
    body = bot["body"]
    assert (body["kind"], body["location"], body["sku"]) == ("azurebot", "global", {"name": "F0"})
    props = body["properties"]
    assert props["msaAppId"] == shim.CLIENT_ID and props["msaAppTenantId"] == shim.TENANT
    assert props["msaAppType"] == "SingleTenant" and props["publicNetworkAccess"] == "Disabled"
    assert props["endpoint"] == f"{shim.ENDPOINT}/agents/{shim.AGENT}/endpoint/protocols/activityProtocol?api-version=v1"
    assert channel["url"].startswith(f"{bot['url'].split('?')[0]}/channels/MsTeamsChannel?api-version=2021-03-01")
    assert channel["body"] == {"location": "global", "properties": {"channelName": "MsTeamsChannel"}}
    assert bot["resource"] is None, "ARM calls use az's own management token"


def test_the_patch_merges_with_what_the_endpoint_already_has_and_never_replaces_it(tmp_path):
    fake, _ = run(tmp_path)
    (patch,) = fake.rest("patch")
    assert patch["headers"] == "Content-Type=application/merge-patch+json" and patch["resource"] == "https://ai.azure.com"
    endpoint = patch["body"]["agent_endpoint"]
    assert set(patch["body"]) == {"agent_endpoint"} and set(endpoint) == {"protocol_configuration", "authorization_schemes"}
    assert endpoint["protocol_configuration"] == {"responses": {}, "invocations": {"keep": "me"},
                                                  "activity": {"enable_m365_public_endpoint": True}}
    assert endpoint["authorization_schemes"] == [{"type": "AzureRbac"}, {"type": "BotServiceRbac"}], \
        "AzureRbac is kept; the other Bot Service scheme is swapped for the scope's"


def test_an_activity_setting_already_there_is_kept_and_an_unknown_scheme_survives(tmp_path):
    scenario = shim.default_scenario()
    agent = shim.default_agent()
    agent["agent_endpoint"]["protocol_configuration"] = {"a2a": {}, "activity": {"something_else": 1}}
    agent["agent_endpoint"]["authorization_schemes"] = [{"type": "Entra"}, {"type": "AzureRbac"}, {"type": "BotServiceRbac"}]
    shim.route(scenario, "get", {"stdout": agent})
    fake, done = run(tmp_path, scenario=scenario)
    endpoint = fake.rest("patch")[0]["body"]["agent_endpoint"]
    assert endpoint["protocol_configuration"] == {"a2a": {}, "activity": {"something_else": 1, "enable_m365_public_endpoint": True}}
    assert endpoint["authorization_schemes"] == [{"type": "Entra"}, {"type": "AzureRbac"}, {"type": "BotServiceRbac"}], done.stdout


def test_an_endpoint_with_nothing_configured_gets_responses_and_activity_and_just_the_bot_scheme(tmp_path):
    scenario = shim.default_scenario()
    shim.route(scenario, "get", {"stdout": {"name": shim.AGENT, "instance_identity": {"client_id": shim.CLIENT_ID}}})
    fake, _ = run(tmp_path, scenario=scenario)
    endpoint = fake.rest("patch")[0]["body"]["agent_endpoint"]
    assert endpoint["protocol_configuration"] == {"responses": {}, "activity": {"enable_m365_public_endpoint": True}}
    assert endpoint["authorization_schemes"] == [{"type": "BotServiceRbac"}]


def test_the_publish_body_carries_the_scope_the_version_and_only_the_documented_fields(tmp_path):
    fake, _ = run(tmp_path)
    (publish,) = [r for r in fake.rest("post") if r["url"].split("?")[0].endswith("/microsoft365/publish")]
    assert publish["resource"] == "https://ai.azure.com"
    body = publish["body"]
    assert set(body) == {"agentDisplayName", "botServiceArmId", "publishScope", "publishAsAutopilot", "appVersion", "shortDescription",
                         "fullDescription", "developerName", "developerWebsiteUrl", "privacyUrl", "termsOfUseUrl"}
    assert body["publishScope"] == "Shared" and body["publishAsAutopilot"] is False and body["appVersion"] == "1.0.0"
    assert body["botServiceArmId"] == (f"/subscriptions/{shim.SUBSCRIPTION}/resourceGroups/{shim.GROUP}"
                                       f"/providers/Microsoft.BotService/botServices/{shim.BOT}")
    for url in (body["developerWebsiteUrl"], body["privacyUrl"], body["termsOfUseUrl"]):
        assert url.startswith("https://")


def test_the_package_is_downloaded_with_the_same_body_it_published(tmp_path):
    fake, _ = run(tmp_path)
    publish, download = [r for r in fake.rest("post")]
    assert download["url"].split("?")[0].endswith("/microsoft365/zip") and download["body"] == publish["body"]
    assert "--output-file" in download["args"]


# -------------------------------------------------------------------------- the scope


def test_tenant_scope_without_the_confirmation_stops_before_any_call(tmp_path):
    fake, done = run(tmp_path, "-PublishScope", "Tenant")
    assert done.returncode != 0 and "-ConfirmTenantPublish" in said(done) and "admin" in said(done)
    assert fake.calls() == []


def test_tenant_scope_confirmed_uses_the_tenant_scheme_and_says_an_admin_must_approve(tmp_path):
    fake, done = run(tmp_path, "-PublishScope", "Tenant", "-ConfirmTenantPublish")
    assert done.returncode == 0, said(done)
    endpoint = fake.rest("patch")[0]["body"]["agent_endpoint"]
    assert endpoint["authorization_schemes"] == [{"type": "AzureRbac"}, {"type": "BotServiceTenant"}]
    assert [r["body"]["publishScope"] for r in fake.rest("post")] == ["Tenant", "Tenant"]
    assert "admin approval" in done.stdout and "admin.cloud.microsoft" in done.stdout


def test_a_public_project_skips_the_endpoint_patch(tmp_path):
    fake, done = run(tmp_path, "-EnablePrivateNetworkRoute:False")
    assert done.returncode == 0, said(done)
    assert fake.rest("patch") == [] and "Skipping the endpoint PATCH" in done.stdout


# ---------------------------------------------------------------------------- guards


def test_an_unregistered_provider_prints_the_command_and_stops_and_never_registers_one(tmp_path):
    scenario = shim.default_scenario()
    scenario["provider"] = "NotRegistered"
    fake, done = run(tmp_path, scenario=scenario)
    assert done.returncode == 1
    assert "az provider register --namespace Microsoft.BotService" in done.stdout
    assert sequence(fake) == ["provider show"], "nothing else was called, and nothing was registered"


def test_an_existing_version_is_raised_by_a_patch_and_the_package_uses_the_one_that_worked(tmp_path):
    scenario = shim.default_scenario()
    shim.route(scenario, "publish", {"exit": 1, "stderr": "Version 1.0.0 already exists for this agent."},
               {"exit": 1, "stderr": "Version 1.0.1 already exists for this agent."}, {"stdout": {"titleId": "T_example-title-id"}})
    fake, done = run(tmp_path, scenario=scenario)
    assert done.returncode == 0, said(done)
    posts = fake.rest("post")
    assert [p["body"]["appVersion"] for p in posts] == ["1.0.0", "1.0.1", "1.0.2", "1.0.2"]
    assert "Published version 1.0.2" in done.stdout


def test_a_publish_that_returns_no_title_id_is_not_reported_as_published(tmp_path):
    scenario = shim.default_scenario()
    shim.route(scenario, "publish", {"stdout": {"status": "accepted"}})
    fake, done = run(tmp_path, scenario=scenario)
    assert done.returncode != 0 and "NOT reported as published" in said(done)
    assert "Published version" not in done.stdout
    assert not [r for r in fake.rest("post") if r["url"].split("?")[0].endswith("/zip")]


def test_any_other_publish_failure_fails_with_the_services_message(tmp_path):
    scenario = shim.default_scenario()
    shim.route(scenario, "publish", {"exit": 1, "stderr": "Forbidden: caller lacks agent write permission"})
    _, done = run(tmp_path, scenario=scenario)
    assert done.returncode != 0 and "agent write permission" in said(done) and "Published version" not in done.stdout


def test_an_agent_with_no_identity_stops_before_creating_anything(tmp_path):
    scenario = shim.default_scenario()
    shim.route(scenario, "get", {"stdout": {"name": shim.AGENT}})
    fake, done = run(tmp_path, scenario=scenario)
    assert done.returncode != 0 and "instance_identity.client_id" in said(done)
    assert fake.rest("put") == [] and fake.rest("patch") == []


@pytest.mark.parametrize("bad", [["-ProjectEndpoint", "http://insecure.example/api/projects/p"], ["-AppVersion", "one"],
                                 ["-PrivacyUrl", "http://insecure.example/privacy"]])
def test_bad_parameters_stop_before_any_request(tmp_path, bad):
    fake = shim.install(tmp_path)
    arguments = [shim.PWSH, "-NoProfile", "-NonInteractive", "-File", str(SCRIPT), *shim.required_arguments(), *bad]
    done = subprocess.run(arguments, capture_output=True, text=True, env=fake.environment(), timeout=120)
    assert done.returncode != 0 and fake.rest("put") == [] and fake.rest("post") == []


# --------------------------------------------------------------------------- WhatIf


def test_whatif_reads_but_changes_nothing_and_prints_what_it_would_send(tmp_path):
    fake, done = run(tmp_path, whatif=True)
    assert done.returncode == 0, said(done)
    assert fake.rest("put") == [] and fake.rest("patch") == [] and fake.rest("post") == []
    assert len(fake.rest("get")) == 1, "the agent is read so the merge can be shown"
    out = done.stdout
    for fragment in ("PUT https://management.azure.com", "PATCH ", "POST ", "BotServiceRbac", "msaAppType", "appVersion",
                     "WhatIf: nothing was published."):
        assert fragment in out, fragment
    assert "Published version" not in out and not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------- hygiene


def test_az_obtains_every_token_and_the_script_holds_none(tmp_path):
    fake, _ = run(tmp_path)
    foundry = [c for c in fake.calls() if c["args"][:1] == ["rest"] and "services.ai.azure.com" in " ".join(c["args"])]
    assert foundry and all("--resource" in c["args"] and "https://ai.azure.com" in c["args"] for c in foundry)
    assert not re.search(r"bearer|get-access-token|authorization:", fake.log.read_text(encoding="utf-8"), re.IGNORECASE)
    source = SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"Bearer |Authorization:|accessToken|ConvertTo-SecureString|password\s*=|client_secret", source, re.IGNORECASE)
    assert "bicep" not in source.lower().replace("no bicep", "")


def test_the_script_is_a_documented_pwsh7_script_with_whatif_and_registers_nothing():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "#Requires -Version 7.0" in source and "SupportsShouldProcess" in source
    for parameter in ("ProjectEndpoint", "AgentName", "ResourceGroup", "BotName", "DisplayName", "ShortDescription", "FullDescription",
                      "AppVersion", "PublishScope", "EnablePrivateNetworkRoute", "OutputDir", "ConfirmTenantPublish"):
        assert f"${parameter}" in source
    assert "'provider', 'register'" not in source and not re.search(r"&\s+az\s+provider\s+register", source)


def test_the_saved_whatif_transcript_exists_and_holds_only_placeholders():
    transcript = REPO / "docs" / "m365-channel" / "evidence" / "publish-whatif.txt"
    text = transcript.read_text(encoding="utf-8")
    assert "What if" in text or "WhatIf" in text
    guids = set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text))
    assert guids <= {shim.TENANT, shim.SUBSCRIPTION, shim.CLIENT_ID}, f"a real-looking identifier: {guids - {shim.TENANT, shim.SUBSCRIPTION, shim.CLIENT_ID}}"
    assert "example" in text and not re.search(r"https://(?!account-example|github\.com/jamesiford|management\.azure\.com|admin\.cloud)", text)
