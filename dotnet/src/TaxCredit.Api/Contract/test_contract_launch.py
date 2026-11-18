"""Keep the conductor launch opt-in compatible without enabling ordinary hosts."""
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


class ContractLaunchTests(unittest.TestCase):
    def arguments(self, marker=None, hooks=None):
        env = {key: value for key, value in os.environ.items()
               if key not in ("CONTRACT_DIR", "CONTRACT_HOOKS")}
        if marker is not None:
            env["CONTRACT_DIR"] = str(marker)
        if hooks is not None:
            env["CONTRACT_HOOKS"] = hooks
        result = subprocess.run([
            "dotnet", "msbuild", str(ROOT / "dotnet/src/TaxCredit.Api/TaxCredit.Api.csproj"),
            "-nologo", "-target:ComputeRunArguments", "-getProperty:RunArguments",
        ], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        return result.stdout.strip()

    def test_conductor_inventory_marker_supplies_the_explicit_startup_flag(self):
        self.assertIn("--CONTRACT_HOOKS=1", self.arguments(ROOT / "contract"))

    def test_ordinary_launch_and_invalid_markers_do_not_enable_hooks(self):
        self.assertNotIn("CONTRACT_HOOKS", self.arguments())
        self.assertNotIn("CONTRACT_HOOKS", self.arguments(ROOT / "dotnet"))

    def test_an_explicit_opt_out_is_never_overridden(self):
        self.assertNotIn("CONTRACT_HOOKS", self.arguments(ROOT / "contract", "0"))


if __name__ == "__main__":
    unittest.main()
