"""The current policy is explicit; old broader diagnostics cannot silently replace it."""
import unittest

from policy import exact_numeric_entries, global_tolerance


class PolicyTests(unittest.TestCase):
    def test_status_and_success_figures_are_never_global_error_tolerances(self):
        self.assertFalse(global_tolerance({"category": "status", "path": "detail"}))
        self.assertFalse(global_tolerance({"category": "value", "path": "facts.money", "expected": "3500.0"}))
        self.assertTrue(global_tolerance({"category": "header", "path": "headers.vary"}))
        self.assertTrue(global_tolerance({"category": "value", "path": "detail[0].url"}))
        self.assertFalse(global_tolerance({"category": "value", "path": "detail[0].ctx.private"}))
        self.assertFalse(global_tolerance({"category": "value", "path": "findings[0].message"}))
        self.assertTrue(global_tolerance({"category": "value", "path": "validation.findings[0].message"}))

    def test_numeric_manifest_exception_requires_exact_route_and_leaf_path(self):
        entry = {"id": "synthetic", "finding": "F-18", "kind": "defect_fix",
                 "route": "POST /api/v2/run-batches", "categories": ["value"],
                 "path_prefix": "preview.never_run"}
        failure = {"scenario": "synthetic", "case": "synthetic", "route": entry["route"],
                   "category": "value", "path": entry["path_prefix"], "expected": "5", "actual": "6"}
        record = {"response": {"body": {"kind": "json"}, "headers": {}}}
        self.assertTrue(exact_numeric_entries(failure, record, [entry]))
        for change in ({"route": "GET /api/v2/run-batches"}, {"path": "preview.never_run.extra"},
                       {"path": "facts.credit"}, {"path": "preview.calculated_credit"}):
            self.assertFalse(exact_numeric_entries({**failure, **change}, record, [entry]))
