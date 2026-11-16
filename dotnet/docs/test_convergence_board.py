import unittest

from dotnet.docs.convergence_board import group_for, matches, numeric_change, tolerated


class PolicyDiagnosticsTests(unittest.TestCase):
    def test_route_matching_keeps_methods_and_static_precedence(self):
        groups = {"a": ["POST /x/{id}"], "b": ["GET /x/static", "GET /x/{id}"]}
        self.assertEqual("b", group_for(groups, "GET /x/static", "p1"))
        self.assertEqual("_unassigned", group_for(groups, "DELETE /x/static", "p1"))
        self.assertFalse(matches("POST /x/{id}", "GET /x/12"))

    def test_numeric_changes_including_uuid_draws_cannot_be_waived(self):
        self.assertTrue(numeric_change({"category": "value", "expected": "40000009", "actual": "40000005"}))
        self.assertTrue(numeric_change({"category": "value", "expected": "20", "actual": "17"}))
        self.assertFalse(numeric_change({"category": "status", "expected": "500", "actual": "422"}))

    def test_tolerances_never_hide_schema_or_status(self):
        self.assertTrue(tolerated({"category": "value", "path": "detail[0].msg"}, 422))
        self.assertTrue(tolerated({"category": "header", "path": "headers.vary"}, 200))
        self.assertFalse(tolerated({"category": "value", "path": "summary.total"}, 200))
        self.assertFalse(tolerated({"category": "status", "path": "status"}, 422))


if __name__ == "__main__":
    unittest.main()
