"""Agent findings: judgements that reach a human, and answers that survive.

The Agent Workbench listed registered agents. That is topology — it shows how
the software is arranged, which is what the editorial test cuts. A finding is
different: "this employee is counted at two worksites in the same month" changes
Average Headcount, which changes a number on a filed return.

Two properties matter more than the rest, and both are tested hardest:

**A decision must survive a restart.** The previous QC resolution store was a
module-level dict. A judgement that changes a filed figure cannot evaporate
because a container recycled.

**An unresolved finding is not a clean result.** Counting it separately is the
difference between "nothing is wrong" and "nobody has looked".
"""
from __future__ import annotations

import pytest


@pytest.fixture
def findings_client(tmp_path):
    """A TestClient with its own finding database."""
    from fastapi.testclient import TestClient

    from api import findings as findings_api
    from infrastructure.persistence.sqlite_findings import SqliteFindingRepository
    from main import app

    original = findings_api._REPO
    repo = SqliteFindingRepository(tmp_path / "findings.db")
    findings_api.set_repository(repo)
    try:
        yield TestClient(app)
    finally:
        repo.close()
        findings_api.set_repository(original)


def _first(client):
    body = client.get("/api/findings/1001/2025?state=GA").json()
    assert body["findings"], "the fixture has test-of-twos anomalies"
    return body["findings"][0]


def _instance(client):
    """A finding at instance grain, or skip.

    Grain follows volume, so whether any instance-grain finding exists depends
    on the fixture. A test about instance behaviour should say so rather than
    silently assert against a policy roll-up.
    """
    import pytest

    body = client.get("/api/findings/1001/2025?state=GA").json()
    for finding in body["findings"]:
        if finding["grain"] == "instance":
            return finding
    pytest.skip("fixture rolled every finding to policy grain")


# ------------------------------------------------------------------ grain


def test_findings_are_counted_as_decisions_not_instances(findings_client):
    """The number that matters is how many judgements somebody has to make.

    On the real reference client the detectors emit 36,016 anomalies. Thirty-six
    thousand buttons is not a work queue — it is the "look how complex this
    software is" failure the editorial test exists to prevent. Rolled to the
    grain a human actually decides at, it is three.
    """
    body = findings_client.get("/api/findings/1001/2025?state=GA").json()
    summary = body["summary"]

    assert summary["total"] == len(body["findings"])
    assert summary["instances"] >= summary["total"], (
        "instances is the underlying population, decisions are the roll-up"
    )
    for finding in body["findings"]:
        assert finding["grain"] in {"policy", "instance"}


def test_a_policy_finding_carries_its_population_and_a_sample(findings_client):
    """A roll-up must not understate what is at stake, or hide the pattern."""
    body = findings_client.get("/api/findings/1001/2025?state=GA").json()
    policies = [f for f in body["findings"] if f["grain"] == "policy"]
    if not policies:
        import pytest
        pytest.skip("fixture has no policy-grain findings")

    for policy in policies:
        population = policy["population"]
        assert population["instances"] >= 1
        assert population["employees_affected"] >= 1
        # A roll-up showing "$0 / 0 hours" beside thousands of affected
        # employees reads as "nothing at stake", which is the opposite of true.
        assert population["total_wages"] > 0
        assert population["total_hours"] > 0
        # Enough to judge the pattern, far short of a dump.
        assert len(population["sample"]) <= 5
        assert population["sample_of"] == population["instances"]
        assert policy["employee_id"] is None, "a policy is not about one person"


def test_grain_follows_volume(findings_client):
    """A handful of exceptions is a queue; thousands is a pattern.

    Asking a reviewer to adjudicate three thousand evenly-split employees one at
    a time is not review, it is attrition — and a client whose staff genuinely
    work across sites has one payroll characteristic, not three thousand
    anomalies.
    """
    from api.findings import _INSTANCE_CAP, _KINDS

    assert _INSTANCE_CAP > 0
    assert _KINDS["test_of_twos"]["grain"] == "policy_with_exceptions"
    assert _KINDS["meaningful_pay_period"]["grain"] == "policy"


def test_a_dominant_worksite_is_arithmetic_not_a_judgement(findings_client):
    """120 hours at one site and 4 at another does not need a human."""
    from api.findings import _is_ambiguous

    clear = {"units": [{"hours": 120.0}, {"hours": 4.0}]}
    split = {"units": [{"hours": 60.0}, {"hours": 55.0}]}

    assert _is_ambiguous(clear) is False
    assert _is_ambiguous(split) is True
    # No hours at all cannot be resolved by arithmetic, so a person looks.
    assert _is_ambiguous({"units": []}) is True


# ------------------------------------------------------------- surfacing


def test_a_finding_explains_itself(findings_client):
    """A count is not a finding. "Why it matters" is what makes it actionable."""
    finding = _first(findings_client)

    assert finding["kind"] in {"test_of_twos", "meaningful_pay_period"}
    assert "counted twice" in finding["why_it_matters"] or "denominator" in finding["why_it_matters"]
    assert finding["proposes"] in {"assign", "drop"}
    assert finding["proposed_effect"], "say what accepting the proposal would do"
    if finding["grain"] == "instance":
        assert finding["employee_id"], "an instance is attached to the employee it affects"


def test_a_proposal_is_a_starting_point_not_an_action(findings_client):
    """Nothing is applied until a human decides. That is the whole point."""
    finding = _first(findings_client)
    assert finding["requires_decision"] is True
    assert finding["resolution"] is None


def test_findings_carry_their_evidence(findings_client):
    """A reviewer deciding between two worksites needs to see both."""
    finding = _instance(findings_client)
    units = finding["evidence"]["units"]

    assert len(units) >= 2
    for unit in units:
        assert unit["worksite_id"]
        assert "wages" in unit and "hours" in unit


def test_open_findings_sort_first(findings_client):
    """The list is a work queue, not a report."""
    body = findings_client.get("/api/findings/1001/2025?state=GA").json()
    fid = body["findings"][0]["finding_id"]
    findings_client.post(f"/api/findings/{fid}/resolve", json={
        "client_id": 1001, "tax_year": 2025, "resolution": "accept",
        "decided_by": "lead@example.com",
    })

    after = findings_client.get("/api/findings/1001/2025?state=GA").json()["findings"]
    assert after[0]["requires_decision"] is True
    assert after[-1]["requires_decision"] is False


# ------------------------------------------------------------- deciding


def test_a_decision_is_recorded_against_the_finding(findings_client):
    finding = _instance(findings_client)
    worksite = finding["evidence"]["units"][0]["worksite_id"]

    response = findings_client.post(f"/api/findings/{finding['finding_id']}/resolve", json={
        "client_id": 1001, "tax_year": 2025, "resolution": "assign",
        "keep_worksite": worksite, "decided_by": "lead@example.com",
        "note": "Confirmed with the client's payroll contact.",
    })
    assert response.status_code == 200

    body = response.json()
    assert body["resolution"] == "assign"
    assert body["detail"]["keep_worksite"] == worksite
    assert body["decided_by"] == "lead@example.com"


def test_assign_without_a_worksite_is_rejected(findings_client):
    """"Keep this employee at one unit" needs to say which unit."""
    finding = _first(findings_client)
    response = findings_client.post(f"/api/findings/{finding['finding_id']}/resolve", json={
        "client_id": 1001, "tax_year": 2025, "resolution": "assign",
        "decided_by": "lead@example.com",
    })
    assert response.status_code == 422
    assert "keep_worksite" in response.json()["detail"]


def test_an_unknown_resolution_is_rejected(findings_client):
    finding = _first(findings_client)
    response = findings_client.post(f"/api/findings/{finding['finding_id']}/resolve", json={
        "client_id": 1001, "tax_year": 2025, "resolution": "probably_fine",
        "decided_by": "lead@example.com",
    })
    assert response.status_code == 422


def test_deciding_again_supersedes_rather_than_overwrites(findings_client):
    """"What did you decide, and when?" is an audit question."""
    finding = _first(findings_client)
    fid = finding["finding_id"]

    for resolution in ("flag", "accept"):
        findings_client.post(f"/api/findings/{fid}/resolve", json={
            "client_id": 1001, "tax_year": 2025, "resolution": resolution,
            "decided_by": "lead@example.com",
        })

    history = findings_client.get(f"/api/findings/1001/{fid}/history").json()["history"]
    assert [h["resolution"] for h in history] == ["flag", "accept"]
    assert history[0]["superseded_at"] is not None
    assert history[1]["superseded_at"] is None


def test_reopening_leaves_the_earlier_decision_in_history(findings_client):
    """Somebody decided something once; that survives them changing their mind."""
    finding = _first(findings_client)
    fid = finding["finding_id"]

    findings_client.post(f"/api/findings/{fid}/resolve", json={
        "client_id": 1001, "tax_year": 2025, "resolution": "accept",
        "decided_by": "lead@example.com",
    })
    findings_client.post(f"/api/findings/{fid}/reopen", json={
        "client_id": 1001, "tax_year": 2025, "resolution": "accept",
        "decided_by": "lead@example.com",
    })

    body = findings_client.get("/api/findings/1001/2025?state=GA").json()
    reopened = next(f for f in body["findings"] if f["finding_id"] == fid)
    assert reopened["requires_decision"] is True

    history = findings_client.get(f"/api/findings/1001/{fid}/history").json()["history"]
    assert len(history) == 1, "the withdrawn decision is closed, not deleted"
    assert history[0]["superseded_at"] is not None


# ------------------------------------------------------------ durability


def test_a_decision_survives_a_restart(tmp_path):
    """The reason this store exists.

    The previous QC resolutions lived in a module-level dict and reset on
    restart. A judgement that changes a filed figure cannot evaporate because a
    container recycled.
    """
    from infrastructure.persistence.sqlite_findings import (
        FindingResolution,
        SqliteFindingRepository,
    )

    path = tmp_path / "findings.db"
    first = SqliteFindingRepository(path)
    first.record(FindingResolution(
        finding_id="t2:E00200:2025-02", client_id=1001, tax_year=2025,
        resolution="assign", detail={"keep_worksite": "GA_MAC_OPS"},
        decided_by="lead@example.com", decided_at="2026-08-27T09:00:00+00:00",
    ))
    first.close()

    second = SqliteFindingRepository(path)
    try:
        live = second.live(1001, 2025)
        assert len(live) == 1
        assert live[0].resolution == "assign"
        assert live[0].detail["keep_worksite"] == "GA_MAC_OPS"
    finally:
        second.close()


def test_decisions_are_scoped_to_a_tenant(tmp_path):
    """One client's judgement must not appear on another's queue."""
    from infrastructure.persistence.sqlite_findings import (
        FindingResolution,
        SqliteFindingRepository,
    )

    repo = SqliteFindingRepository(tmp_path / "findings.db")
    try:
        for client_id in (1001, 2001):
            repo.record(FindingResolution(
                finding_id="t2:E00200:2025-02", client_id=client_id, tax_year=2025,
                resolution="accept", decided_by="lead@example.com",
                decided_at="2026-08-27T09:00:00+00:00",
            ))

        assert len(repo.live(1001)) == 1
        assert repo.live(1001)[0].client_id == 1001
        assert len(repo.live(2001)) == 1
    finally:
        repo.close()


# --------------------------------------------------------------- summary


def test_open_findings_are_counted_separately(findings_client):
    """"Nothing is wrong" and "nobody has looked" are different claims."""
    body = findings_client.get("/api/findings/1001/2025?state=GA").json()
    summary = body["summary"]

    assert summary["total"] == summary["requires_decision"], "nothing decided yet"
    assert summary["all_decided"] is False
    assert summary["none_found"] is False


def test_all_decided_is_not_the_same_as_none_found(findings_client):
    """A queue worked through is a different state from a queue that was empty."""
    body = findings_client.get("/api/findings/1001/2025?state=GA").json()
    for finding in body["findings"]:
        findings_client.post(f"/api/findings/{finding['finding_id']}/resolve", json={
            "client_id": 1001, "tax_year": 2025, "resolution": "accept",
            "decided_by": "lead@example.com",
        })

    after = findings_client.get("/api/findings/1001/2025?state=GA").json()["summary"]
    assert after["requires_decision"] == 0
    assert after["all_decided"] is True
    assert after["none_found"] is False, "findings existed; they were answered"


def test_findings_are_scoped_to_the_requested_tenant(findings_client):
    """Same rule as everywhere else: a wrong tenant is empty, never a default."""
    response = findings_client.get("/api/findings/999999/2025")
    assert response.status_code == 404
    assert "999999" in response.json()["detail"]
