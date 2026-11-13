"""Optional `program_code` on every read capability that took only a state, and what it does and does not change. [F07.5]

A state with several programs asks which (the F04c rule for reads); naming the program answers for it and says so. A state with one
program answers exactly as it always did, with no new key.
"""
from __future__ import annotations

import pytest

from application.capabilities import catalog, registry
from application.capabilities.errors import CapabilityError
from tests import two_program_world as world
from tests.two_program_world import ALPHA, BETA, CLIENT, STATE

# `simulate` is not here: its function is at the 9-argument ceiling of the code-standards ratchet and the schema/parameter contract forbids
# `**kwargs`, so adding a tenth parameter needs a human decision (see the F07 decision log). Its query and route already take program_code.
STATE_KEYED = ("client_eligibility", "client_trend", "client_at_risk", "calc_walkthrough", "employee_drill", "findings_list")


@pytest.fixture()
def zz(tmp_path, monkeypatch):
    from bootstrap import wiring
    from tests.data_engine_fixture import SqliteGoldReader, SqliteWarehouse

    world.install(tmp_path, monkeypatch)
    monkeypatch.setattr(wiring, "get_gold_reader", lambda: SqliteGoldReader(SqliteWarehouse()))  # an empty store: nothing run yet
    return None


@pytest.mark.parametrize("tool", STATE_KEYED)
def test_the_catalog_offers_an_optional_program_code_and_the_function_accepts_it(tool):
    import inspect

    spec = catalog.get(tool)
    prop = spec.schema["properties"]["program_code"]
    assert prop["type"] == "string" and prop["maxLength"] == 64
    assert "program_code" not in spec.schema.get("required", [])
    assert "program_code" in inspect.signature(registry.FUNCTIONS[tool]).parameters


def test_a_state_with_several_programs_asks_which_and_names_both(zz):
    with pytest.raises(CapabilityError) as asked:
        registry.call("client_eligibility", client_id=CLIENT, tax_year=2025, state=STATE)
    assert ALPHA in str(asked.value) and BETA in str(asked.value) and "program_code" in str(asked.value)


def test_naming_the_program_answers_for_it_and_says_which_it_used(zz):
    result = registry.call("client_eligibility", client_id=CLIENT, tax_year=2025, program_code=BETA)
    assert result.facts["program_code"] == BETA
    other = registry.call("client_eligibility", client_id=CLIENT, tax_year=2025, state=STATE, program_code=ALPHA.lower())
    assert other.facts["program_code"] == ALPHA


def test_a_program_that_disagrees_with_the_state_is_refused(zz):
    with pytest.raises(CapabilityError, match="not GA"):
        registry.call("client_eligibility", client_id=CLIENT, tax_year=2025, state="GA", program_code=BETA)


def test_the_walkthrough_and_trend_name_the_program_they_used(zz):
    from application.capabilities.errors import NotCalculated

    with pytest.raises(NotCalculated):
        registry.call("calc_walkthrough", client_id=CLIENT, tax_year=2025, program_code=BETA)  # asked for BETA, nothing run yet
    trend = registry.call("client_trend", client_id=CLIENT, program_code=BETA)
    assert trend.facts["program_code"] == BETA


def test_a_single_program_state_answers_exactly_as_before_with_no_new_key(zz):
    result = registry.call("client_eligibility", client_id=CLIENT + 1, tax_year=2024, state="GA")
    assert "program_code" not in result.facts
    assert "program_code" not in registry.call("client_trend", client_id=CLIENT + 1).facts


def test_the_findings_route_takes_a_program_that_must_agree_with_the_state(zz):
    from fastapi.testclient import TestClient

    import main

    http = TestClient(main.app)
    base = f"/api/findings/{CLIENT}/2025"
    disagree = http.get(base, params={"state": "GA", "program_code": BETA})
    assert disagree.status_code == 422 and "not GA" in disagree.json()["detail"]
    unknown = http.get(base, params={"program_code": "NOPE"})
    assert unknown.status_code == 404 and "no active program" in unknown.json()["detail"]
    named = http.get(base, params={"program_code": BETA.lower()})
    assert named.status_code == 404 and "No payroll" in named.json()["detail"], "the program passed its checks and the read ran for its state"
