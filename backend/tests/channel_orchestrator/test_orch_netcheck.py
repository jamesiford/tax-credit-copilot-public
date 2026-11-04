"""`/netcheck` and `/modelprobe`: gated diagnostics that never carry a credential. [CH-14]"""
from __future__ import annotations

import asyncio
import json

import pytest
from app.core.modelprobe import run_modelprobe
from app.core.netcheck import NetProbe, account_hosts, check_host, classify, environment_report, run_netcheck
from test_orch_host import context, orchestrator, run

PROJECT = "https://aif-example.services.ai.azure.com/api/projects/proj-example"


class FakeProbe(NetProbe):
    """No network: names map to canned addresses, and chosen hosts fail at a chosen step."""

    def __init__(self, addresses=None, tcp_fail=(), tls_fail=(), http_fail=()):
        self.addresses, self.tcp_fail, self.tls_fail, self.http_fail = addresses or {}, set(tcp_fail), set(tls_fail), set(http_fail)

    def resolve(self, host):
        if host not in self.addresses:
            raise OSError("Name or service not known")
        return self.addresses[host]

    def connect(self, address, timeout):
        if address in self.tcp_fail:
            raise TimeoutError("timed out")

    def tls_and_get(self, host, address, timeout):
        if host in self.tls_fail:
            raise OSError("handshake failure")
        return 404

    def httpx_get(self, url, timeout):
        if any(h in url for h in self.http_fail):
            raise OSError("All connection attempts failed")
        return 401


def test_addresses_are_classified():
    assert [classify(a) for a in ("10.1.2.3", "20.1.2.3", "127.0.0.1", "169.254.1.1", "fd00::1")] == [
        "private", "public", "loopback", "link-local", "private"]


def test_a_name_that_does_not_resolve_stops_at_resolve():
    report = check_host(FakeProbe(), "nowhere.example")
    assert report["resolve"].startswith("OSError") and "tcp" not in report


def test_a_private_address_that_cannot_be_connected_is_reported_as_private_and_failed():
    probe = FakeProbe({"acct.example": ["10.0.0.4"]}, tcp_fail={"10.0.0.4"})
    report = check_host(probe, "acct.example")
    assert report["resolved"] == [{"address": "10.0.0.4", "kind": "private"}]
    assert report["tcp"]["ok"] is False and "TimeoutError" in report["tcp"]["error"] and "tls_get_status" not in report


def test_a_reachable_host_reports_tls_and_the_httpx_result_separately():
    probe = FakeProbe({"acct.example": ["20.1.1.1"]}, http_fail={"acct.example"})
    report = check_host(probe, "acct.example", httpx_path="/openai/v1/models")
    assert report["tcp"]["ok"] and report["tls_get_status"] == 404
    assert report["httpx_status"].startswith("OSError"), "the plain socket worked while the model client's transport did not"


def test_the_accounts_other_names_are_derived_from_the_project_endpoint():
    assert [h for h, _ in account_hosts(PROJECT)] == [
        "aif-example.services.ai.azure.com", "aif-example.openai.azure.com", "aif-example.cognitiveservices.azure.com"]
    assert account_hosts("not a url") == []


def test_the_environment_report_gives_names_and_only_the_listed_values():
    env = {"FOUNDRY_MODEL": "m", "FOUNDRY_TOKEN_THING": "must-not-appear", "AI_PROVIDER_CHAIN": "foundry", "HTTPS_PROXY": "http://user:pw@proxy:3128",
           "UNRELATED": "x", "CHANNEL_GATEWAY_AUDIENCE": "api://not-shown"}
    report = environment_report(env)
    assert "FOUNDRY_TOKEN_THING" in report["names"] and "UNRELATED" not in report["names"]
    assert report["values"] == {"FOUNDRY_MODEL": "m", "AI_PROVIDER_CHAIN": "foundry"}
    assert report["proxy_variables_set"] == ["HTTPS_PROXY"]
    text = json.dumps(report)
    assert "must-not-appear" not in text and "pw@" not in text and "api://not-shown" not in text


def test_the_full_report_covers_every_target_and_leaks_nothing():
    probe = FakeProbe({h: ["20.0.0.1"] for h in (
        "aif-example.services.ai.azure.com", "aif-example.openai.azure.com", "aif-example.cognitiveservices.azure.com",
        "gw.example", "login.microsoftonline.com", "www.microsoft.com")})
    text = run_netcheck(env={"AI_PROVIDER_CHAIN": "foundry", "SECRET_TOKEN": "s3cret"}, project_endpoint=PROJECT,
                        gateway_url="https://gw.example", providers=("foundry",), probe=probe)
    report = json.loads(text)
    assert [t["host"] for t in report["targets"]][-3:] == ["gw.example", "login.microsoftonline.com", "www.microsoft.com"]
    assert report["providers"] == ["foundry"] and "s3cret" not in text and "Bearer" not in text


def test_modelprobe_reports_success_without_the_reply():
    out = json.loads(asyncio.run(run_modelprobe(
        {"FOUNDRY_PROJECT_ENDPOINT": PROJECT, "FOUNDRY_MODEL": "gpt-x"}, call=lambda e, m: {"base_url": "https://h/p/openai/v1/", "reply_chars": 2})))
    assert out["ok"] is True and out["reply_chars"] == 2 and out["model"] == "gpt-x" and out["project_endpoint_host"] == "aif-example.services.ai.azure.com"


def test_modelprobe_reports_a_failure_by_type_and_cause_and_does_not_raise():
    def boom(endpoint, model):
        try:
            raise ConnectionError("refused")
        except ConnectionError as cause:
            raise RuntimeError("Connection error.") from cause

    out = json.loads(asyncio.run(run_modelprobe({"FOUNDRY_PROJECT_ENDPOINT": PROJECT, "AZURE_AI_MODEL_DEPLOYMENT_NAME": "m"}, call=boom)))
    assert out["ok"] is False and out["error"].startswith("RuntimeError") and out["cause"].startswith("ConnectionError")


def test_modelprobe_without_configuration_says_so():
    assert json.loads(asyncio.run(run_modelprobe({})))["ok"] is False


@pytest.mark.parametrize("command", ["/netcheck", "/modelprobe"])
def test_the_commands_are_not_offered_without_the_debug_flag(command):
    orch, rig = orchestrator([{"text": "never"}])
    assert not orch.settings.debug_whoami
    text = run(orch, context(), command)
    assert "targets" not in text and '"ok"' not in text


def test_with_the_flag_a_command_is_answered_by_the_diagnostics_and_runs_no_tool(monkeypatch):
    orch, rig = orchestrator([{"text": "never"}], CHANNEL_DEBUG_WHOAMI="true")
    import app.host as host

    monkeypatch.setattr(host, "run_netcheck", lambda **kw: json.dumps({"targets": [], "providers": kw["providers"]}))

    async def fake_probe(env):
        return json.dumps({"ok": True})

    monkeypatch.setattr(host, "run_modelprobe", fake_probe)
    assert json.loads(run(orch, context(), "/netcheck"))["providers"] == list(orch.settings.ai.provider_chain)
    assert json.loads(run(orch, context(), "/modelprobe")) == {"ok": True}
    assert rig.gateway.calls == [] and rig.chat.seen == []
