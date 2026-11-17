import unittest

from wave_replay_report import accepted_entries, registered_markup


class WavePolicyAuditTests(unittest.TestCase):
    def test_numeric_json_is_not_waived_by_an_error_or_framework_registration(self):
        failure = {"route": "POST /mcp", "scenario": "g1_mcp", "case": "call", "category": "value",
                   "path": "result.structuredContent.facts.eligible", "expected": "539", "actual": "540"}
        entry = {"id": "test", "route": failure["route"], "kind": "framework_default"}
        record = {"response": {"body": {"kind": "json"}, "headers": {"content-type": "application/json"}}}
        self.assertEqual([], accepted_entries(failure, record, [entry]))

    def test_native_markup_exception_is_limited_to_registered_html_document_bodies(self):
        failure = {"route": "GET /docs", "category": "value", "path": "body.text"}
        record = {"response": {"body": {"kind": "text"}, "headers": {"content-type": "text/html; charset=utf-8"}}}
        entry = {"kind": "framework_default"}
        self.assertTrue(registered_markup(failure, record, [entry]))
        for changed in ({**failure, "route": "GET /api/eligibility/2025"},
                        {**failure, "path": "facts.eligible"}, {**failure, "category": "status"}):
            self.assertFalse(registered_markup(changed, record, [entry]))
        self.assertFalse(registered_markup(failure, record, []))
        record["response"]["body"]["kind"] = "json"
        self.assertFalse(registered_markup(failure, record, [entry]))

    def test_durable_exception_requires_exact_registered_preview_counter_paths(self):
        failure = {"route": "POST /api/v2/run-batches", "scenario": "p2_run_batches", "case": "preview",
                   "category": "value", "path": "preview.never_run", "expected": "1", "actual": "0"}
        record = {"response": {"body": {"kind": "json"}, "headers": {}}}
        entry = {"id": "test", "route": failure["route"], "kind": "defect_fix", "finding": "F-18",
                 "path_prefix": "preview.never_run"}
        self.assertEqual([entry], accepted_entries(failure, record, [entry]))
        for path in ("preview.items", "preview.eligible", "preview.last_run.run_id", "facts.eligible"):
            self.assertEqual([], accepted_entries({**failure, "path": path}, record, [entry]))
        self.assertEqual([], accepted_entries(failure, record, [{**entry, "finding": ""}]))


if __name__ == "__main__":
    unittest.main()
