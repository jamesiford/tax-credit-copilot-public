"""`scripts/deploy-channel.ps1` waits for the gateway's health instead of trusting the deploy's verdict. [CH-14]

Found live: `az webapp deploy` reported "the site failed to start within 10 minutes" for a gateway that was serving
and ready minutes earlier, and the hook failed the whole `azd up`. The script is dot-sourced with `-NoRun` so the
probe and the clock can be replaced: no network, no sleeping, and the tests assert the retry is bounded.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "deploy-channel.ps1"
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(PWSH is None, reason="PowerShell 7 (pwsh) is not installed")

APP = "app-tcc-channel-abc12345"


@pytest.fixture
def az(tmp_path):
    """A fake `az` whose exit code is `AZ_EXIT`; it uploads nothing."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if os.name == "nt":
        (bin_dir / "az.cmd").write_text("@echo off\r\nexit /b %AZ_EXIT%\r\n", encoding="ascii")
    else:
        shim = bin_dir / "az"
        shim.write_text('#!/bin/sh\nexit "${AZ_EXIT:-0}"\n', encoding="ascii")
        shim.chmod(0o755)
    return bin_dir


def run(az, codes, *, deploy_exit=0, timeout=100, interval=10, base_url="", check=""):
    """Dot-source the script, replace the probe (answers `codes` in turn, then repeats the last) and the clock."""
    program = f"""
. '{SCRIPT}' -NoRun -HealthTimeoutSeconds {timeout} -HealthIntervalSeconds {interval}
$script:now = [DateTime]'2026-01-01T00:00:00Z'; $script:codes = @({','.join(map(str, codes))}); $script:probes = 0; $script:sleeps = 0; $script:urls = @()
function Get-Now {{ $script:now }}
function Wait-Seconds([int]$Seconds) {{ $script:now = $script:now.AddSeconds($Seconds); $script:sleeps++ }}
function Get-HealthStatus([string]$Url) {{ $script:urls += $Url; $c = $script:codes[[Math]::Min($script:probes, $script:codes.Count - 1)]; $script:probes++; $c }}
try {{ Invoke-ChannelDeploy; $ok = 'ok' }} catch {{ $ok = 'failed: ' + $_.Exception.Message }}
"result=$ok"; "probes=$($script:probes)"; "sleeps=$($script:sleeps)"; "urls=$($script:urls -join ',')"
"""
    env = {**os.environ, "PATH": f"{az}{os.pathsep}{os.environ['PATH']}", "AZ_EXIT": str(deploy_exit), "TCC_ENABLE_M365_CHANNEL": "true",
           "CHANNEL_APP_NAME": APP, "AZURE_RESOURCE_GROUP": "rg-test", "CHANNEL_BASE_URL": base_url, "TCC_CHANNEL_HEALTH_CHECK": check}
    done = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", program], capture_output=True, text=True, env=env, timeout=240)
    lines = dict(line.split("=", 1) for line in done.stdout.splitlines() if line.startswith(("result=", "probes=", "sleeps=", "urls=")))
    return lines, done.stdout + done.stderr


def test_a_gateway_that_comes_up_a_little_late_is_waited_for(az):
    got, _ = run(az, [503, 503, 200])
    assert got["result"] == "ok" and got["probes"] == "3" and got["sleeps"] == "2"


def test_a_deploy_that_reports_a_start_failure_for_a_gateway_that_started_is_a_success(az):
    got, output = run(az, [200], deploy_exit=1)
    assert got["result"] == "ok" and got["probes"] == "1"
    assert "reported exit code 1" in output and "treating the deployment as successful" in output


def test_a_gateway_that_never_answers_fails_clearly_and_the_wait_is_bounded(az):
    got, _ = run(az, [0], timeout=100, interval=10)
    assert got["result"].startswith("failed: channel gateway is not healthy")
    assert "answered 0" in got["result"] and "az webapp deploy exit code 0" in got["result"]
    assert int(got["probes"]) <= 100 // 10 + 1, "bounded by the timeout on the (injected) clock"


def test_the_last_status_it_saw_is_in_the_failure(az):
    got, _ = run(az, [503], deploy_exit=1)
    assert "answered 503" in got["result"] and "exit code 1" in got["result"]


def test_the_health_url_is_the_terraform_output_or_the_default_hostname(az):
    assert run(az, [200], base_url="https://gw.example/")[0]["urls"] == "https://gw.example/channel/health"
    assert run(az, [200])[0]["urls"] == f"https://{APP}.azurewebsites.net/channel/health"


def test_with_the_check_off_a_failed_deploy_still_fails_and_nothing_is_probed(az):
    got, _ = run(az, [200], deploy_exit=1, check="off")
    assert got["result"].startswith("failed: az webapp deploy failed with exit code 1") and got["probes"] == "0"
