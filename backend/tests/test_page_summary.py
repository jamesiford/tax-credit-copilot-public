"""The Copilot summary: a brief built from the page's own payload, and a check
on every figure the narration states.

ADR-004 is the reason these exist. The model never computes a figure; it picks
headlines from `facts`. What it CAN do is misstate one — it said Cascade was
"1.73 jobs short… one more role would move them closer" on 29 Sep — so the
check is not optional decoration: it is the only thing between a misstated
number and a reader who takes it as computed.
"""
from __future__ import annotations

import json

import pytest

from tools import page_brief as pb


# ------------------------------------------------------------------ the check


def test_a_figure_from_the_brief_passes_including_rounding_a_reader_accepts():
    brief = {"facts": ["$548,730 claimable across TY2020–TY2025.", "GA_GA-013 at 4.71 over."]}
    assert pb.unsupported_figures("**Cascade** has $548,730 claimable since TY2020.", brief) == []
    assert pb.unsupported_figures("About $549k claimable; GA-013 is 4.7 jobs over.", brief) == []


def test_a_figure_the_brief_never_held_is_named():
    brief = {"facts": ["1.73 jobs short of the minimum."]}
    assert pb.unsupported_figures("They are 2.5 jobs short and worth $12,000.", brief) == ["2.5", "$12,000"]


def test_small_counts_are_not_flagged_every_time_a_list_is_numbered():
    assert pb.unsupported_figures("4 of 6 locations are on track.", {"facts": []}) == []


def test_a_wrong_year_is_a_wrong_figure():
    assert pb.unsupported_figures("Below the minimum since TY2019.", {"facts": ["TY2021"]}) == ["2019"]


# --------------------------------------------------------------- the builders


def test_portfolio_names_each_client_by_the_reason_the_page_ranks_them():
    brief = pb.portfolio_brief({
        "total_clients": 5, "assessed_clients": 4,
        "items": [
            {"client_name": "Ironbridge", "priority_band": "on_the_line", "jobs_margin": -0.83,
             "program_code": "GA_JTC", "tax_year": 2022},
            {"client_name": "Halloway", "priority_band": "declining",
             "trend": {"fallen_by": 47.7, "peak_tax_year": 2022, "below_base": True, "credit_earned_usd": "97000"}},
            {"client_name": "Cascade", "priority_band": "unclaimed_at_scale", "identified_usd": "73000"},
        ],
    })
    assert brief["facts"][0] == "5 clients in the book, 4 assessed."
    assert brief["facts"][1] == "1. Ironbridge: On the line (GA_JTC TY2022), 0.83 jobs short of the minimum"
    assert "down 47.7 jobs since TY2022, now below its base year, $97,000 already earned" in brief["facts"][2]
    assert brief["facts"][3] == "3. Cascade: Identified, $73,000 identified"
    assert any("not a zero" in c for c in brief["caveats"])


def _row(unit, year, status, qualified=False, net_new=0.0, **extra):
    return {"worksite_id": unit, "tax_year": year, "status": status, "qualified": qualified,
            "net_new_vs_base": net_new, "is_base_year": status == "base", **extra}


def test_client_says_qualify_about_the_finished_year_and_on_track_about_the_open_one():
    brief = pb.client_brief({
        "items": [
            _row("GA-016", 2020, "base"), _row("GA-016", 2025, "below_minimum", net_new=0.34),
            _row("GA-016", 2026, "in_progress", net_new=0.0, months_reachable=7),
            _row("GA-010", 2020, "base"), _row("GA-010", 2025, "above_minimum", True, 12.9),
            _row("GA-010", 2026, "in_progress", True, 9.6, months_reachable=7),
        ],
        "unit_totals": [{"total_annual_credit_usd": "548730", "total_tranche_lifetime_usd": "766290"}],
    }, client_name="Cascade", placeholder_years=[2026])
    facts = brief["facts"]
    assert facts[0] == "2 locations; in its latest finished year, 1 qualify and 1 are below the minimum."
    assert facts[1] == "$548,730 claimable across TY2020–TY2025; $766,290 if maintained."
    assert "GA-016 was below the minimum in TY2025 (0.3 net-new jobs against its TY2020 base)." in facts
    assert "TY2026 is still open: 1 of 2 locations on track so far." in facts
    assert "GA-016 is behind pace in TY2026 (0.0 net-new jobs so far)." in facts
    assert any("placeholder" in c for c in brief["caveats"])
    assert any("forecast, not a qualification" in c for c in brief["caveats"])


def test_an_uncalculated_client_is_not_a_zero():
    brief = pb.client_brief({"items": [], "message": None}, client_name="Northwind")
    assert "not a zero" in brief["headline"]
    assert brief["data"] == {"calculated": False}


def test_unit_counts_the_cohort_within_the_band_of_the_floor_the_payload_carries():
    brief = pb.unit_brief({
        "year": 2026,
        "unit": {"worksite_id": "GA_GA-016", "average_headcount": 3.0, "base_average_headcount": 7.33, "months_reachable": 7,
                 "status": "in_progress", "qualified": False, "net_new_vs_base": 0.0, "threshold": 2.0},
        "thresholds": {"min_weekly_hours": 35},
        "total_unfiltered": 5,
        "near_threshold": [
            {"employee_id": "E1", "avg_weekly_hours": 34.1, "additional_weekly_hours": 0.9},
            {"employee_id": "E2", "avg_weekly_hours": 20.0},
        ],
    }, client_name="Cascade", month=7, placeholder=True)
    assert brief["facts"][0] == "GA_GA-016: 5 employees counted in July TY2026."
    assert brief["facts"][1] == "Average headcount 3.0 against a base of 7.33; reading: behind pace over 7 closed months."
    assert "1 more employees are within 5 hrs/week of the 35-hour floor; 2 are ineligible in all." in brief["facts"]
    assert "Employee E1 averages 34.10 hrs/week and needs 0.90 more to qualify." in brief["facts"]
    assert len(brief["caveats"]) == 2


def test_employee_states_each_method_against_the_floor():
    brief = pb.employee_brief({
        "employee_id": "200100828", "tax_year": 2026,
        "thresholds": {"minimum_average_weekly_hours": 35, "minimum_average_weekly_wages_usd": 680},
        "raw_source_rows": [{"selection_decision": "included"}] * 12,
        "step1": {"min_max": {"eligible": True, "rounded_avg_weekly_hours": 42.7, "rounded_avg_weekly_wages": 1032.54}},
        "onezero": {"months": list(range(12)), "min_max": [{"unit_id": "GA_GA-016", "months": [0] * 7 + [1] * 5}]},
    })
    assert brief["facts"][0] == "Employee 200100828, TY2026: 12 pay periods on record, 12 included."
    assert brief["facts"][1] == "Min-Max: eligible — 42.70 hrs/week against 35, $1,033/week against $680."
    assert brief["facts"][2] == "Counted in 5 of 12 measuring months under Min-Max, at GA_GA-016."


# ----------------------------------------------------------------- the endpoint


def _events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            out.append((lines["event"], json.loads(lines.get("data", "{}"))))
    return out


BRIEF = {"page": "portfolio", "subject": "the book", "headline": "5 clients in the book, 5 assessed.",
         "facts": ["5 clients in the book, 5 assessed.", "1. Ironbridge: On the line, 0.83 jobs short"],
         "caveats": [], "data": {}}


def test_without_copilot_it_says_the_computed_facts(client, monkeypatch):
    import api.summary as summary

    monkeypatch.setattr(summary, "build_brief", lambda req: BRIEF)
    monkeypatch.setattr(client.app.state, "registry", None, raising=False)
    events = _events(client.post("/api/summary", json={"page": "portfolio"}).text)
    names = [e for e, _ in events]
    assert names == ["brief", "fallback", "done"]
    assert events[1][1]["facts"] == BRIEF["facts"]


def test_with_copilot_it_streams_and_then_checks_every_figure(client, monkeypatch):
    import api.summary as summary

    class _Update:
        def __init__(self, text):
            self.text = text

    class _Agent:
        async def run(self, prompt, stream=True):
            assert "0.83 jobs short" in prompt
            for piece in ("- **Ironbridge** is 0.83 jobs short", "; worth $40,000."):
                yield _Update(piece)

    class _Record:
        agent = _Agent()

    class _Registry:
        by_name = {"PageSummaryAgent": _Record()}

        def __getitem__(self, name):
            return self.by_name[name]

    monkeypatch.setattr(summary, "build_brief", lambda req: BRIEF)
    monkeypatch.setattr(client.app.state, "registry", _Registry(), raising=False)
    events = _events(client.post("/api/summary", json={"page": "portfolio"}).text)
    tokens = "".join(d.get("content", "") for e, d in events if e == "token")
    assert tokens == "- **Ironbridge** is 0.83 jobs short; worth $40,000."
    check = next(d for e, d in events if e == "check")
    assert check == {"unsupported": ["$40,000"]}
    assert events[-1][0] == "done"


@pytest.mark.parametrize("body", [
    {"page": "client"},
    {"page": "unit", "client_id": 2001},
    {"page": "employee", "client_id": 2001, "tax_year": 2026},
])
def test_a_page_without_its_scope_says_so_rather_than_guessing(client, body):
    events = _events(client.post("/api/summary", json=body).text)
    assert events[0][0] == "error"
    assert "needs" in events[0][1]["detail"]


def test_an_unknown_page_is_refused(client):
    assert client.post("/api/summary", json={"page": "settings"}).status_code == 422
