"""The claims API: coverage matrix, decisions, and history.

The coverage endpoint is what B4 renders, so its contract is the one that
matters. Two properties are asserted hardest:

**Opportunity and exposure never net.** They are summed separately all the way
up, per client and overall. A portfolio headline that netted them would let one
client's over-claim cancel another's recoverable dollars — arithmetically true,
commercially useless, and indefensible in front of an authority.

**Out-of-scope is not an opportunity.** A gap in a program we are not engaged to
handle is noise, and noise erodes trust in the gaps that are real.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.claims import ClaimStatus, EngagementScope, Provenance


@pytest.fixture
def claims_client(tmp_path):
    """A TestClient with its own claim database.

    The repository is a module-level singleton (the composition root), so tests
    must swap it or they share one file and each other's rows.
    """
    from fastapi.testclient import TestClient

    from api import claims as claims_api
    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository
    from main import app

    original = claims_api._REPO
    repo = SqliteClaimRepository(tmp_path / "claims.db")
    claims_api.set_repository(repo)
    try:
        yield TestClient(app)
    finally:
        repo.close()
        claims_api.set_repository(original)


def _record(client, **overrides):
    body = {
        "client_id": 1001,
        "program_code": "GA_JTC",
        "tax_year": 2023,
        "status": "assessed",
        "provenance": "computed",
        "decided_by": "analyst@example.com",
        "identified_usd": "140000",
    }
    body.update(overrides)
    return client.post("/api/claims", json=body)


# --------------------------------------------------------------- recording


def test_recording_a_claim_returns_its_reading(claims_client):
    response = _record(claims_client)
    assert response.status_code == 201

    body = response.json()
    assert body["program_code"] == "GA_JTC"
    assert body["outcome"] == "unclaimed"
    assert body["variance_usd"] == "140000"
    assert body["provenance_verified"] is True


def test_an_onboarding_assertion_is_recorded_as_unverified(claims_client):
    """A client arriving with an existing claim. Nothing computed it."""
    body = _record(
        claims_client,
        status="claimed",
        provenance="client_asserted",
        identified_usd="0",
        claimed_usd="90000",
        decided_by="onboarding@example.com",
    ).json()

    assert body["provenance"] == "client_asserted"
    assert body["provenance_verified"] is False
    # We have not computed anything, so we cannot yet call this over-claimed
    # with any authority — but the sign is honest about what we know today.
    assert body["claimed_usd"] == "90000"


def test_a_reasonless_decline_is_rejected_by_the_api(claims_client):
    response = _record(claims_client, status="declined")
    assert response.status_code == 422
    assert "decline_reason" in response.json()["detail"]


def test_an_unknown_status_is_rejected(claims_client):
    assert _record(claims_client, status="probably_fine").status_code == 422


# ------------------------------------------------------------------ history


def test_a_cell_carries_its_whole_history(claims_client):
    _record(claims_client)
    claims_client.post(
        "/api/claims/cell/1001/GA_JTC/2023/transition",
        json={"status": "proposed", "decided_by": "lead@example.com"},
    )
    claims_client.post(
        "/api/claims/cell/1001/GA_JTC/2023/transition",
        json={
            "status": "claimed",
            "decided_by": "filer@example.com",
            "claimed_usd": "140000",
            "filing_reference": "IT-CA-2023-0042",
            "provenance": "filed_by_us",
        },
    )

    body = claims_client.get("/api/claims/cell/1001/GA_JTC/2023").json()
    assert body["current"]["status"] == "claimed"
    assert body["current"]["outcome"] == "confirmed"
    assert [h["status"] for h in body["history"]] == ["assessed", "proposed", "claimed"]


def test_an_illegal_transition_is_a_422_not_a_500(claims_client):
    _record(claims_client)
    response = claims_client.post(
        "/api/claims/cell/1001/GA_JTC/2023/transition",
        json={"status": "certified", "decided_by": "lead@example.com"},
    )
    assert response.status_code == 422
    assert "cannot move" in response.json()["detail"]


def test_a_missing_cell_is_a_404(claims_client):
    assert claims_client.get("/api/claims/cell/1001/GA_JTC/2023").status_code == 404
    assert claims_client.post(
        "/api/claims/cell/1001/GA_JTC/2023/transition",
        json={"status": "proposed", "decided_by": "lead@example.com"},
    ).status_code == 404


# ----------------------------------------------------------------- coverage


def test_client_coverage_is_the_program_by_year_grid(claims_client):
    for year in (2021, 2022, 2023):
        _record(claims_client, tax_year=year)
    _record(claims_client, program_code="FED_WOTC", tax_year=2023)

    body = claims_client.get("/api/claims/coverage/1001").json()
    assert len(body["cells"]) == 4
    assert body["totals"]["cells"] == 4

    filtered = claims_client.get("/api/claims/coverage/1001?tax_year=2023").json()
    assert len(filtered["cells"]) == 2


def test_opportunity_and_exposure_are_summed_separately(claims_client):
    """The assertion this whole endpoint exists to guarantee."""
    # Under-claimed by 40k.
    _record(
        claims_client, tax_year=2022, status="claimed",
        identified_usd="140000", claimed_usd="100000",
    )
    # Over-claimed by 40k.
    _record(
        claims_client, tax_year=2023, status="claimed",
        identified_usd="100000", claimed_usd="140000",
    )

    totals = claims_client.get("/api/claims/coverage/1001").json()["totals"]

    assert totals["opportunity_usd"] == "40000"
    assert totals["exposure_usd"] == "40000"
    assert totals["exposure_cells"] == 1
    # If these had been netted, both would read zero and the screen would show
    # a client with nothing to discuss.
    assert totals["opportunity_usd"] != "0"


def test_exposure_is_visible_at_portfolio_scope_too(claims_client):
    _record(claims_client, client_id=1001, tax_year=2023, status="claimed",
            identified_usd="200000", claimed_usd="150000")
    _record(claims_client, client_id=2001, tax_year=2023, status="claimed",
            identified_usd="50000", claimed_usd="90000")

    body = claims_client.get("/api/claims/coverage").json()

    assert len(body["clients"]) == 2
    assert body["totals"]["opportunity_usd"] == "50000"
    assert body["totals"]["exposure_usd"] == "40000"

    per_client = {c["client_id"]: c["totals"] for c in body["clients"]}
    assert per_client[1001]["exposure_cells"] == 0
    assert per_client[2001]["exposure_cells"] == 1


def test_portfolio_coverage_does_not_mix_tenants(claims_client):
    _record(claims_client, client_id=1001, identified_usd="140000")
    _record(claims_client, client_id=2001, identified_usd="999999")

    body = claims_client.get("/api/claims/coverage/1001").json()
    assert all(c["client_id"] == 1001 for c in body["cells"])
    assert "999999" not in claims_client.get("/api/claims/coverage/1001").text


def test_unverified_cells_are_counted(claims_client):
    _record(claims_client, tax_year=2022, provenance="computed")
    _record(claims_client, tax_year=2023, provenance="client_asserted")

    totals = claims_client.get("/api/claims/coverage/1001").json()["totals"]
    assert totals["unverified_cells"] == 1


def test_v2_portfolio_ranks_by_jobs_gap_and_keeps_unassessed_visible(claims_client):
    _record(
        claims_client,
        client_id=1001,
        tax_year=2023,
        status="assessed",
        identified_usd="0",
        average_headcount="74.1",
        base_average_headcount="73.0",
        threshold_jobs="2.0",
    )
    _record(
        claims_client,
        client_id=2001,
        tax_year=2023,
        status="assessed",
        identified_usd="140000",
        average_headcount="73.0",
        base_average_headcount="73.0",
        threshold_jobs="50.0",
    )
    _record(
        claims_client,
        client_id=2003,
        tax_year=2023,
        status="not_assessed",
        identified_usd="0",
    )

    body = claims_client.get(
        "/api/v2/portfolio?near=true&sort=jobs_gap&order=asc&limit=10&offset=0"
    ).json()

    assert body["items"][0]["client_id"] == 1001
    assert body["items"][0]["gap_jobs"] == 0.9
    assert body["items"][0]["one_more_job_qualifies"] is True
    assert any(item["status"] == "not_assessed" for item in body["items"]) is True
    assert body["total"] >= 2


def test_v2_portfolio_includes_clients_that_have_never_been_assessed(claims_client, monkeypatch):
    """A client with payroll and no run must still appear on the page.

    Under the pipeline model a client the sweep has not reached is a gap to
    close, not a bucket it belongs in — and it still has to be visible while the
    gap is open. A client absent from the page whose stated job is "who do I
    call" is the one client nobody calls, which is worse than showing $0 because
    at least $0 is visible. This is the Northwind case: real payroll, five
    locations, invisible purely because no run had written a claim row for it.
    """
    import api.claims as claims_api

    monkeypatch.setattr(claims_api, "_client_book", lambda: [
        {"account_id": 1001, "name": "Candle Bottle"},
        {"account_id": 2002, "name": "Northwind Care Systems"},
    ])
    _record(claims_client, client_id=1001, tax_year=2023, status="assessed", identified_usd="500")

    body = claims_client.get("/api/v2/portfolio").json()
    rows = {item["client_id"]: item for item in body["items"]}

    assert 2002 in rows, "a client with no claim row must still be on the page"
    northwind = rows[2002]
    assert northwind["status"] == "not_assessed"
    assert northwind["effective_outcome"] == "not_assessed"
    assert northwind["client_name"] == "Northwind Care Systems"

    # Null, never zero. Zero reads as "we looked and found nothing"; this client
    # has not been looked at, and the two must not render alike.
    assert northwind["identified_usd"] is None
    assert northwind["gap_jobs"] is None

    # The denominator the page needs to say "2 clients · 1 assessed".
    assert body["total_clients"] == 2
    assert body["assessed_clients"] == 1
    assert body["unassessed_clients"] == 1


def test_v2_portfolio_unassessed_clients_survive_a_dollar_sort(claims_client, monkeypatch):
    """Sorting by value must not make an unassessed client disappear."""
    import api.claims as claims_api

    monkeypatch.setattr(claims_api, "_client_book", lambda: [
        {"account_id": 1001, "name": "Candle Bottle"},
        {"account_id": 2002, "name": "Northwind Care Systems"},
    ])
    _record(claims_client, client_id=1001, tax_year=2023, status="assessed", identified_usd="500")

    body = claims_client.get("/api/v2/portfolio?sort=identified_usd&order=desc").json()

    assert 2002 in {item["client_id"] for item in body["items"]}


def test_v2_portfolio_an_unassessed_client_is_not_an_opportunity(claims_client, monkeypatch):
    """`not_assessed` is not `unclaimed`. We have not looked, so we cannot say."""
    import api.claims as claims_api

    monkeypatch.setattr(claims_api, "_client_book", lambda: [
        {"account_id": 1001, "name": "Candle Bottle"},
        {"account_id": 2002, "name": "Northwind Care Systems"},
    ])
    _record(claims_client, client_id=1001, tax_year=2023, status="assessed", identified_usd="500")

    unclaimed = claims_client.get("/api/v2/portfolio?outcome=unclaimed").json()
    assert 2002 not in {item["client_id"] for item in unclaimed["items"]}

    # But asking for exactly that state must surface it.
    never = claims_client.get("/api/v2/portfolio?status=not_assessed").json()
    assert 2002 in {item["client_id"] for item in never["items"]}


# -------------------------------------------------- the declining overlay
#
# The partner's §2 asks for "clients whose employment levels are trending downward"
# and "companies at risk of losing credits". No single claim can answer it: a
# trend is a statement about several years and every row in the book is one
# cell. So the reading is taken across the client's history and applied OVER
# the cell band — and only ever downward.


def _history(client, client_id, years):
    """Record one claim per year for a client. `years` is (year, headcount, $)."""
    for tax_year, headcount, identified in years:
        _record(
            client,
            client_id=client_id,
            claim_id=f"{client_id}-{tax_year}",
            tax_year=tax_year,
            identified_usd=identified,
            average_headcount=headcount,
            base_average_headcount=40.0,
            threshold_jobs=2.0,
        )


def test_a_client_shedding_jobs_no_longer_reads_as_settled(claims_client):
    """The reading that matters. Halloway is the live case.

    It peaked at 100.75 in TY2022 and has fallen every year since, and the
    cell-level band calls it `settled` — "Nothing outstanding" — on a client
    shedding forty jobs. That is exactly backwards.
    """
    _history(claims_client, 2004, [
        (2021, 85.75, "163345"),
        (2022, 100.75, "45500"),
        (2023, 92.84, "0"),
        (2024, 70.34, "0"),
        (2025, 61.42, "0"),
    ])

    rows = {i["client_id"]: i for i in claims_client.get("/api/v2/portfolio").json()["items"]}
    row = rows[2004]

    assert row["priority_band"] == "declining"
    assert row["priority_rank"] == 2
    assert row["trend"]["years_falling"] == 3
    assert row["trend"]["peak_tax_year"] == 2022


def test_declining_never_displaces_a_finding_against_a_filed_return(claims_client):
    """`exposed` outranks it, and — more importantly — must not be renamed to it.

    Exposure means we have looked at something somebody filed and believe it is
    wrong. Declining is a forecast. A client can be both, and when it is, the
    row says the thing that has already happened.
    """
    _history(claims_client, 2004, [
        (2021, 85.75, "163345"),
        (2022, 100.75, "45500"),
        (2024, 70.34, "0"),
    ])
    # A filed return we cannot substantiate, in the year the band will choose.
    _record(
        claims_client, client_id=2004, claim_id="2004-2025", tax_year=2025,
        status="claimed", identified_usd="1000", claimed_usd="90000",
        average_headcount=61.42, base_average_headcount=40.0, threshold_jobs=2.0,
    )

    rows = {i["client_id"]: i for i in claims_client.get("/api/v2/portfolio").json()["items"]}
    row = rows[2004]

    assert row["priority_band"] == "exposed"
    # The trend is still reported — it is a real fact about the client — it just
    # does not get to be the headline.
    assert row["trend"]["declining"] is True


def test_the_trend_survives_the_year_filter(claims_client):
    """A TREND IS NOT A CELL, and the page is always scoped to a year.

    The book takes `year` from the shell, so every real page load filters the
    claims to one tax year — and one year has no direction. Reading the trend
    off the filtered slice made Halloway read `settled` on every scoped load
    while reading `declining` only on the unscoped call nobody makes.
    """
    _history(claims_client, 2004, [
        (2021, 85.75, "163345"),
        (2022, 100.75, "45500"),
        (2023, 92.84, "0"),
        (2024, 70.34, "0"),
        (2025, 61.42, "0"),
    ])

    scoped = claims_client.get("/api/v2/portfolio?year=2025").json()
    row = {i["client_id"]: i for i in scoped["items"]}[2004]

    assert row["tax_year"] == 2025, "the CELL is still the year that was asked for"
    assert row["priority_band"] == "declining"
    assert row["trend"]["years_falling"] == 3


def test_a_client_that_recovered_carries_no_trend_at_all(claims_client):
    """Not `declining: false`. An absent trend and a flat one are different."""
    _history(claims_client, 2002, [
        (2023, 55.10, "20000"),
        (2024, 59.25, "0"),
        (2025, 71.42, "0"),
    ])

    rows = {i["client_id"]: i for i in claims_client.get("/api/v2/portfolio").json()["items"]}
    assert "trend" not in rows[2002]
    assert rows[2002]["priority_band"] != "declining"


# --------------------------------------------------------- the footprint


def test_the_book_carries_where_each_client_operates(claims_client, monkeypatch):
    """The partner's §2 map filter needs states on the row, not a second endpoint.

    Held and priceable are reported separately because they are different
    claims. A state we have payroll in but no authored statute for is a real gap
    in coverage, and the map is the one screen that shows it.
    """
    import api.claims as claims_api

    monkeypatch.setattr(claims_api, "_footprint", lambda: {2001: ["GA", "NC", "SC"]})
    monkeypatch.setattr(claims_api, "_priceable_states", lambda: {"GA", "SC"})
    _record(claims_client, client_id=2001, tax_year=2023, identified_usd="500")

    rows = {i["client_id"]: i for i in claims_client.get("/api/v2/portfolio").json()["items"]}

    assert rows[2001]["states"] == ["GA", "NC", "SC"]
    assert rows[2001]["priceable_states"] == ["GA", "SC"]


def test_an_unassessed_client_still_has_a_footprint(claims_client, monkeypatch):
    """Where a client operates is a fact about payroll, not about having run it.

    Dropping it here would take the unassessed clients off the map — the ones a
    footprint filter most needs to surface.
    """
    import api.claims as claims_api

    monkeypatch.setattr(claims_api, "_client_book", lambda: [
        {"account_id": 1001, "name": "Candle Bottle"},
        {"account_id": 2002, "name": "Northwind Care Systems"},
    ])
    monkeypatch.setattr(claims_api, "_footprint", lambda: {2002: ["GA", "TN"]})
    monkeypatch.setattr(claims_api, "_priceable_states", lambda: {"GA", "TN"})
    _record(claims_client, client_id=1001, tax_year=2023, identified_usd="500")

    rows = {i["client_id"]: i for i in claims_client.get("/api/v2/portfolio").json()["items"]}
    assert rows[2002]["states"] == ["GA", "TN"]


# --------------------------------------------------------------- engagement


def test_an_out_of_scope_gap_is_not_an_opportunity(claims_client):
    """"Unclaimed — not our mandate" must not read as "unclaimed — call them"."""
    _record(claims_client, program_code="FED_WOTC", identified_usd="80000")
    claims_client.put("/api/claims/engagement", json={
        "client_id": 1001, "program_code": "FED_WOTC", "scope": "out_of_scope",
        "note": "Client handles WOTC in-house.",
    })

    cells = claims_client.get("/api/claims/coverage/1001").json()["cells"]
    wotc = next(c for c in cells if c["program_code"] == "FED_WOTC")

    assert wotc["engagement_scope"] == "out_of_scope"
    assert wotc["outcome"] == "out_of_scope", "not 'unclaimed'"


def test_an_in_scope_gap_stays_an_opportunity(claims_client):
    _record(claims_client, identified_usd="80000")
    claims_client.put("/api/claims/engagement", json={
        "client_id": 1001, "program_code": "GA_JTC", "scope": "in_scope",
    })

    cells = claims_client.get("/api/claims/coverage/1001").json()["cells"]
    assert cells[0]["outcome"] == "unclaimed"


def test_engagement_scope_supersedes(claims_client):
    for scope in ("prospective", "in_scope"):
        claims_client.put("/api/claims/engagement", json={
            "client_id": 1001, "program_code": "GA_JTC", "scope": scope,
        })

    engagements = claims_client.get("/api/claims/coverage/1001").json()["engagements"]
    assert len(engagements) == 1
    assert engagements[0]["scope"] == "in_scope"


# --------------------------------------------------------------- vocabulary


def test_the_lifecycle_vocabulary_is_published(claims_client):
    """So the UI does not keep its own drifting copy of the enum."""
    body = claims_client.get("/api/claims/lifecycle").json()

    statuses = {s["value"]: s["is_claimed"] for s in body["statuses"]}
    assert statuses["assessed"] is False
    assert statuses["certified"] is True

    provenance = {p["value"]: p["verified"] for p in body["provenance"]}
    assert provenance["client_asserted"] is False
    assert provenance["authority_confirmed"] is True

    assert "over_claimed" in body["outcomes"]
    assert "out_of_scope" in body["engagement_scopes"]


# ----------------------------------------------------------------- assessment


def test_assessment_records_what_the_engine_computed(claims_client):
    """The step that turns the coverage matrix into a computed artifact."""
    body = claims_client.post("/api/claims/assess", json={"client_id": 1001}).json()

    assert body["assessed"], "the reference client has priceable Georgia years"
    for cell in body["assessed"]:
        assert cell["provenance"] == "computed"
        assert cell["status"] == "assessed"
        assert cell["rule_pack_version"]

    # And it landed in the store, not just the response.
    coverage = claims_client.get("/api/claims/coverage/1001").json()
    assert len(coverage["cells"]) == len(body["assessed"])


def test_assessment_agrees_with_the_scope_selector(claims_client):
    """Two parts of one system must not disagree about what can be priced.

    `/api/scope` disables a program with no authored years. If assessment
    computed one anyway the matrix would show a figure the selector says is
    impossible — a confident number under no particular year's statute.
    """
    scope = claims_client.get("/api/scope").json()
    calculable = {p["program_code"] for p in scope["programs"] if p["calculable"]}

    body = claims_client.post("/api/claims/assess", json={"client_id": 1001}).json()
    assessed = {c["program_code"] for c in body["assessed"]}

    assert assessed <= calculable, (
        f"assessed {assessed - calculable} that scope says cannot be priced"
    )


def test_an_unpriceable_program_is_declined_by_name(claims_client):
    body = claims_client.post("/api/claims/assess", json={"client_id": 1001}).json()

    reasons = {d["reason"] for d in body["declined"]}
    assert "program_not_year_scoped" in reasons
    for entry in body["declined"]:
        assert entry["program_code"]
        assert entry["detail"], "a decline must say why"


def test_reassessment_refreshes_the_figure_without_erasing_a_decision(claims_client):
    """A recalculation is new EVIDENCE, not a new decision.

    Someone declined this cell. Re-running the engine must not quietly reset it
    to `assessed` and re-propose something the client has already answered.
    """
    claims_client.post("/api/claims/assess", json={"client_id": 1001})
    cells = claims_client.get("/api/claims/coverage/1001").json()["cells"]
    target = cells[0]

    claims_client.post(
        f"/api/claims/cell/1001/{target['program_code']}/{target['tax_year']}/transition",
        json={
            "status": "declined",
            "decided_by": "lead@example.com",
            "decline_reason": "Client takes the R&D credit instead.",
        },
    )

    claims_client.post("/api/claims/assess", json={"client_id": 1001})

    after = claims_client.get(
        f"/api/claims/cell/1001/{target['program_code']}/{target['tax_year']}"
    ).json()["current"]

    assert after["status"] == "declined", "the decision survived the recalculation"
    assert after["decline_reason"] == "Client takes the R&D credit instead."


def test_assessing_an_unknown_client_is_never_someone_elses_payroll(claims_client):
    """The dangerous one: assessment WRITES.

    Single-tenant sources used to ignore the account id, so assessing client
    999999 would have recorded claims against 999999 computed from client
    1001's payroll — wrong figures, persisted, under the wrong company's name.
    """
    response = claims_client.post("/api/claims/assess", json={"client_id": 999999})
    assert response.status_code == 404

    # And nothing was written for the impostor.
    assert claims_client.get("/api/claims/coverage/999999").json()["cells"] == []


def test_a_mismatched_tenant_reads_empty_not_default(claims_client):
    """The root fix, at the source rather than at each call site."""
    from api._payperiods import configured_account_id, load_pay_periods

    assert load_pay_periods(configured_account_id()), "the configured tenant has rows"
    assert load_pay_periods(999999) == [], "any other tenant has none"


# ------------------------------------------------- the jobs reasoning itself
#
# `/api/claims/proximity` is gone — the "who is closest" question is now a
# `PriorityBand` on `/api/v2/portfolio`, and its rules are pinned in
# tests/test_priority_bands.py. What survives here is the thing that made the
# question answerable at all: the assessment recording WHY a figure is what it
# is, not just the figure.


def test_assessment_records_the_jobs_reasoning_not_just_the_figure(claims_client):
    """Without it a $0 cell cannot be told from a $0 cell one hire away."""
    claims_client.post("/api/claims/assess", json={"client_id": 1001})
    cells = claims_client.get("/api/claims/coverage/1001").json()["cells"]

    assert cells
    for cell in cells:
        assert cell["average_headcount"] is not None
        assert cell["base_average_headcount"] is not None
        assert cell["threshold_jobs"] is not None
        assert cell["net_new_jobs"] is not None

