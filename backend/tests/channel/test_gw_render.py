"""The provenance line the MCP text carries. [CH-10]

A briefing footer has to be copied, not composed. The values arrive in the envelope's
`provenance`, but a client that shows the model only the text block would leave it
nothing to copy, and a model with nothing to copy writes something. So the text names the
run, rule pack, assumption set and trail hash, and says nothing when a result has none —
a claims-only read has no run, and inventing one is the one thing the field exists to prevent.
"""
from __future__ import annotations

from application.capabilities.envelope import DISCLAIMER
from channel.render import VERBATIM, provenance_line, render_tool_text
from gateway_harness import envelope


def test_the_line_names_every_value_the_result_has():
    body = envelope("client_trend")
    body["provenance"] = {"run_id": "run-1", "rule_pack_version": "rules/ga_jtc/2023.json", "assumption_set_id": "SET-A", "trail_sha256": "ab" * 32, "source": "x"}
    assert provenance_line(body) == f"Provenance: run run-1; rule pack rules/ga_jtc/2023.json; assumptions SET-A; trail hash {'ab' * 32}."


def test_a_result_with_no_provenance_says_nothing_rather_than_inventing_a_run():
    body = envelope("client_trend")
    body["provenance"] = {"run_id": None, "rule_pack_version": None, "assumption_set_id": None, "trail_sha256": None, "source": "recorded claims; no run"}
    assert provenance_line(body) == "" and "Provenance" not in render_tool_text(body)
    assert provenance_line({}) == ""


def test_the_line_sits_between_the_body_and_the_disclaimer_and_the_text_keeps_its_frame():
    body = envelope("client_trend", run_id="run-9")
    text = render_tool_text(body)
    assert text.startswith(VERBATIM) and text.endswith(DISCLAIMER)
    assert text.index("The credit is $31,500.00.") < text.index("Provenance: run run-9") < text.index(DISCLAIMER)


def test_the_wording_adds_no_digits_of_its_own():
    """The figure check reads digits as numerals, so a label like 'sha256' would add one to every footer."""
    body = envelope("client_trend")
    body["provenance"] = {"run_id": "abc", "rule_pack_version": "pack", "assumption_set_id": "set", "trail_sha256": "def", "source": None}
    assert not any(ch.isdigit() for ch in provenance_line(body))
