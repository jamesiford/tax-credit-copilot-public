"""Negative fixtures prove that unmocked tests cannot enter the validation run."""

import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "guard_offline", Path(__file__).resolve().parents[1] / "guard_offline.py"
)
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)
MOCK = 'mock_provider "azurerm" {}\nrun "safe" {\n command = apply\n}\n'


class OfflineBoundaryTests(unittest.TestCase):
    def test_explicit_mock_accepts_plan_and_apply(self):
        for command in ("plan", "apply"):
            with self.subTest(command=command):
                self.assertEqual([], GUARD.check_sources({
                    "tests/safe.tftest.hcl": MOCK.replace("apply", command)
                }))

    def test_missing_mock_or_real_provider_refuses(self):
        for fixture in (MOCK.replace('mock_provider "azurerm" {}\n', ""),
                        MOCK + 'provider "azurerm" {}\n',
                        MOCK + 'providers = { azurerm = azurerm.live }\n',
                        MOCK + 'mock_provider "fabric" {}\n'):
            with self.subTest(fixture=fixture):
                self.assertTrue(GUARD.check_sources({"tests/unsafe.tftest.hcl": fixture}))

    def test_alias_provider_or_external_resource_refuses(self):
        for source in ('provider "azurerm" {\n alias = "live"\n}',
                       'provider "fabric" {}',
                       'resource "azurerm_storage_account" "python" {}',
                       'data "azurerm_virtual_network" "python" {}',
                       'import {\n to = azurerm_linux_web_app.python\n}',
                       'module "unknown" {\n source = "example/remote/azurerm"\n}'):
            with self.subTest(source=source):
                self.assertTrue(GUARD.check_sources({
                    "unsafe.tf": source, "tests/safe.tftest.hcl": MOCK
                }))


if __name__ == "__main__":
    unittest.main()
