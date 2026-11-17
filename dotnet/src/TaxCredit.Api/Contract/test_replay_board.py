"""Prevent missing replay reports from being mistaken for successful prior runs."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import replay_board


class ReplayReportTests(unittest.TestCase):
    def test_relative_output_is_absolute_before_the_child_changes_directory(self):
        with tempfile.TemporaryDirectory(dir=Path("dotnet/artifacts")) as directory:
            raw = Path(directory)
            scenario = raw / "example.json"
            scenario.write_text(json.dumps({"profile": "P2"}))

            def completed(command, **kwargs):
                output = Path(command[command.index("--out") + 1])
                self.assertTrue(output.is_absolute())
                self.assertIn("http://127.0.0.1:1/__contract__/reset?profile=P2", command)
                output.with_suffix(".json").write_text('{"scenarios": []}')
                return subprocess.CompletedProcess(command, 1)

            with patch("replay_board.subprocess.run", side_effect=completed):
                result = replay_board.run_scenario(Path.cwd(), "python", {}, "http://127.0.0.1:1", scenario, raw)
            self.assertEqual({"scenarios": []}, result)

    def test_a_failed_run_cannot_reuse_a_stale_report(self):
        with tempfile.TemporaryDirectory(dir=Path("dotnet/artifacts")) as directory:
            raw = Path(directory)
            scenario = raw / "example.json"
            scenario.write_text(json.dumps({"profile": "P1"}))
            output = raw / "reports"
            output.mkdir()
            stale = output / "example.json"
            stale.write_text('{"scenarios": []}')
            with patch("replay_board.subprocess.run", return_value=subprocess.CompletedProcess([], 1)):
                with self.assertRaisesRegex(RuntimeError, "did not produce a report"):
                    replay_board.run_scenario(Path.cwd(), "python", {}, "http://127.0.0.1:1", scenario, output)
            self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
