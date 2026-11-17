"""Fixture configuration is not replaced with the observer's provenance metadata."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from admission import ROOT
from hermetic import environment


class HermeticTests(unittest.TestCase):
    def test_external_configuration_is_not_inherited_and_fixture_commit_is_not_overridden(self):
        output = ROOT / "dotnet" / "artifacts" / "w4-integration" / "synthetic-environment-test"
        with patch.dict(os.environ, {"GIT_COMMIT": "private-looking-sentinel",
                                     "WAREHOUSE_SQL_ENDPOINT": "private-looking-sentinel",
                                     "FOUNDRY_PROJECT_ENDPOINT": "private-looking-sentinel"}, clear=True), \
                patch.object(Path, "mkdir"):
            result = environment(output)
        self.assertNotIn("GIT_COMMIT", result)
        self.assertNotIn("WAREHOUSE_SQL_ENDPOINT", result)
        self.assertEqual("", result["FOUNDRY_PROJECT_ENDPOINT"])
        self.assertEqual("csv", result["DATA_SOURCE"])
        self.assertEqual("sqlite", result["TCC_PERSISTENCE_PROVIDER"])
        self.assertTrue(Path(result["TEMP"]).is_relative_to(output))
        self.assertNotIn("private-looking-sentinel", repr(result))
