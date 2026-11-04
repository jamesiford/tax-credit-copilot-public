"""The questions the parity test asks, and what each door is expected to say about them. [RM-13]

One `Case` is one question asked the same way through every door: the catalog arguments the REST, gateway,
MCP and MAF-tool doors are handed, what a reader says to Teams (so the real orchestrator settles the same
arguments from the reader's own words), and, where the portal chat can answer it, the intent, the page scope
and the sentence it is asked with. A door that cannot answer a case says WHY, in `portal_na`, instead of
being left out: the matrix of cases and doors is the evidence, and a hole in it is a finding.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tests.data_engine_fixture import CLIENT, YEAR

NAME = "Synthetic Client One"
PAGE = {"client_id": CLIENT, "tax_year": YEAR, "state": "GA"}


@dataclass(frozen=True)
class Portal:
    """How the portal chat is asked the same question: the intent it runs, the page scope and the sentence."""

    intent: str
    message: str
    scope: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Case:
    """One question through every door.

    `proposed` is what a scripted model passes when it names the tool; the orchestrator's rules then write the
    client, year and method over it from `question`, and `args` is what must come out (and what the other doors
    are handed). `lane` is `aggregate`, `employee` (a person-level result: the person's lane) or `write` (a preview).
    """

    id: str
    tool: str
    args: dict[str, Any]
    question: str
    proposed: dict[str, Any] = field(default_factory=dict)
    lane: str = "aggregate"
    portal: Portal | None = None
    portal_na: str = ""


_PORTAL_NA_NO_INTENT = "the portal chat has no intent that runs this tool (the page reads it over REST)"
_PORTAL_NA_METHOD = "the portal's eligibility brief reads Pay Period only, by decision D-05; the REST/MCP/MAF doors take the method"
_PORTAL_NA_PROTOTYPE = "the portal's what-if is the straight-line prototype (`simulate_headcount`), a different question from the catalog's `simulate`"
_AGG = {"dataset": "unit_year_master", "client_id": CLIENT, "select": ["worksite_id"], "measures": [{"column": "*", "agg": "count", "as": "n"}]}

CASES: tuple[Case, ...] = (
    Case("eligibility-min-max", "client_eligibility", {"client_id": CLIENT, "tax_year": YEAR, "method": "min_max"},
         f"What is the credit for {NAME} in {YEAR} using the Min-Max method?", portal_na=_PORTAL_NA_METHOD),
    Case("eligibility-pay-period", "client_eligibility", {"client_id": CLIENT, "tax_year": YEAR, "method": "pay_period"},
         f"What is the credit for {NAME} in {YEAR} using the Pay Period method?",
         portal=Portal("eligibility", f"What is the credit in {YEAR}?", {**PAGE, "method": "pay_period"})),
    Case("trend", "client_trend", {"client_id": CLIENT}, f"How has {NAME} trended?",
         portal=Portal("trend", "How has it trended?", {**PAGE, "method": "pay_period"})),
    Case("at-risk", "client_at_risk", {"client_id": CLIENT, "tax_year": YEAR, "state": "GA", "method": "min_max"},
         f"Which counted jobs at {NAME} could fall out of the credit in {YEAR} using Min-Max?", {"state": "GA", "method": "min_max"},
         portal=Portal("at_risk", "Which jobs could fall out?", {**PAGE, "method": "min_max"})),
    Case("situation", "client_situation", {"client_id": CLIENT, "year": YEAR}, f"Brief me on {NAME} for {YEAR}",
         portal=Portal("situation", "Brief me on them", {**PAGE, "method": "min_max"})),
    Case("book", "book_rank", {}, "Who should we call first across the whole book?",
         portal=Portal("book", "Who should we call first?", {})),
    Case("discovery-all", "client_discovery", {"client_id": CLIENT}, f"Which programmes could {NAME} qualify for across every state?",
         portal=Portal("multi_state", "full portfolio", {**PAGE, "method": "min_max"})),
    Case("discovery-other", "client_discovery", {"client_id": CLIENT, "state": "GA"},
         f"What other programmes could {NAME} qualify for besides the Georgia one?", {"state": "GA"},
         portal=Portal("discovery", "what else", {**PAGE, "method": "min_max"})),
    Case("what-if", "simulate", {"client_id": CLIENT, "tax_year": YEAR, "worksite_id": "GA_ATL_HQ", "action": "add_headcount",
                                  "magnitude": 2, "method": "pay_period"},
         f"What if {NAME} added 2 people at GA_ATL_HQ in {YEAR} using the Pay Period method?",
         {"worksite_id": "GA_ATL_HQ", "action": "add_headcount", "magnitude": 2, "method": "pay_period"}, portal_na=_PORTAL_NA_PROTOTYPE),
    Case("walkthrough", "calc_walkthrough", {"client_id": CLIENT, "tax_year": YEAR, "state": "GA", "method": "min_max"},
         f"Walk me through the calculation for {NAME} for {YEAR} using Min-Max", {"state": "GA", "method": "min_max"},
         portal_na="the portal's explain re-narrates the trail cached by an earlier answer; it runs no client-year read"),
    Case("findings", "findings_list", {"client_id": CLIENT, "tax_year": YEAR, "state": "GA"},
         f"Show the findings for {NAME} for {YEAR}", {"state": "GA"}, portal_na=_PORTAL_NA_NO_INTENT),
    Case("claim-history", "claim_cell_history", {"client_id": CLIENT, "program_code": "GA_JTC", "tax_year": YEAR},
         f"Show the history of the Georgia claim for {NAME} in {YEAR}", {"program_code": "GA_JTC"}, portal_na=_PORTAL_NA_NO_INTENT),
    Case("data-catalog", "data_catalog", {}, "What data can I query?", portal_na=_PORTAL_NA_NO_INTENT),
    Case("data-distinct", "data_distinct_values", {"client_id": CLIENT, "dataset": "unit_year_master", "column": "worksite_id"},
         f"Which worksites does {NAME} have?", {"dataset": "unit_year_master", "column": "worksite_id"}, portal_na=_PORTAL_NA_NO_INTENT),
    Case("data-aggregate", "data_query", dict(_AGG), f"How many method rows does each worksite of {NAME} have?",
         {k: v for k, v in _AGG.items() if k != "client_id"}, portal_na=_PORTAL_NA_NO_INTENT),
    Case("data-capped", "data_query", {"dataset": "unit_month_summary", "client_id": CLIENT, "select": ["worksite_id", "tax_year"], "limit": 2},
         f"List the worksites and years of {NAME}", {"dataset": "unit_month_summary", "select": ["worksite_id", "tax_year"], "limit": 2},
         portal_na=_PORTAL_NA_NO_INTENT),
    Case("data-employee", "data_query", {"dataset": "employee_eligibility", "client_id": CLIENT, "select": ["record_token", "tax_year"], "limit": 3},
         f"Show three employee eligibility rows for {NAME}", {"dataset": "employee_eligibility", "select": ["record_token", "tax_year"], "limit": 3},
         lane="employee", portal_na=_PORTAL_NA_NO_INTENT),
    Case("prepare-engagement", "engagement_set_prepare", {"client_id": CLIENT, "program_code": "GA_JTC", "scope": "in_scope", "note": "x"},
         f"Mark the GA_JTC engagement of {NAME} as in scope", {"program_code": "GA_JTC", "scope": "in_scope", "note": "x"},
         lane="write", portal_na="a change is previewed and confirmed in the portal's own forms, never from the chat"),
    Case("prepare-claim", "claim_transition_prepare", {"client_id": CLIENT, "program_code": "GA_JTC", "tax_year": YEAR, "status": "assessed"},
         f"Move the {YEAR} GA_JTC claim of {NAME} to assessed", {"program_code": "GA_JTC", "status": "assessed"},
         lane="write", portal_na="a change is previewed and confirmed in the portal's own forms, never from the chat"),
)
