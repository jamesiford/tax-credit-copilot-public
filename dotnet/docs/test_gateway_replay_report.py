import unittest

from gateway_replay_report import durable_counter, global_tolerance


class GatewayPolicyDiagnosticTests(unittest.TestCase):
    def test_nested_mcp_error_wording_is_free_but_error_code_is_not(self):
        failure = {"category": "value", "path": "result.structuredContent.error.message"}
        self.assertTrue(global_tolerance(failure, 200))
        self.assertTrue(global_tolerance({**failure, "path": "error.message"}, 200))
        self.assertFalse(global_tolerance({**failure, "path": "result.structuredContent.error.code"}, 200))

    def test_rendered_error_wording_requires_the_same_error_code(self):
        failure = {"category": "value", "path": "result.content[0].text",
                   "expected": "The request did not go through (invalid_arguments): source wording",
                   "actual": "The request did not go through (invalid_arguments): native wording"}
        self.assertTrue(global_tolerance(failure, 200))
        self.assertFalse(global_tolerance({**failure, "actual": failure["actual"].replace("invalid_arguments", "not_authorized")}, 200))

    def test_good_tool_text_and_figures_are_not_error_wording(self):
        self.assertFalse(global_tolerance({"category": "value", "path": "result.content[0].text",
                                          "expected": "539 eligible", "actual": "540 eligible"}, 200))
        self.assertFalse(global_tolerance({"category": "value", "path": "facts.eligible",
                                          "expected": 539, "actual": 540}, 200))
        self.assertFalse(global_tolerance({"category": "value", "path": "result.structuredContent.facts.findings[0].message",
                                          "expected": "539 eligible", "actual": "540 eligible"}, 200))

    def test_durable_exception_is_limited_to_registered_operational_preview_counters(self):
        entries = [{"finding": "F-18"}]
        self.assertTrue(durable_counter({"path": "preview.never_run"}, entries))
        for path in ("preview.items", "preview.eligible", "facts.eligible", "counts.never_run", "preview.last_run.run_id"):
            self.assertFalse(durable_counter({"path": path}, entries))
        self.assertFalse(durable_counter({"path": "preview.never_run"}, []))


if __name__ == "__main__":
    unittest.main()
