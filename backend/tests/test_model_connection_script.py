"""`scripts/create-model-connection.ps1`: safe to read, safe to dry-run. [AI-03]

The script creates a Foundry model connection through an ARM deployment and must
never put a secret on a command line or in the repository. These tests run only
its `-WhatIf` path and its argument checks — nothing touches Azure — and hold the
properties that matter: the dry run fetches no secret, prints no secret, names the
exact command, and the secret reaches the template only through an environment
variable read by a generated .bicepparam.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "create-model-connection.ps1"
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(PWSH is None, reason="PowerShell 7 (pwsh) is not installed; the script is PowerShell-only")


def run(tmp_path, arguments: str):
    template = tmp_path / "modelgateway.bicep"
    template.write_text("param connectionName string\n", encoding="utf-8")
    command = f"& '{SCRIPT}' -ResourceGroup rg-test -TemplateFile '{template}' {arguments}"
    return subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, text=True, timeout=120)


def test_the_dry_run_names_the_command_fetches_no_secret_and_prints_none(tmp_path):
    result = run(tmp_path, "-Parameter @{ connectionName = 'corp-gw'; targetUrl = 'https://gateway.example.com'; models = @('m1','m2') } "
                           "-KeyVaultName kv-test -SecretName gw-key -WhatIf")
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "az deployment group create --resource-group rg-test --name tcc-model-connection --parameters" in out
    assert "param connectionName = 'corp-gw'" in out and "param models = ['m1', 'm2']" in out
    assert "param apiKey = readEnvironmentVariable('TCC_GATEWAY_SECRET')" in out
    assert "Key Vault kv-test/gw-key" in out and "az keyvault" not in out


def test_the_secret_cannot_be_passed_as_a_template_parameter(tmp_path):
    result = run(tmp_path, "-Parameter @{ connectionName = 'c'; apiKey = 'hunter2' } -WhatIf")
    assert result.returncode != 0 and "Do not pass the secret" in (result.stderr + result.stdout)
    assert "hunter2" not in result.stdout


def test_a_missing_template_is_an_error(tmp_path):
    command = f"& '{SCRIPT}' -ResourceGroup rg -TemplateFile 'C:/no/such.bicep' -Parameter @{{a='b'}} -WhatIf"
    result = subprocess.run([PWSH, "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=120)
    assert result.returncode != 0 and "TemplateFile not found" in (result.stderr + result.stdout)


def test_the_script_never_places_a_secret_on_a_command_line_or_in_the_repo():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "readEnvironmentVariable" in text and "Read-Host -Prompt" in text and "-AsSecureString" in text
    assert "'--parameters', $parameterFile" in text, "the template reads parameters from a file; the secret is not an argument"
    assert "--query', 'value'" in text, "the Key Vault value is read, not echoed"
    assert "Remove-Item -LiteralPath $parameterFile" in text and "ZeroFreeBSTR" in text
