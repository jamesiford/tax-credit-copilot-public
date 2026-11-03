"""`scripts/deploy-channel.ps1`, run for real against a stubbed `az`. [CH-07b]

The script is what replaces an azd service, so its two promises are tested by running it:
with the toggle off it does nothing and exits 0 (the default `azd up` is unchanged), and
with it on it builds the backend package and calls `az webapp deploy` for exactly the app
Terraform named. `az` is a shim first on PATH that records its arguments, so nothing
reaches Azure. Needs PowerShell 7, as the azd hook itself does.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "deploy-channel.ps1"
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(PWSH is None, reason="PowerShell 7 (pwsh) is not installed")

APP = "app-tcc-channel-abc12345"
GROUP = "rg-tcc-test"


@pytest.fixture
def shim(tmp_path):
    """A fake `az` on PATH. It logs its arguments and copies the zip it was asked to deploy."""
    log, bin_dir = tmp_path / "az.log", tmp_path / "bin"
    bin_dir.mkdir()
    copy = tmp_path / "deployed.zip"
    if os.name == "nt":
        (bin_dir / "az.cmd").write_text(
            f'@echo off\r\necho %*>>"{log}"\r\n'
            ':loop\r\nif "%~1"=="" goto done\r\nif "%~1"=="--src-path" copy /y "%~2" "' + str(copy) + '" >nul\r\n'
            "shift\r\ngoto loop\r\n:done\r\nexit /b 0\r\n", encoding="ascii")
    else:
        script = bin_dir / "az"
        script.write_text(
            f'#!/bin/sh\necho "$@" >> "{log}"\nwhile [ $# -gt 0 ]; do\n'
            f'  [ "$1" = "--src-path" ] && cp "$2" "{copy}"\n  shift\ndone\nexit 0\n', encoding="ascii")
        script.chmod(0o755)
    return type("Shim", (), {"dir": bin_dir, "log": log, "zip": copy})


def run(shim, *args, **env):
    environment = {**os.environ, "PATH": f"{shim.dir}{os.pathsep}{os.environ['PATH']}",
                   "CHANNEL_APP_NAME": "", "AZURE_RESOURCE_GROUP": "", "TCC_ENABLE_M365_CHANNEL": "", **env}
    return subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-File", str(SCRIPT), *args],
        capture_output=True, text=True, env=environment, timeout=180,
    )


def az_calls(shim) -> list[str]:
    return shim.log.read_text(encoding="utf-8").splitlines() if shim.log.exists() else []


@pytest.mark.parametrize("flag", ["", "false", "False", "0", "yes"])
def test_with_the_toggle_off_it_exits_zero_calls_nothing_and_is_not_alarming(shim, flag):
    done = run(shim, TCC_ENABLE_M365_CHANNEL=flag)
    assert done.returncode == 0 and done.stderr == ""
    assert "not enabled" in done.stdout and "error" not in done.stdout.lower()
    assert az_calls(shim) == []


def test_off_needs_no_terraform_output_at_all(shim):
    assert run(shim, TCC_ENABLE_M365_CHANNEL="false", CHANNEL_APP_NAME="null").returncode == 0


def test_on_packages_backend_and_deploys_it_to_the_named_app(shim):
    done = run(shim, TCC_ENABLE_M365_CHANNEL="true", CHANNEL_APP_NAME=APP, AZURE_RESOURCE_GROUP=GROUP)
    assert done.returncode == 0, done.stdout + done.stderr
    [call] = az_calls(shim)
    assert call.startswith("webapp deploy") and f"-g {GROUP}" in call and f"-n {APP}" in call
    assert "--type zip" in call and "--async false" in call
    with zipfile.ZipFile(shim.zip) as archive:
        names = set(archive.namelist())
    assert {"startup-channel.sh", "channel/main.py", "main.py"} <= names
    assert not any(n.startswith(("tests/", ".env")) for n in names)


def test_on_is_idempotent_it_deploys_the_same_package_again(shim):
    for _ in range(2):
        assert run(shim, TCC_ENABLE_M365_CHANNEL="true", CHANNEL_APP_NAME=APP, AZURE_RESOURCE_GROUP=GROUP).returncode == 0
    first, second = az_calls(shim)
    assert first.split("--src-path")[0] == second.split("--src-path")[0]


def test_whatif_prints_the_plan_and_changes_nothing(shim):
    done = run(shim, "-WhatIf", TCC_ENABLE_M365_CHANNEL="true", CHANNEL_APP_NAME=APP, AZURE_RESOURCE_GROUP=GROUP)
    assert done.returncode == 0
    assert APP in done.stdout + done.stderr and "channel gateway" in done.stdout + done.stderr
    assert az_calls(shim) == [] and not shim.zip.exists()


@pytest.mark.parametrize("missing", ["CHANNEL_APP_NAME", "AZURE_RESOURCE_GROUP"])
def test_on_without_a_terraform_output_fails_naming_it(shim, missing):
    env = {"TCC_ENABLE_M365_CHANNEL": "true", "CHANNEL_APP_NAME": APP, "AZURE_RESOURCE_GROUP": GROUP, missing: "null"}
    done = run(shim, **env)
    assert done.returncode != 0 and missing in done.stderr + done.stdout
    assert az_calls(shim) == []


def test_a_failing_deploy_fails_the_hook_and_leaves_no_temp_zip(shim, tmp_path):
    marker = tmp_path / "tmp"
    marker.mkdir()
    if os.name == "nt":
        (shim.dir / "az.cmd").write_text("@echo off\r\nexit /b 3\r\n", encoding="ascii")
    else:
        (shim.dir / "az").write_text("#!/bin/sh\nexit 3\n", encoding="ascii")
    done = run(shim, TCC_ENABLE_M365_CHANNEL="true", CHANNEL_APP_NAME=APP, AZURE_RESOURCE_GROUP=GROUP, TMP=str(marker), TMPDIR=str(marker))
    assert done.returncode != 0 and "az webapp deploy failed" in done.stderr + done.stdout
    assert list(marker.glob("tcc-channel-*.zip")) == []


def test_the_script_is_wired_into_azd_and_ci_behind_the_toggle():
    azure = (REPO / "azure.yaml").read_text(encoding="utf-8")
    assert azure.count("deploy-channel.ps1") == 2 and "postdeploy:" in azure
    workflow = (REPO / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    step = workflow[workflow.index("Zip deploy the channel gateway"):]
    assert "env.CHANNEL_APP_NAME != ''" in step.split("run:")[0] and "deploy-channel.ps1" in step.split("\n\n")[0]
    assert "package-app.py" in SCRIPT.read_text(encoding="utf-8")
