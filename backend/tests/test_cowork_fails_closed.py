"""Cowork fails closed: only a positively first-party channel is handed employee rows. [RM-02]

The rule is on the API itself, so it holds with no gateway in front: a person's own token sent
straight to the API, an agent that names no channel, an unknown one, `cowork`, `api-test` or a
delegated assurance are all treated like Cowork, and are refused employee-level rows unless the
caller is a writer. The refusal happens before the source is read, and `invoke` repeats it on every
finished result so a capability that forgot the pre-run check cannot leak.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from application.capabilities import registry
from application.capabilities.data_access import is_cowork, is_first_party, refuse_user_lane
from application.capabilities.data_catalog import data_catalog
from application.capabilities.envelope import Block, ToolResult
from application.capabilities.errors import DataQueryRefused
from application.capabilities.invoke import CapabilityFailure, invoke
from bootstrap.channel_wiring import set_writer_entitlement
from application.identity import ANONYMOUS, ActingUser, Principal, PRINCIPAL_AGENT
from tests.data_caps_fixture import READER_OID, WRITER_OID, data_service, person  # noqa: F401 - fixture
from tests.test_agent_principal import OTHER_OID, api, entra  # noqa: F401 - fixtures
from tests.test_auth import mint
from tests.test_capabilities_api import agent_headers, post, user_headers
from tests.test_data_capabilities_api import EMPLOYEES, served  # noqa: F401 - fixture

REFUSED = "employee_level_not_available"
ROOT = Path(__file__).resolve().parents[1]


class Writers:
    """Anybody on the list is entitled to make changes; the signed-in test person is on it only when asked."""

    def __init__(self, *oids: str) -> None:
        self.oids = set(oids)

    def is_writer(self, oid: str) -> bool:
        return oid in self.oids


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def refused(response) -> bool:
    return response.status_code == 403 and response.json()["error"]["code"] == REFUSED


# ----------------------------------------------- a token sent straight to the API


def test_a_persons_own_token_sent_straight_to_the_api_is_refused_employee_rows(served, api):  # noqa: F811
    set_writer_entitlement(Writers())
    assert refused(post(api, "data_query", EMPLOYEES, user_headers()))
    assert served.calls == [], "refused before the source was read"


def test_a_forged_channel_header_on_a_persons_token_changes_nothing(served, api):  # noqa: F811
    from tests.test_agent_principal import acting_header

    set_writer_entitlement(Writers())
    forged = {**user_headers(), "X-TCC-Acting-User": acting_header(channel="teams", oid=OTHER_OID)}
    assert refused(post(api, "data_query", EMPLOYEES, forged))
    assert served.calls == []


def test_a_writer_with_their_own_token_is_served(served, api):  # noqa: F811
    set_writer_entitlement(Writers(WRITER_OID))
    response = post(api, "data_query", EMPLOYEES, bearer(mint(oid=WRITER_OID)))
    assert response.status_code == 200 and response.json()["user_only_facts"] == ["rows"]


def test_a_persons_token_may_still_ask_for_aggregates(served, api):  # noqa: F811
    set_writer_entitlement(Writers())
    aggregate = {"dataset": "unit_year_master", "client_id": 1001, "select": ["worksite_id"],
                 "measures": [{"column": "*", "agg": "count", "as": "n"}]}
    assert post(api, "data_query", aggregate, user_headers()).status_code == 200


# ---------------------------------------------- the gateway's assertion, as the API reads it


@pytest.mark.parametrize("channel", ["cowork", "api-test", None])
def test_an_agent_that_is_not_first_party_is_refused_employee_rows(served, api, channel):  # noqa: F811
    set_writer_entitlement(Writers())
    assert refused(post(api, "data_query", EMPLOYEES, agent_headers(channel=channel, oid=OTHER_OID)))
    assert served.calls == []


def test_a_channel_the_api_does_not_know_is_a_400_before_anything_runs(served, api):  # noqa: F811
    response = post(api, "data_query", EMPLOYEES, agent_headers(channel="carrier-pigeon", oid=OTHER_OID))
    assert response.status_code == 400 and served.calls == []


def test_a_first_party_channel_claiming_a_delegated_assurance_is_not_first_party(served, api):  # noqa: F811
    set_writer_entitlement(Writers())
    assert refused(post(api, "data_query", EMPLOYEES, agent_headers(channel="teams", assurance="delegated", oid=OTHER_OID)))


@pytest.mark.parametrize("channel", ["teams", "m365-copilot"])
def test_a_first_party_channel_receives_the_persons_lane(served, api, channel):  # noqa: F811
    set_writer_entitlement(Writers())
    response = post(api, "data_query", EMPLOYEES, agent_headers(channel=channel, oid=OTHER_OID))
    assert response.status_code == 200 and response.json()["user_only_facts"] == ["rows"]


@pytest.mark.parametrize("channel", ["cowork", "api-test", None])
def test_a_writer_is_served_whatever_the_channel(served, api, channel):  # noqa: F811
    set_writer_entitlement(Writers(WRITER_OID))
    assert post(api, "data_query", EMPLOYEES, agent_headers(channel=channel, oid=WRITER_OID)).status_code == 200


# -------------------------------------------------------- who counts as first-party


def acting(**overrides) -> Principal:
    user = ActingUser(oid=READER_OID, **{"channel": "teams", "assurance": "channel-asserted", **overrides})
    return Principal(oid="gateway", principal_type=PRINCIPAL_AGENT, acting_for=user, authenticated=True)


@pytest.mark.parametrize("principal, first_party", [
    (acting(), True),
    (acting(channel="m365-copilot"), True),
    (acting(channel="cowork"), False),
    (acting(channel="api-test"), False),
    (acting(channel=None), False),
    (acting(channel="Teams"), False),
    (acting(channel="teams", assurance="delegated"), False),
    (Principal(oid=READER_OID, authenticated=True), False),
    (Principal(oid="gateway", principal_type=PRINCIPAL_AGENT, authenticated=True), False),
    (ANONYMOUS, False),
], ids=["teams", "m365-copilot", "cowork", "api-test", "no-channel", "wrong-case", "delegated-teams", "person", "agent-no-user", "anonymous"])
def test_first_party_is_positive_and_everything_else_is_cowork_like(principal, first_party):
    assert is_first_party(principal) is first_party and is_cowork(principal) is (not first_party)


def test_the_catalog_tells_every_cowork_like_caller_that_employee_rows_are_unavailable(data_service):  # noqa: F811
    for principal in (person(channel="cowork"), person(channel=None), person(channel="api-test")):
        assert any("Cowork" in n for n in data_catalog(principal).facts["notes"])
    assert not any("Cowork" in n for n in data_catalog(person(channel="teams")).facts["notes"])


# ------------------------------------------------ the API's second wall, in invoke


def user_lane_result() -> ToolResult:
    return ToolResult(tool="book_rank", facts={"rows": [{"x": 1}]}, user_only_facts=("rows",),
                      blocks=(Block("table", rows=(("x",), ("1",)), audience="user"),))


@pytest.fixture
def leaky_capability(monkeypatch):
    """A capability that forgot the pre-run check and returns a person-only lane."""
    monkeypatch.setattr(registry, "get", lambda tool: (lambda *args, **kwargs: user_lane_result()))
    set_writer_entitlement(Writers(WRITER_OID))
    yield
    set_writer_entitlement(None)


def test_invoke_refuses_a_user_lane_result_for_a_caller_that_is_not_first_party(leaky_capability):
    for principal in (person(READER_OID, "cowork"), person(READER_OID, None), person(READER_OID, "api-test"), ANONYMOUS):
        with pytest.raises(CapabilityFailure) as failure:
            invoke("book_rank", {}, principal)
        assert failure.value.status == 403 and failure.value.code == REFUSED


def test_invoke_lets_the_same_result_through_to_a_first_party_channel_and_to_a_writer(leaky_capability):
    assert invoke("book_rank", {}, person(READER_OID, "teams")).user_only_facts == ("rows",)
    assert invoke("book_rank", {}, person(READER_OID, "m365-copilot")).user_only_facts == ("rows",)
    assert invoke("book_rank", {}, person(WRITER_OID, "cowork")).user_only_facts == ("rows",)
    assert invoke("book_rank", {}, person(WRITER_OID, None)).user_only_facts == ("rows",)


def test_an_unknown_audience_word_is_person_only_and_refused_the_same_way():
    odd = ToolResult(tool="book_rank", facts={}, blocks=(Block("table", rows=(("x",),), audience="user"),))
    with pytest.raises(DataQueryRefused):
        refuse_user_lane(person(READER_OID, "cowork"), odd)
    refuse_user_lane(person(READER_OID, "teams"), odd)
    refuse_user_lane(person(READER_OID, "cowork"), ToolResult(tool="book_rank", facts={}))


# ------------------------------------------------------------------ the rule, kept


def _compares_to_a_channel_name(source: str) -> bool:
    """True if the code compares something to the string "cowork" (a negative test for who may see rows)."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare):
            literals = [n.value for n in [node.left, *node.comparators] if isinstance(n, ast.Constant)]
            if "cowork" in literals:
                return True
    return False


def test_nothing_decides_who_may_see_rows_by_comparing_a_channel_to_cowork():
    """A negative test ("is it Cowork?") is how an unknown channel was once let through. The decision is
    `ActingUser.is_first_party`, positive, in one place."""
    for folder in ("application", "channel", "api"):
        for path in (ROOT / folder).rglob("*.py"):
            assert not _compares_to_a_channel_name(path.read_text(encoding="utf-8")), f"{path.name} compares a channel to 'cowork'"


def test_the_detector_notices_a_negative_channel_test():
    assert _compares_to_a_channel_name('if acting.channel == "cowork":\n    pass')
    assert not _compares_to_a_channel_name('if not acting.is_first_party:\n    pass')


def test_the_api_and_the_gateway_use_the_one_first_party_definition():
    texts = {name: (ROOT / name).read_text(encoding="utf-8") for name in ("channel/lane_guard.py", "application/capabilities/data_access.py")}
    assert "is_first_party" in texts["channel/lane_guard.py"] and "is_first_party" in texts["application/capabilities/data_access.py"]
    assert "refuse_user_lane(principal, result)" in (ROOT / "application/capabilities/invoke.py").read_text(encoding="utf-8")
    identity = (ROOT / "application/identity.py").read_text(encoding="utf-8")
    assert "FIRST_PARTY_CHANNELS" in identity and '("teams", "m365-copilot")' not in identity
