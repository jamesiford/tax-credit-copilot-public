"""Synthetic mutations cover fidelity and the value-free output boundary together."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from admission import capacity_admission
from catalogue import Refused, admitted_case, check_rows, origin, request_path
from safe_compare import compare_document, compare_responses

HERE = Path(__file__).resolve().parent
SENTINEL = "PRIVATE_SENTINEL_z42_do_not_persist"


def response(value: object, status: int = 200) -> dict:
    from contract.exchange import describe_body
    content = json.dumps(value, separators=(",", ":")).encode()
    return {"status": status, "headers": {"content-type": "application/json"},
            "body": describe_body({"content-type": "application/json"}, content)}


class CompareMutations(unittest.TestCase):
    def test_strict_values_money_scale_type_presence_and_status(self):
        baseline = response({"money": "3500.0", "nullable": None, "rows": [1, 2]})
        mutations = [
            response({"money": "3500.0000", "nullable": None, "rows": [1, 2]}),
            response({"money": 3500.0, "nullable": None, "rows": [1, 2]}),
            response({"money": "3500.0", "rows": [1, 2]}),
            response({"money": "3500.0", "nullable": None, "rows": [2, 1]}),
            response({"money": "3500.0", "nullable": None, "rows": [1, 2]}, 503),
        ]
        for mutation in mutations:
            with self.subTest(ordinal=mutations.index(mutation)):
                self.assertFalse(compare_responses("eligibility", baseline, mutation)["semantic_equal"])

    def test_only_existing_semantic_normalisations(self):
        from contract.exchange import describe_body
        left, right = response({"value": 5.0, "eligible": True}), response({"eligible": True, "value": 5})
        right["body"] = describe_body(right["headers"], b'{ "eligible":true, "value":5 }')
        result = compare_responses("eligibility", left, right)
        self.assertTrue(result["semantic_equal"])
        self.assertFalse(result["content_hash_equal"])
        self.assertFalse(result["wire_equal"])

    def test_event_order_and_member_content_order_and_integrity(self):
        from contract.exchange import describe_body
        sse = {"status": 200, "headers": {"content-type": "text/event-stream"},
               "body": describe_body({"content-type": "text/event-stream"},
                                     b"event: first\ndata: 1\n\nevent: second\ndata: 2\n\n")}
        changed = deepcopy(sse)
        changed["body"]["events"].reverse()
        self.assertIn("event", compare_responses("ai", sse, changed)["categories"])
        archive = {"status": 200, "headers": {"x-content-sha256": "a" * 64},
                   "body": {"kind": "bytes", "length": 100, "sha256": "a" * 64, "zip_entries": [
                       {"name": SENTINEL + ".xml", "size": 20, "sha256": "b" * 64},
                       {"name": "manifest.json", "size": 30, "sha256": "c" * 64}]}}
        changed = deepcopy(archive)
        changed["body"].update(length=110, sha256="d" * 64)
        changed["headers"]["x-content-sha256"] = "d" * 64
        self.assertTrue(compare_responses("artifact", archive, changed)["semantic_equal"])
        changed["body"]["zip_entries"][0]["sha256"] = "e" * 64
        verdict = compare_responses("artifact", archive, changed)
        self.assertIn("zip-entry", verdict["categories"])
        self.assertNotIn(SENTINEL, json.dumps(verdict))
        changed = deepcopy(archive)
        changed["body"]["zip_entries"].reverse()
        self.assertIn("zip-entry", compare_responses("artifact", archive, changed)["categories"])
        changed = deepcopy(archive)
        changed["headers"]["x-content-sha256"] = "f" * 64
        self.assertFalse(compare_responses("artifact", archive, changed)["semantic_equal"])

    def test_trails_canonical_and_per_file_manifest_hashes_are_not_container_exempt(self):
        left = response({"bundle_sha256": "a" * 64, "bundle_bytes": 100,
                         "trail_hash": "b" * 64, "canonical_hash": "c" * 64,
                         "manifest": [{"sha256": "d" * 64}]})
        for field in ("trail_hash", "canonical_hash", "manifest"):
            changed = deepcopy(left)
            changed["body"]["value"][field] = "e" * 64
            self.assertFalse(compare_responses("export", left, changed)["semantic_equal"])

    def test_private_keys_headers_filenames_urls_errors_and_no_files_or_traces(self):
        left = response({"facts": {SENTINEL + ".https://private.invalid": SENTINEL}})
        right = response({"facts": {SENTINEL + ".https://private.invalid": None}})
        left["headers"]["x-" + SENTINEL] = SENTINEL
        out, err = io.StringIO(), io.StringIO()
        with patch("builtins.open", side_effect=AssertionError("No payload files")), \
                redirect_stdout(out), redirect_stderr(err):
            verdict = compare_responses("eligibility", left, right)
            broken = compare_document({"case": SENTINEL, "expected": left, "actual": right})
        text = json.dumps([verdict, broken]) + out.getvalue() + err.getvalue()
        self.assertNotIn(SENTINEL, text)
        self.assertNotIn("private.invalid", text)
        self.assertNotIn("expected", text)
        self.assertFalse(broken["semantic_equal"])

    def test_subprocess_bridge_never_emits_payload_or_traceback(self):
        document = {"case": "eligibility", "sample": 1,
                    "expected": response({SENTINEL: SENTINEL}), "actual": response({})}
        # Standard JSON transports Num lexemes through the existing contract serializer.
        from contract import jsontext
        for data in (jsontext.dumps(document).encode(), (SENTINEL + "{").encode()):
            result = subprocess.run([sys.executable, "-B", str(HERE / "safe_compare.py")],
                                    input=data, capture_output=True, timeout=5, check=False)
            output = (result.stdout + result.stderr).decode()
            self.assertNotIn(SENTINEL, output)
            self.assertNotIn("Traceback", output)
            self.assertFalse(json.loads(result.stdout)["semantic_equal"])


class BoundaryTests(unittest.TestCase):
    def test_closed_paths_and_bounds_before_transport(self):
        for name in ("gateway", "ai", "artifact", "export", "sealed", "refresh", "run",
                     "prepare", "commit", "download", "narration", "https://private.invalid"):
            with self.subTest(name=name), self.assertRaises(Refused):
                admitted_case(name)
        self.assertIn("limit=25", request_path("eligibility", 1001, 2025, "GA_JTC", "min_max"))
        with self.assertRaises(Refused):
            request_path("eligibility", "../private", 2025, "GA_JTC", "min_max")
        with self.assertRaises(Refused):
            check_rows({"rows": list(range(26))}, 25)
        for url in ("http://private.invalid", "https://user:token@private.invalid",
                    "https://private.invalid/path", "https://private.invalid?secret=1"):
            with self.subTest(ordinal=len(url)), self.assertRaises(Refused):
                origin(url)

    def test_admission_denies_before_any_connection_and_sanitises_subprocess_errors(self):
        with patch.dict(os.environ, {"TCC_SHADOW_APPROVED": ""}), \
                patch("admission.guard_preflight", return_value={"verdict": "passed"}), \
                patch("admission.oracle_preflight", return_value=True), \
                patch("admission.subprocess.run") as run:
            self.assertEqual("not-attempted", capacity_admission(Path(SENTINEL))["capacity"])
            run.assert_not_called()
        with patch.dict(os.environ, {"TCC_SHADOW_APPROVED": "yes"}), \
                patch("admission.guard_preflight", return_value={"verdict": "passed"}), \
                patch("admission.oracle_preflight", return_value=True), \
                patch("admission.subprocess.run", return_value=subprocess.CompletedProcess(
                    [], 2, ("ERROR private " + SENTINEL).encode(), SENTINEL.encode())):
            result = capacity_admission(Path(SENTINEL))
            self.assertEqual("unavailable", result["capacity"])
            self.assertNotIn(SENTINEL, json.dumps(result))
