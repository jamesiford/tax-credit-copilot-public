"""The tool runner's rules, each on its own. [CH-08]"""
from __future__ import annotations

import asyncio
import json

from app.core.maf_agent import function_tools
from app.core.settings import OrchestratorConfigError, load_settings
from app.core.state import ConversationState
from app.core.tools import ToolRunner, model_tools, offered_schema, years_in
from application.capabilities import catalog
from orch_harness import ENV, USER_OID, FakeClock, FakeGateway, identity

import pytest


def runner(question: str, gateway: FakeGateway | None = None, state: ConversationState | None = None, **over):
    gateway = gateway or FakeGateway()
    state = state or ConversationState()
    kwargs = dict(max_calls=6, confirm_ttl_seconds=300, clock=FakeClock())
    kwargs.update(over)
    return ToolRunner(gateway.client(), identity(), state, question, **kwargs), gateway, state


def run(r, name, args=None):
    return asyncio.run(r.run(name, args or {}))


def test_years_are_read_from_the_readers_words():
    assert years_in("TY2023 versus 2022, then 2023 again") == [2023, 2022]
    assert years_in("hired 15000 people in 20230") == []


def test_commit_tools_plumbing_and_the_resolver_are_not_tools_a_model_may_name():
    names = set(model_tools())
    assert not {n for n in names if n.endswith("_commit")}
    assert not {"verify_figures", "claim_package_redeem", "client_resolve", "employee_drill"} & names
    assert {s.name for s in catalog.offered() if s.kind == catalog.WRITE_PREPARE} <= names


def test_no_maf_tool_is_a_commit_and_the_model_is_shown_no_client_id():
    r, *_ = runner("anything")
    tools = function_tools(r)
    assert {t.name for t in tools} == set(model_tools())
    assert not [t for t in tools if t.name.endswith("_commit")]
    for spec in model_tools().values():
        shown = offered_schema(spec)
        assert "client_id" not in shown["properties"] and "client_id" not in shown["required"]
        assert "tax_year" not in shown["required"]


def test_what_the_model_sees_of_a_result_names_the_facts_and_holds_no_value():
    r, gateway, _ = runner("What is Cascade's credit for 2023 under Min-Max?")
    seen = run(r, "client_eligibility", {"tax_year": 2023})
    text = json.dumps(seen)
    assert seen["ok"] and "client_eligibility_min_max.credit.annual_credit_usd" in text
    for value in ("227605", "227,605", "1138025", "375.53"):
        assert value not in text


def test_a_prepared_changes_token_is_kept_by_the_runner_and_never_shown_to_anyone_else():
    r, gateway, state = runner("Mark Cascade's GA_JTC engagement as in scope")
    seen = run(r, "engagement_set_prepare", {"program_code": "GA_JTC", "scope": "in_scope"})
    assert "tok-1" not in json.dumps(seen) and r.pending is not None and r.pending.token == "tok-1"
    assert "confirmation" not in r.runs[0].facts


def test_the_tool_budget_is_enforced_and_a_refused_name_is_recorded_not_run():
    r, gateway, _ = runner("Cascade", max_calls=1)
    assert run(r, "client_trend")["ok"] is True
    assert run(r, "client_situation")["error"] == "tool_budget"
    assert run(r, "engagement_set_commit")["error"] == "unknown_tool" and r.refused == ["engagement_set_commit"]
    assert gateway.tools_called() == ["client_resolve", "client_trend"]


def test_the_client_is_resolved_once_per_turn_not_once_per_tool():
    r, gateway, _ = runner("Cascade 2023")
    run(r, "client_trend")
    run(r, "client_at_risk", {"tax_year": 2023})
    assert gateway.tools_called().count("client_resolve") == 1


def test_one_named_client_selects_it_even_when_the_conversation_was_about_another():
    state = ConversationState(client_id=2002)
    r, gateway, _ = runner("Now Cascade please", state=state)
    run(r, "client_trend")
    assert gateway.calls[-1].args["client_id"] == 2001 and state.client_id == 2001


def test_the_method_is_the_readers_and_defaults_to_both_certified_methods():
    for question, methods in (
        ("Cascade 2023", ["min_max", "pay_period"]), ("Cascade 2023 min-max", ["min_max"]),
        ("Cascade 2023 pay period", ["pay_period"]), ("Cascade 2023 both min-max and pay period", ["min_max", "pay_period"]),
    ):
        r, gateway, _ = runner(question)
        run(r, "client_eligibility", {"tax_year": 2023})
        assert [c.args["method"] for c in gateway.calls if c.tool == "client_eligibility"] == methods, question


def test_the_same_tool_under_two_methods_has_two_labels_so_no_path_collides():
    r, *_ = runner("Cascade 2023")
    run(r, "client_eligibility", {"tax_year": 2023})
    assert [x.label for x in r.runs] == ["client_eligibility_min_max", "client_eligibility_pay_period"]


def test_an_argument_the_catalog_does_not_know_is_refused_before_the_gateway():
    r, gateway, _ = runner("Cascade")
    seen = run(r, "client_trend", {"colour": "red"})
    assert seen["error"] == "invalid_arguments" and "client_trend" not in gateway.tools_called()


def test_the_settings_refuse_half_a_configuration_and_name_every_gap():
    with pytest.raises(OrchestratorConfigError) as exc:
        load_settings({"AI_PROVIDER_CHAIN": "gateway"})
    for name in ("CHANNEL_GATEWAY_URL", "CHANNEL_GATEWAY_AUDIENCE", "TENANT_ID"):
        assert name in str(exc.value)


def test_the_settings_reject_values_that_would_weaken_a_control():
    for bad in ({"CHANNEL_MAX_TOOL_CALLS": "0"}, {"CHANNEL_CONFIRM_TTL_SECONDS": "5"}, {"CHANNEL_NAME": "slack"},
                {"CHANNEL_IDENTITY_SOURCES": "x-agent-user-id"}, {"CHANNEL_GATEWAY_URL": "http://insecure.example"},
                {"AI_PROVIDER_CHAIN": "foundry_connection", "AI_FOUNDRY_CONNECTION_NAME": "c"}):
        with pytest.raises(OrchestratorConfigError):
            load_settings({**ENV, **bad})
    ok = load_settings({**ENV, "CHANNEL_DEBUG_WHOAMI": "true"})
    assert ok.debug_whoami and ok.max_tool_calls == 6 and ok.confirm_ttl_seconds == 300
    assert ok.gateway_scope == "api://gateway-test/.default" and USER_OID
