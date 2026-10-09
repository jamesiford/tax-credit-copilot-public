"""Tests for the per-employee derivation drill + review annotations (Stage 2)."""
from __future__ import annotations


def _a_ga_employee(client) -> str:
    body = client.get("/api/onezero/2025?state=GA").json()
    ga = next(r for r in body["results"] if r["state"] == "GA")
    return ga["eligibility_sample"][0]["Employee_ID"]


def test_employee_drill_shape(client):
    eid = _a_ga_employee(client)
    r = client.get(f"/api/onezero/2025/employee/{eid}?state=GA")
    assert r.status_code == 200
    d = r.json()
    assert d["employee_id"] == eid
    assert d["state"] == "GA"
    # Full source -> output chain.
    assert d["source_lines"] and "Hours_Worked" in d["source_lines"][0]
    assert "avg_weekly_hours" in d and "avg_weekly_wages" in d
    ft = d["floor_test"]
    assert ft["min_weekly_hours"] == 35.0
    assert len(d["months"]) == 12
    # An eligibility-sample employee passed both floors -> counts.
    assert d["eligible"] is True
    assert ft["weight"] in (0.5, 1.0)
    assert d["months_counted"] >= 1
    assert d["headcount_contribution"] > 0


def test_employee_drill_unknown_404(client):
    r = client.get("/api/onezero/2025/employee/NOPE-XYZ?state=GA")
    assert r.status_code == 404


def test_employee_review_roundtrip(client):
    from api.onezero import reset_employee_reviews

    reset_employee_reviews()
    eid = _a_ga_employee(client)
    r = client.post(
        f"/api/onezero/employee/{eid}/review",
        json={"status": "validated", "note": "checked", "reviewer": "Maria"},
    )
    assert r.status_code == 200
    assert r.json()["review"]["status"] == "validated"

    # Drill reflects the annotation.
    d = client.get(f"/api/onezero/2025/employee/{eid}?state=GA").json()
    assert d["review"]["status"] == "validated"

    # Clear it.
    r2 = client.post(f"/api/onezero/employee/{eid}/review", json={"status": "cleared"})
    assert r2.status_code == 200
    assert r2.json()["review"] is None
    reset_employee_reviews()
