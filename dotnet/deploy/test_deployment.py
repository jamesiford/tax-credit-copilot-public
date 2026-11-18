"""Fast tests for deployment-owned inclusion, integrity and fail-closed boundaries."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import package_zip
import stage


def temporary():
    root = stage.DEPLOY / ".artifacts" / "tests"
    root.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=root)


class DeploymentTests(unittest.TestCase):
    def test_only_named_public_payroll_is_staged(self):
        self.assertTrue(stage.is_resource("backend/data/payroll.csv"))
        self.assertTrue(stage.is_resource("backend/data/payroll_pay_periods.csv"))
        for name in ("backend/data/payroll/One.csv", "backend/.env", "contract/seed/accounts.json",
                     "backend/data/payroll.db", "backend/data/token.json"):
            self.assertFalse(stage.is_resource(name), name)

    def test_rules_ingestion_and_schema_remain_complete(self):
        for name in ("backend/rules/ga_jtc/2023.json", "backend/rules/lookups/tier-map.json",
                     "backend/data/rules_ingested/ga_jtc.json",
                     "docs/data/schema/tcc-schema.sqlserver.sql",
                     "docs/data/schema/migrations/005.sql"):
            self.assertTrue(stage.is_resource(name), name)

    def test_hidden_and_build_outputs_cannot_enter_context(self):
        for name in ("dotnet/src/X/obj/Generated.cs", "dotnet/src/X/.env.json",
                     "dotnet/src/TaxCredit.AppHost/Program.cs", "dotnet/tests/X/Test.cs"):
            self.assertFalse(stage.is_source(name), name)
        self.assertFalse(stage.is_resource("backend/rules/.env.json"))

    def test_embedded_resources_and_embedded_mapping_are_build_inputs(self):
        self.assertTrue(stage.is_source("dotnet/src/TaxCredit.Infrastructure.Ai/Agents/Resources/Prompts.resx"))
        self.assertTrue(stage.is_source("backend/data/source/mapping/default.json"))

    def test_destructive_staging_is_bounded_to_named_child(self):
        with temporary() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                stage.reset_directory(root, root)
            self.assertTrue(root.exists())

    def test_hash_manifest_rejects_tampering(self):
        with temporary() as directory:
            root = Path(directory)
            self.make_publication(root)
            (root / ".artifacts" / "publish" / "api" / "TaxCredit.Api.dll").write_bytes(b"changed")
            previous = root / ".artifacts" / "api.zip"
            previous.write_bytes(b"previous verified package")
            with patch.object(package_zip, "DEPLOY", root), patch.object(sys, "argv", ["package_zip.py", "--service", "api"]):
                with self.assertRaisesRegex(RuntimeError, "checksum"):
                    package_zip.main()
            self.assertEqual(b"previous verified package", previous.read_bytes())
            self.assertFalse(previous.with_suffix(".zip.tmp").exists())

    def test_unmanifested_files_cannot_be_zipped(self):
        with temporary() as directory:
            root = Path(directory)
            self.make_publication(root)
            (root / ".artifacts" / "publish" / "api" / ".env").write_text("synthetic", encoding="ascii")
            with patch.object(package_zip, "DEPLOY", root), patch.object(sys, "argv", ["package_zip.py", "--service", "api"]):
                with self.assertRaisesRegex(RuntimeError, "unmanifested"):
                    package_zip.main()

    def test_zip_is_deterministic_and_preserves_package_root(self):
        with temporary() as directory:
            root = Path(directory)
            self.make_publication(root)
            with patch.object(package_zip, "DEPLOY", root), patch.object(sys, "argv", ["package_zip.py", "--service", "api"]), contextlib.redirect_stdout(io.StringIO()):
                package_zip.main()
                before = (root / ".artifacts" / "api.zip").read_bytes()
                package_zip.main()
            self.assertEqual(before, (root / ".artifacts" / "api.zip").read_bytes())
            with zipfile.ZipFile(root / ".artifacts" / "api.zip") as archive:
                self.assertEqual({"TaxCredit.Api.dll", "artifact-manifest.json"}, set(archive.namelist()))

    def test_worker_and_unactivated_azd_deploy_are_refused_before_any_azure_command(self):
        for service, expected in (("worker", "topology unavailable"), ("api", "activation is required")):
            result = subprocess.run(
                ["pwsh", "-NoLogo", "-NoProfile", "-File", str(stage.DEPLOY / "guard-target.ps1"),
                 "-Service", service], capture_output=True, text=True,
                env={"PATH": os.environ["PATH"],
                     **{key: value for key, value in os.environ.items()
                        if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC"}}},
                timeout=20
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn(expected, result.stderr)

    def test_native_target_assertions_accept_only_matching_dotnet_metadata(self):
        script = r"""
$env:DEPLOY_DOTNET_ACTIVATE = '1'
$env:DOTNET_ENVIRONMENT_NAME = 'proof'
$env:DOTNET_RESOURCE_GROUP_NAME = 'rg-tcc-dotnet-proof'
$env:DOTNET_TARGET_SUBSCRIPTION = '00000000-0000-0000-0000-000000000001'
$env:DOTNET_API_APP_NAME = 'app-tcc-dotnet-proof-api'
$env:GIT_COMMIT = '0000000000000000000000000000000000000000'
$env:AZURE_SUBSCRIPTION_ID = ''
$env:AZURE_ENV_NAME = ''
$env:AZURE_RESOURCE_GROUP = ''
function az {
    if ($args[0] -eq 'account') { $env:DOTNET_TARGET_SUBSCRIPTION }
    elseif ($args[1] -eq 'show') {
        @{
            id="/subscriptions/$($env:DOTNET_TARGET_SUBSCRIPTION)/resourceGroups/rg-tcc-dotnet-proof/providers/Microsoft.Web/sites/app-tcc-dotnet-proof-api"
            reserved=$true; public='Disabled'; identity='UserAssigned'
            tags=@{'tcc-runtime'='dotnet';'tcc-ownership'='infra-dotnet';'azd-service-name'='dotnet-api';'azd-env-name'='proof'}
        } | ConvertTo-Json -Compress
    }
    elseif ($args[2] -eq 'show') { '{"stack":"DOTNETCORE|10.0","start":"dotnet TaxCredit.Api.dll"}' }
    elseif ($args[2] -eq 'appsettings') { $env:GIT_COMMIT }
    else { throw 'Unexpected metadata operation.' }
    $global:LASTEXITCODE = 0
}
& '__GUARD__' -Service api
"""
        script = script.replace("__GUARD__", str(stage.DEPLOY / "guard-target.ps1").replace("'", "''"))
        for source, accepted in ((script, True), (script.replace("public='Disabled'", "public='Enabled'"), False),
                                 (script.replace('"DOTNETCORE|10.0"', '"PYTHON|3.12"'), False)):
            result = subprocess.run(["pwsh", "-NoLogo", "-NoProfile", "-Command", source],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(accepted, result.returncode == 0, result.stderr)

    @staticmethod
    def make_publication(root: Path):
        publication = root / ".artifacts" / "publish" / "api"
        publication.mkdir(parents=True)
        content = b"synthetic executable fixture"
        (publication / "TaxCredit.Api.dll").write_bytes(content)
        (publication / "artifact-manifest.json").write_text(json.dumps({
            "schema": 1, "service": "api", "commit": "0" * 40,
            "files": [{"path": "TaxCredit.Api.dll", "sha256": hashlib.sha256(content).hexdigest()}],
        }), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
