"""Exercise external setup without starting a server or weakening replay checks."""
import json
import unittest
from unittest.mock import MagicMock, patch

from contract import replay
from contract.replay_setup import prepare_external


class ExternalReplaySetupTests(unittest.TestCase):
    def test_p2_and_auth_are_prepared_before_the_first_exchange(self):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        with patch("contract.replay_setup.urllib.request.urlopen", return_value=response) as post:
            prepare_external("http://localhost:1", "http://localhost:1/__contract__/reset",
                             {"profile": "P2", "auth": {"rate_limit_per_minute": 7}})
        requests = [call.args[0] for call in post.call_args_list]
        self.assertEqual({"profile": "P2"}, json.loads(requests[0].data))
        self.assertTrue(requests[1].full_url.endswith("/__contract__/env"))
        values = json.loads(requests[1].data)["set"]
        self.assertEqual(("entra", "true", "7"), (
            values["AUTH_MODE"], values["CHANNEL_ENFORCE_WRITER_FOR_USERS"],
            values["RATE_LIMIT_PER_MINUTE"]))

    def test_reset_failure_prevents_replay_and_subsequent_setup(self):
        with patch("contract.replay_setup._post", side_effect=RuntimeError("reset refused")) as post:
            with self.assertRaisesRegex(RuntimeError, "reset refused"):
                prepare_external("http://localhost:1", "http://localhost:1/reset", {"profile": "P1"})
        self.assertEqual(1, post.call_count)

    def test_external_main_prepares_each_declared_profile_without_changing_comparison(self):
        reports = [
            {"scenario": name, "exchanges": 1, "failures": [], "tolerated": []}
            for name in ("p1_auth", "p2_reads_writes", "p2_run_batches")
        ]
        events = []
        with patch("sys.argv", ["replay", "--base-url", "http://localhost:1",
                              "--reset-url", "http://localhost:1/reset",
                              "--scenario", "p1_auth", "--scenario", "p2_reads_writes",
                              "--scenario", "p2_run_batches", "--mode", "semantic"]), \
             patch("contract.replay_setup.prepare_external",
                   side_effect=lambda base, reset, spec: events.append(("setup", spec["profile"]))) as setup, \
             patch.object(replay, "replay_one",
                          side_effect=lambda name, base, mode: events.append(("replay", name)) or reports.pop(0)):
            self.assertEqual(0, replay.main())
        self.assertEqual([("setup", "P1"), ("replay", "p1_auth"),
                          ("setup", "P2"), ("replay", "p2_reads_writes"),
                          ("setup", "P2"), ("replay", "p2_run_batches")], events)
        self.assertEqual(3, setup.call_count)

    def test_unauthenticated_scenario_explicitly_restores_its_auth_mode(self):
        with patch("contract.replay_setup._post") as post:
            prepare_external("http://localhost:1/", "http://localhost:1/reset", {"profile": "P1"})
        values = post.call_args.args[1]["set"]
        self.assertEqual({"AUTH_MODE": "none", "CHANNEL_ENFORCE_WRITER_FOR_USERS": "false",
                          "RATE_LIMIT_PER_MINUTE": "60"}, values)

    def test_prepared_external_servers_without_reset_url_are_left_untouched(self):
        report = {"scenario": "p1_auth", "exchanges": 1, "failures": [], "tolerated": []}
        with patch("sys.argv", ["replay", "--base-url", "http://localhost:1",
                              "--scenario", "p1_auth", "--mode", "semantic"]), \
             patch("contract.replay_setup.prepare_external") as setup, \
             patch.object(replay, "replay_one", return_value=report):
            self.assertEqual(0, replay.main())
        setup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
