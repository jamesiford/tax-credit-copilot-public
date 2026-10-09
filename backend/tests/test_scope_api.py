"""The scope endpoint: which clients, which programs, which years.

Scope is the dimension every calculating screen renders inside, so the contract
matters more than most. Two properties are load-bearing:

**Jurisdiction is derived.** A program belongs to exactly one jurisdiction. The
API returns it *on the program* rather than as a separate axis, because two
independent axes let an operator select a contradiction ("Georgia" + "Federal
WOTC") that has no meaning.

**Years are enumerated, never ranged.** `authored_years` comes from the rule
packs on disk. A UI that offered a year the engine cannot price would produce a
confident-looking empty screen, which is the failure mode this project keeps
running into.
"""
from __future__ import annotations


def test_scope_lists_clients_programs_and_years(client):
    body = client.get("/api/scope").json()

    assert body["clients"], "there is always at least one tenant"
    assert body["programs"], "rule packs exist"
    assert body["data_source"] in {"csv", "fabric", "lakehouse"}

    for entry in body["clients"]:
        assert isinstance(entry["account_id"], int)
        assert entry["name"]
        assert isinstance(entry["synthetic"], bool)


def test_every_program_carries_its_own_jurisdiction(client):
    """Derived, not a separate axis — see the module docstring."""
    body = client.get("/api/scope").json()

    for program in body["programs"]:
        jurisdiction = program["jurisdiction"]
        assert jurisdiction["level"] in {"state", "federal", "local"}
        if jurisdiction["level"] == "state":
            assert len(jurisdiction["code"]) == 2, program["program_code"]

    assert "jurisdictions" not in body, (
        "jurisdiction must not be offered as an independent axis"
    )


def test_georgia_is_calculable_across_its_authored_years(client):
    body = client.get("/api/scope").json()
    ga = next(p for p in body["programs"] if p["program_code"] == "GA_JTC")

    assert ga["calculable"] is True
    assert ga["year_scoped"] is True
    assert 2023 in ga["authored_years"], "the certified year must be priceable"
    assert 2027 not in ga["authored_years"], "TY2027 statute is not authored"
    # TY2026 is authored as a labelled placeholder, and the scope says so.
    assert ga["placeholder_years"] == [2026]
    assert ga["authored_years"] == sorted(ga["authored_years"])


def test_a_program_without_authored_years_says_why(client):
    """Present but disabled, with a reason. Omitting it would read as 'no such
    program', which is a different and wrong statement."""
    body = client.get("/api/scope").json()
    unpriceable = [p for p in body["programs"] if not p["calculable"]]

    assert unpriceable, "not every state is year-scoped yet"
    for program in unpriceable:
        assert program["authored_years"] == []
        assert program["not_calculable_reason"]
        assert "ADR-005" in program["not_calculable_reason"]


def test_default_window_is_a_base_year_plus_five(client):
    years = client.get("/api/scope").json()["years"]

    assert years["window_years"] == 6
    assert len(years["default_window"]) <= 6
    assert years["default_window"] == sorted(years["default_window"])
    if years["default_window"]:
        assert years["default_window"][-1] == years["latest"]
    assert set(years["default_window"]) <= set(years["authored"]), (
        "the default window must not offer a year with no authored statute"
    )


def test_client_scope_separates_payroll_years_from_priceable_ones(client):
    """"We hold your 2026 payroll but cannot price it yet" is a real answer."""
    account_id = client.get("/api/scope").json()["clients"][0]["account_id"]
    body = client.get(f"/api/scope/client/{account_id}").json()

    assert body["rows"] > 0
    assert body["states"], "a client with payroll works somewhere"
    assert body["payroll_years"] == sorted(body["payroll_years"])

    priceable = set(body["calculable_years"])
    held = set(body["payroll_years"])
    unpriceable = set(body["payroll_without_statute"])

    assert priceable <= held, "cannot price a year we hold no payroll for"
    assert priceable.isdisjoint(unpriceable), "a year is one or the other"
    assert priceable | unpriceable == held, "every payroll year is accounted for"
    # An open year is a calculable one still running — read to date, never claimed.
    assert set(body["open_years"]) <= priceable


def test_unknown_client_is_a_404_not_an_empty_scope(client):
    response = client.get("/api/scope/client/999999")
    assert response.status_code == 404
    assert "999999" in response.json()["detail"]


def test_unknown_client_never_returns_another_tenants_payroll(client):
    """The dangerous version of the above.

    Single-tenant fixture sources ignore the account id, so a naive
    implementation answers 200 with the DEFAULT tenant's rows under the
    requested client's name. That is one client's figures presented as another's
    — the worst outcome available on a screen whose numbers reach a tax return.
    """
    known = {c["account_id"] for c in client.get("/api/scope").json()["clients"]}
    real = client.get(f"/api/scope/client/{min(known)}").json()

    impostor = client.get("/api/scope/client/424242")
    assert impostor.status_code == 404
    assert str(real["rows"]) not in impostor.text


def test_state_resolution_handles_both_row_shapes():
    """The CSV fixture encodes state in the Worksite_ID prefix; the lakehouse
    projection carries Work_State. One reading, or a row is visible to one
    caller and invisible to another — which is how a screen silently empties.
    """
    from api._payperiods import row_state, states_present

    assert row_state({"Worksite_ID": "GA_SAV_DC"}) == "GA"
    assert row_state({"Work_State": "ga", "Worksite_ID": "GA_SAV_DC"}) == "GA"
    assert row_state({"Work_State": "NC", "Worksite_ID": "GA_SAV_DC"}) == "NC"

    # Nothing resolvable must return empty rather than a wrong guess.
    assert row_state({"Worksite_ID": "SAVANNAH_DC"}) == ""
    assert row_state({"Worksite_ID": ""}) == ""
    assert row_state({}) == ""

    assert states_present([
        {"Worksite_ID": "GA_A"}, {"Worksite_ID": "NC_B"}, {"Worksite_ID": "GA_C"},
    ]) == ["GA", "NC"]


def test_load_pay_periods_takes_an_account_parameter():
    """Scope is a property of the request, not of the deployment.

    Before B3 the tenant came only from FLEX_ACCOUNT_ID, so switching client in
    the UI would have needed an environment change.
    """
    import inspect

    from api._payperiods import load_pay_periods, require_pay_periods

    assert "account_id" in inspect.signature(load_pay_periods).parameters
    assert "account_id" in inspect.signature(require_pay_periods).parameters
