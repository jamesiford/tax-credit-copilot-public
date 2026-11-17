"""Drift, outages and partial observations cannot become successful shadow samples."""
from pathlib import Path
import unittest
from unittest.mock import patch

from catalogue import Refused
from live import connection_options, run
from sampling import Marker, paired, timing_summary
from test_shadow import SENTINEL, response


class SamplingTests(unittest.TestCase):
    def test_timing_keeps_http_errors_and_transport_failures_in_the_denominator(self):
        summary = timing_summary([{"ms": 10, "outcome": "response", "http_success": True},
                                  {"ms": 30, "outcome": "response", "http_success": False},
                                  {"ms": 40, "outcome": "failed", "http_success": False}])
        self.assertEqual(3, summary["attempted"])
        self.assertEqual(2, summary["failures"])
        self.assertEqual(1, summary["http_failures"])
        self.assertEqual(1, summary["transport_failures"])
        self.assertEqual(20, summary["median_ms"])
        self.assertIsNone(summary["p95_ms"])

    def test_driver_trace_credentials_and_duplicate_transport_flags_are_refused(self):
        baseline = ("Driver={ODBC Driver 18 for SQL Server};Server=synthetic.invalid;Database=synthetic;"
                    "Encrypt=Yes;TrustServerCertificate=No;ApplicationIntent=ReadOnly")
        self.assertIn("server", connection_options(baseline))
        for suffix in (";Encrypt=No", ";TraceFile=private.log", ";PWD=private", ";Authentication=ActiveDirectoryMsi"):
            with self.subTest(ordinal=len(suffix)), self.assertRaises(Refused):
                connection_options(baseline + suffix)

    def test_interleaves_and_requires_repeat_and_marker_stability(self):
        calls = []

        def fetch(host):
            calls.append(host)
            return response({"money": "3500.0"})
        result = paired("eligibility", fetch, lambda: Marker(5, "synthetic-modified"))
        self.assertEqual(["python", "dotnet", "dotnet", "python"], calls)
        self.assertEqual(2, result["completed"])
        self.assertEqual(2, result["semantic_matches"])
        self.assertEqual(2, result["hash_matches"])

    def test_changed_missing_and_count_preserving_unproved_markers(self):
        for markers in ([Marker(5, 1), Marker(5, 2), Marker(5, 2)], [None] * 3,
                        [Marker(5, None)] * 3):
            iterator = iter(markers)
            result = paired("eligibility", lambda host: response({"money": "3500.0"}), lambda: next(iterator))
            self.assertGreater(result["inconclusive"], 0)
            self.assertLess(result["completed"], result["planned"])

    def test_dependency_outages_and_partial_pairs_remain_in_denominator(self):
        def failing(host):
            if host == "python":
                raise ConnectionError(SENTINEL)
            return response({"detail": "synthetic"}, 503)
        result = paired("eligibility", failing, lambda: Marker(5, 1))
        self.assertEqual(2, result["attempted"])
        self.assertEqual(0, result["paired"])
        self.assertEqual(2, result["failed"])
        self.assertEqual(0, result["semantic_matches"])
        result = paired("eligibility", lambda host: response({"detail": "synthetic"}, 503), lambda: Marker(5, 1))
        self.assertEqual(2, result["failed"])
        self.assertEqual(0, result["completed"])

    def test_stable_marker_cannot_hide_a_changed_repeat(self):
        calls = []

        def fetch(host):
            calls.append(host)
            return response({"money": "3500.0" if len(calls) <= 2 else "4000.0"})
        result = paired("eligibility", fetch, lambda: Marker(5, 1))
        self.assertEqual(1, result["completed"])
        self.assertEqual(1, result["inconclusive"])

    def test_live_mode_refuses_without_verified_identity_and_safe_runtime_inputs(self):
        with patch("live.capacity_admission", return_value={"capacity": "active"}), \
                patch("live.source_reader") as sql:
            result = run(Path(SENTINEL), {})
            sql.assert_not_called()
        self.assertTrue(all(group["attempted"] == 0 for group in result["groups"].values()))
        self.assertFalse(result["scratch"]["used"])
        self.assertIn("mandatory-audit-excluded", result["groups"]["gateway"]["unmeasured_reasons"])
        self.assertIn("artifact-access-audit-excluded", result["groups"]["claims_artifacts_rules"]["unmeasured_reasons"])
