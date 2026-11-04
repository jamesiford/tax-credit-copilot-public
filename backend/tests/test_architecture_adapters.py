"""An adapter adds, rounds, ranks and reformats nothing: the rule of the run, as a test. [RM-13]

`test_architecture_patterns.py` holds the orchestrator's executors and tool bodies to this. The same rule binds the
other adapters over the capability catalog: the MCP facade and the gateway's routes, the API's capability route and
the portal chat's pipelines and evidence. The portal was the one that broke it: its portfolio and discovery
pipelines added up the hits' credits themselves, so the narrator was told totals no other door could produce (the
parity test found it; the sums moved into `discover_credits`, where every door reads them).

The detector is the one the orchestrator rule uses (`figure_computations`): it forbids the OPERATIONS (arithmetic,
`round`, `sum`, `min`, `max`, `format` and the rest), not a variable name, so it cannot be argued around. What an
adapter legitimately does with a number that is not a result (an index, a counter, a byte count, the reader's own
input) is listed below, by function and statement, each with its reason. A stale entry fails.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from test_architecture_patterns import figure_computations

BACKEND = Path(__file__).resolve().parents[1]
ADAPTERS = sorted(
    {*(f"api/chat/{p.name}" for p in (BACKEND / "api" / "chat").glob("pipelines_*.py")),
     *(f"api/chat/{p.name}" for p in (BACKEND / "api" / "chat").glob("evidence*.py")),
     "api/capabilities.py", "channel/mcp.py", "channel/routes.py", "channel/tools.py", "channel/render.py"},
)

#: (file, function, statement) -> why it is not a figure.
ALLOWED = {
    ("channel/mcp.py", "McpServer._session_owner", "time.monotonic() - held[1]"): "a session's age against its time to live",
    ("channel/routes.py", "_bounded_body", "data += chunk"): "bytes of the request body, counted against the size cap",
    ("api/chat/pipelines_whatif.py", "_extract_simulation", "-abs(n)"): "the sign of the headcount change the READER asked for, read from their words",
    ("api/chat/pipelines_whatif.py", "_extract_simulation", "abs(n)"): "the same input: the magnitude of what the reader typed",
    ("api/chat/pipelines_whatif.py", "_pipeline_simulate", "abs(new_hires)"): "the reader's own input restated in the narrator's instruction",
    ("api/chat/evidence.py", "<module>", "from decimal import Decimal"): "an isinstance test, so a Decimal is written exactly",
    ("api/chat/evidence.py", "_scalar_facts", "format(value, 'f')"): "a Decimal written out digit for digit, never rounded",
    ("api/chat/evidence.py", "evidence_item", "blocks += [{'kind': 'callout', 'title': 'Note', 'text': w, 'tone': 'partial'} for w in result.warnings]"): "list concatenation: each warning becomes a callout",
    ("api/chat/evidence_tap.py", "with_evidence", "sent + 1"): "the ordinal of an evidence item, a position and not a figure",
    ("api/chat/evidence_tap.py", "with_evidence", "sent += pending"): "the same ordinal counter",
}
SEEDED = '''
async def _pipeline_portfolio(result):
    total_lifetime = sum(h["lifetime_credit_usd"] for h in result["hits"])
    return {"portfolio_total_lifetime_usd": total_lifetime}
'''


def hits() -> set[tuple[str, str, str]]:
    return {(f, function, text) for f in ADAPTERS for function, _line, _kind, text in figure_computations((BACKEND / f).read_text(encoding="utf-8"))}


def test_the_adapters_are_found():
    assert {"api/capabilities.py", "channel/mcp.py", "channel/routes.py", "channel/tools.py", "channel/render.py"} <= set(ADAPTERS)
    assert {"api/chat/pipelines_core.py", "api/chat/pipelines_briefs.py", "api/chat/pipelines_whatif.py", "api/chat/evidence.py"} <= set(ADAPTERS)
    assert all((BACKEND / f).exists() for f in ADAPTERS)


def test_no_adapter_computes_or_formats_a_figure():
    found = hits()
    assert not found - set(ALLOWED), f"an adapter computes a figure; move it into a capability: {sorted(found - set(ALLOWED))}"


def test_every_allowed_statement_still_exists_and_says_why():
    assert not set(ALLOWED) - hits(), "an allowance no longer matches any code"
    assert all(len(reason) > 20 for reason in ALLOWED.values())


def test_the_detector_finds_the_portfolio_sum_the_portal_used_to_make():
    found = figure_computations(SEEDED)
    assert [(function, text) for function, _line, _kind, text in found if "sum" in text or "number call" in _kind]
    assert any(function == "_pipeline_portfolio" for function, *_ in found)


@pytest.mark.parametrize("name", ["pipelines_core.py", "pipelines_briefs.py"])
def test_the_pipelines_that_summed_hits_are_clean_now(name):
    assert not [h for h in hits() if h[0] == f"api/chat/{name}"]
