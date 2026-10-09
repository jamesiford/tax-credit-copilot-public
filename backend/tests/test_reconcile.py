"""[P1] PILOT-04 — reconciliation harness tests."""
from __future__ import annotations

from tools.reconcile import reconcile


def test_p1_pilot04_reconcile_classifies_each_row():
    bench = [
        {"key": "GA", "average_headcount": 60.59},
        {"key": "SC", "average_headcount": 5.12},
        {"key": "NC", "average_headcount": 24.08},
        {"key": "VA", "average_headcount": 4.42},
    ]
    computed = [
        {"key": "GA", "average_headcount": 60.59},   # exact match
        {"key": "SC", "average_headcount": 5.40},    # within tolerance (0.5)
        {"key": "NC", "average_headcount": 30.00},   # mismatch
        {"key": "TN", "average_headcount": 1.83},    # missing from benchmark
    ]
    report = reconcile(bench, computed, tolerance=0.5)
    by_key = {r["key"]: r["status"] for r in report["rows"]}
    assert by_key["GA"] == "match"
    assert by_key["SC"] == "within_tolerance"
    assert by_key["NC"] == "mismatch"
    assert by_key["TN"] == "missing_benchmark"
    assert by_key["VA"] == "missing_computed"
    assert report["summary"]["reconciled"] is False


def test_p1_pilot04_clean_tie_out_reconciles():
    bench = [{"key": "GA", "average_headcount": 60.59}]
    computed = [{"key": "GA", "average_headcount": 60.59}]
    report = reconcile(bench, computed)
    assert report["summary"]["reconciled"] is True
    assert report["summary"]["exact_matches"] == 1


def test_p1_pilot04_endpoint_ties_out_against_synthetic_benchmark(client):
    body = client.get("/api/reconcile/2025").json()
    assert body["_roadmap_tag"] == "P1"
    assert body["benchmark_source"]["_synthetic"] is True
    # The synthetic fixture mirrors the engine, so it should reconcile cleanly.
    assert body["summary"]["mismatches"] == 0
    assert body["summary"]["reconciled"] is True
