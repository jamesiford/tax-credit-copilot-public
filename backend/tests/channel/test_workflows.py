"""Whole workflows through the gateway, REST and MCP, against the real capability layer. [CH-11]

W1 (the Monday book review) and W2 (the client credit review pack) are the two workflows the
Cowork plugin's skills teach. Each is written here as the script of tool calls the skill
describes, run once as the hosted orchestrator would call it (REST, an app-only token acting for
a person) and once as Cowork would (MCP, the person's own token). What is proved:

* a document built ONLY from tool output passes `verify_figures`, and the same document with one
  digit changed does not, for every figure in it;
* every change is two steps, lands once, is attributed to the person, and is audited with its
  confirmation linked;
* a person who may read everything but not write is refused every commit, and nothing is written.

The API behind the gateway is the production app (Entra on, SQLite stores, the synthetic book).
"""
from __future__ import annotations

import io
import re

import pytest
from openpyxl import load_workbook

from application import wiring
from application.capabilities import registry
from channel.render import VERBATIM, provenance_line
from test_simulate_unit import SITE, cascade, wired  # noqa: F401 - fixtures
from workflow_harness import (  # noqa: F401 - fixtures
    OTHER_OID, PAYROLL_CLIENT, USER_OID, entra, flow, gold, money_mutations, platform_text, service, surface, world,
)

ENGAGE = {"client_id": 2001, "program_code": "GA_JTC", "scope": "in_scope", "note": "signed"}
CONTACT_DATES = ("29 October", "27 October")


def resolve(surface, name: str) -> int:
    """`client_resolve` as the skills use it: one exact name resolves on the first call [CH-15e]."""
    first = surface.call("client_resolve", {"name_or_text": name})
    assert first.ok and first.facts["resolved"] is True and first.facts["clarify"] is False
    assert first.facts["client_name"] == name
    return first.facts["client_id"]


def shape(events):
    return [(e.tool_name, e.phase, e.outcome) for e in events]


# ================================================================ W1: the book review


def test_w1_the_ranking_is_the_pages_and_every_row_is_named(surface):
    book = surface.call("book_rank", {"limit": 8})
    assert book.ok and book.text.startswith(VERBATIM)
    assert book.facts == registry.call("book_rank", limit=8).to_dict()["facts"]
    rows = book.facts["clients"]
    assert [r["position"] for r in rows] == list(range(1, len(rows) + 1))
    assert rows[-1]["client_name"] == "Halloway Foods" and rows[-1]["reason"] == "Not assessed"
    assert {r["reason"] for r in rows[:-1]} == {"Identified"}


def test_w1_a_workbook_built_only_from_tool_output_verifies_and_one_wrong_digit_does_not(flow, surface):
    book = surface.call("book_rank", {"limit": 8})
    pages = [platform_text(book)]
    for row in book.facts["clients"]:
        client_id = resolve(surface, row["client_name"])
        situation = surface.call("client_situation", {"client_id": client_id})
        assert situation.ok
        trend = surface.call("client_trend", {"client_id": client_id})
        assert trend.ok
        pages += [platform_text(situation), platform_text(trend)]
    workbook = "\n".join([*pages, "Last contact: 29 October by mail; open thread since 27 October."])

    checked = surface.verify(workbook, *CONTACT_DATES)
    assert checked.ok and checked.facts["status"] == "pass", checked.facts["violations"]
    assert checked.facts["checked_numerals"] > 20

    without_context = surface.verify(workbook)
    assert without_context.facts["status"] == "rejected", "a date the author added is not the engine's, and says so"

    mutations = money_mutations(workbook)
    assert len(mutations) >= 8
    for wrong in mutations:
        assert surface.verify(wrong, *CONTACT_DATES).facts["status"] == "rejected"


def test_w1_an_unassessed_client_reads_as_unassessed_never_as_zero(surface):
    client_id = resolve(surface, "Halloway Foods")
    situation = surface.call("client_situation", {"client_id": client_id})
    assert situation.facts["assessed"] is False and "$0" not in situation.text


def test_w1_an_engagement_is_two_steps_lands_once_and_is_audited_for_the_acting_user(flow, surface):
    prepared, committed = surface.two_steps("engagement_set", ENGAGE)
    assert committed.ok and committed.facts["replayed"] is False
    assert [e.scope.value for e in flow.world.claims.engagements(2001)] == ["in_scope"]
    assert prepared.facts["preview"]["before"] is None or prepared.facts["preview"]["before"] != prepared.facts["preview"]["after"]

    events = flow.events()
    assert {e.channel for e in events} == {surface.channel} and {e.identity_assurance for e in events} == {surface.assurance}
    assert {e.user_oid for e in events} == {USER_OID}
    writes = [e for e in events if e.tool_name.startswith("engagement_set")]
    assert shape(writes) == [("engagement_set_prepare", "begin", "pending"), ("engagement_set_prepare", "end", "ok"),
                             ("engagement_set_commit", "begin", "pending"), ("engagement_set_commit", "end", "ok")]
    ends = {e.tool_name: e for e in writes if e.phase == "end"}
    assert ends["engagement_set_prepare"].confirmation_ref == prepared.confirmation_id
    assert ends["engagement_set_commit"].confirmation_ref == prepared.confirmation_id, "the commit points at the preview that was confirmed"
    assert {e.client_id for e in writes} == {2001}


def test_w1_the_whole_script_leaves_a_trail_of_reads_and_exactly_one_change(flow, surface):
    book = surface.call("book_rank")
    client_id = resolve(surface, book.facts["clients"][0]["client_name"])
    surface.call("client_trend", {"client_id": client_id})
    surface.verify(platform_text(book))
    surface.two_steps("engagement_set", ENGAGE)
    ends = [e for e in flow.events() if e.phase in ("end", "single")]
    assert {e.tool_name for e in ends} >= {"book_rank", "client_resolve", "client_trend", "verify_figures", "engagement_set_commit"}
    assert sum(1 for e in ends if e.tool_name == "engagement_set_commit" and e.outcome == "ok") == 1
    assert all(e.outcome == "ok" for e in ends)


# ================================================================ W2: the review pack


@pytest.fixture
def pack(flow, surface):
    """W2's reads for the payroll client, as the skill's steps 1-2 and 7 call them."""
    client_id = resolve(surface, "Saltmarsh Kitchens")
    assert client_id == PAYROLL_CLIENT
    reads = {
        "client_situation": surface.call("client_situation", {"client_id": client_id}),
        "client_eligibility": surface.call("client_eligibility", {"client_id": client_id, "tax_year": 2023, "state": "GA", "method": "pay_period"}),
        "client_trend": surface.call("client_trend", {"client_id": client_id}),
        "client_at_risk": surface.call("client_at_risk", {"client_id": client_id, "tax_year": 2023, "state": "GA"}),
        "client_discovery": surface.call("client_discovery", {"client_id": client_id, "state": "GA"}),
        "calc_walkthrough": surface.call("calc_walkthrough", {"client_id": client_id, "tax_year": 2023, "state": "GA"}),
    }
    assert all(r.ok for r in reads.values()), {k: r.body for k, r in reads.items() if not r.ok}
    return reads


def briefing_and_footer(reads) -> tuple[str, list[str]]:
    """The Word briefing's text and the four provenance values its footer carries, all from the envelopes."""
    sections = [platform_text(reads[name]) for name in ("client_situation", "client_eligibility", "client_trend", "client_at_risk", "client_discovery")]
    walkthrough = reads["calc_walkthrough"]
    footer = provenance_line(reads["client_eligibility"].body)
    values = [v for k, v in reads["client_eligibility"].body["provenance"].items() if k != "source" and v]
    return "\n\n".join([*sections, "Appendix A\n" + platform_text(walkthrough), footer, "Prepared 3 November. Page 1 of 4."]), values


def test_w2_the_briefing_verifies_with_its_provenance_footer_and_a_changed_hash_does_not(pack, surface):
    text, values = briefing_and_footer(pack)
    assert len(values) == 4 and "Provenance: run run-42" in text
    ok = surface.verify(text, "3 November", "Page 1 of 4", *values)
    assert ok.facts["status"] == "pass", ok.facts["violations"]
    assert surface.verify(text, "3 November", "Page 1 of 4").facts["status"] == "rejected", "identifiers are not facts unless the author names them"
    trail_hash = next(v for v in values if len(v) == 64)
    run = next(m for m in re.finditer(r"\d{4,}", trail_hash))
    changed = trail_hash[:run.end() - 1] + str((int(trail_hash[run.end() - 1]) + 1) % 10) + trail_hash[run.end():]
    altered = text.replace(trail_hash, changed)
    assert altered != text and surface.verify(altered, "3 November", "Page 1 of 4", *values).facts["status"] == "rejected", "one digit of the trail hash"
    for wrong in money_mutations(text)[:10]:
        assert surface.verify(wrong, "3 November", "Page 1 of 4", *values).facts["status"] == "rejected"


def test_w2_each_finding_is_decided_in_two_steps_and_attributed(flow, pack, surface):
    listed = surface.call("findings_list", {"client_id": PAYROLL_CLIENT, "tax_year": 2025, "state": "GA"})
    open_ids = [f["finding_id"] for f in listed.facts["findings"] if f["requires_decision"]]
    assert open_ids, "the synthetic payroll carries a finding to decide"
    for number, finding_id in enumerate(open_ids, start=1):
        args = {"client_id": PAYROLL_CLIENT, "tax_year": 2025, "finding_id": finding_id, "resolution": "accept", "note": "reviewed"}
        prepared, committed = surface.two_steps("finding_resolve", args, idem=f"finding-{number}")
        assert committed.ok, committed.body
        assert prepared.facts["preview"]["after"]["finding_id"] == finding_id
    live = {r.finding_id: r for r in flow.world.findings.live(PAYROLL_CLIENT, 2025)}
    assert set(live) == set(open_ids) and all(getattr(r.resolution, "value", r.resolution) == "accept" for r in live.values())
    assert all(r.decided_by in (USER_OID, "pat@example.com") for r in live.values()), "attributed to the person, not the bot"
    after = surface.call("findings_list", {"client_id": PAYROLL_CLIENT, "tax_year": 2025, "state": "GA"})
    assert after.facts["summary"]["requires_decision"] == 0


def test_w2_the_claim_moves_to_proposed_only_through_a_confirmed_commit(flow, pack, surface):
    args = {"client_id": PAYROLL_CLIENT, "program_code": "GA_JTC", "tax_year": 2024, "status": "proposed"}
    before = len(flow.history(PAYROLL_CLIENT, "GA_JTC", 2024))
    prepared = surface.call("claim_transition_prepare", args)
    assert prepared.ok and len(flow.history(PAYROLL_CLIENT, "GA_JTC", 2024)) == before, "a preview changes nothing"
    assert prepared.facts["preview"]["before"]["status"] == "assessed" and prepared.facts["preview"]["after"]["status"] == "proposed"
    committed = surface.commit("claim_transition", args, prepared.token, "move-1")
    assert committed.ok
    history = flow.history(PAYROLL_CLIENT, "GA_JTC", 2024)
    assert len(history) == before + 1 and history[-1].status.value == "proposed"
    assert history[-1].decided_by in (USER_OID, "pat@example.com"), "the person, by object id when only the channel vouches, by sign-in name when they signed in"


def test_w2_the_package_is_created_in_two_steps_linked_and_downloaded_once(flow, pack, surface):
    args = {"client_id": PAYROLL_CLIENT, "tax_year": 2024}
    assert surface.call("claim_package_link", args).error_code == "not_calculated", "no link before a package exists"
    _, built = surface.two_steps("claim_package_create", args, idem="package-1")
    assert built.ok, built.body
    link = surface.call("claim_package_link", args)
    assert link.ok
    path = link.facts["download_path"]
    assert path.startswith("/channel/v1/downloads/") and path in link.text
    assert not any(m in link.text.lower() for m in ("sig=", "blob.core", "sharedaccess"))
    first = flow.gw.client.get(path)
    assert first.status_code == 200 and first.headers["x-content-sha256"] == built.facts["result"]["sha256"]
    assert load_workbook(io.BytesIO(first.content)).sheetnames[0] == "Coverage"
    assert flow.gw.client.get(path).status_code == 410, "single use"
    downloads = [e for e in flow.events() if e.tool_name == "claim_package_download" and e.phase == "end"]
    assert [(e.outcome, e.user_oid) for e in downloads] == [("ok", USER_OID)]


def test_w2_a_whatif_the_user_names_is_the_engines_and_verifies(flow, surface, wired):  # noqa: F811
    """Step 3 of the skill: the worksite, action and size are the person's; every figure that comes back is the engine's."""
    args = {"client_id": 2001, "tax_year": 2025, "worksite_id": SITE, "action": "add_headcount", "magnitude": 2}
    result = surface.call("simulate", args)
    assert result.ok and result.facts == registry.call("simulate", **args).to_dict()["facts"]
    text = platform_text(result)
    assert surface.verify(text).facts["status"] == "pass"
    wrong = money_mutations(text)
    assert wrong and all(surface.verify(variant).facts["status"] == "rejected" for variant in wrong)

# ============================================================ a person who may only read


WRITES = (
    ("finding_resolve", {"client_id": PAYROLL_CLIENT, "tax_year": 2025, "finding_id": "policy:test_of_twos:GA:2025", "resolution": "accept"}),
    ("finding_reopen", {"client_id": PAYROLL_CLIENT, "finding_id": "policy:test_of_twos:GA:2025"}),
    ("claim_transition", {"client_id": PAYROLL_CLIENT, "program_code": "GA_JTC", "tax_year": 2024, "status": "proposed"}),
    ("claim_record", {"client_id": 2002, "program_code": "GA_JTC", "tax_year": 2022, "status": "assessed"}),
    ("engagement_set", ENGAGE),
    ("claim_package_create", {"client_id": PAYROLL_CLIENT, "tax_year": 2024}),
)


@pytest.fixture(params=["rest", "mcp"])
def reader(request, flow):
    """Somebody on neither writer list: they sign in and read, and that is all."""
    return flow.surface(request.param, OTHER_OID)


def test_a_reader_can_run_every_read_of_both_workflows(reader, pack):
    for tool, args in (("book_rank", {}), ("client_situation", {"client_id": 2001}), ("client_trend", {"client_id": 2001}),
                       ("client_eligibility", {"client_id": 2001, "tax_year": 2023}), ("client_at_risk", {"client_id": 2001, "tax_year": 2023}),
                       ("client_discovery", {"client_id": 2001}), ("calc_walkthrough", {"client_id": 2001, "tax_year": 2023}),
                       ("findings_list", {"client_id": PAYROLL_CLIENT, "tax_year": 2025, "state": "GA"})):
        assert reader.call(tool, args).ok, tool


@pytest.mark.parametrize(("tool", "args"), WRITES, ids=[w[0] for w in WRITES])
def test_a_reader_is_refused_every_commit_and_nothing_is_written(flow, reader, tool, args):
    writer = flow.surface("rest")
    prepared = writer.call(f"{tool}_prepare", args)
    assert prepared.ok, prepared.body
    refused_prepare = reader.call(f"{tool}_prepare", args)
    assert not refused_prepare.ok and refused_prepare.error_code == "not_authorized"

    snapshot = (len(flow.world.claims.history(2001, "GA_JTC", 2023)), len(flow.history(PAYROLL_CLIENT, "GA_JTC", 2024)),
                len(flow.history(2002, "GA_JTC", 2022)), flow.world.claims.engagements(2001), flow.world.findings.live(PAYROLL_CLIENT))
    refused = reader.commit(tool, args, prepared.token, "stolen-1")
    assert not refused.ok and refused.error_code == "not_authorized"
    assert snapshot == (len(flow.world.claims.history(2001, "GA_JTC", 2023)), len(flow.history(PAYROLL_CLIENT, "GA_JTC", 2024)),
                        len(flow.history(2002, "GA_JTC", 2022)), flow.world.claims.engagements(2001), flow.world.findings.live(PAYROLL_CLIENT))
    outcomes = [(e.tool_name, e.outcome) for e in flow.events(OTHER_OID) if e.phase in ("end", "single") and e.tool_name.startswith(tool)]
    assert (f"{tool}_commit", "refused") in outcomes
    assert not [e for e in flow.events(OTHER_OID) if e.outcome == "ok" and e.tool_name.endswith("_commit")]
    assert wiring.get_artifact_service() is not None


def test_a_refused_package_leaves_no_package_to_link(flow, reader):
    args = {"client_id": PAYROLL_CLIENT, "tax_year": 2024}
    prepared = flow.surface("rest").call("claim_package_create_prepare", args)
    assert not reader.commit("claim_package_create", args, prepared.token, "p").ok
    assert flow.surface("rest").call("claim_package_link", args).error_code == "not_calculated"




