"""Output policy: rules for the words a model may say. [AI-07]

Dataset: `tests/ai_evals/datasets/output_policy.jsonl`. The rules are patterns, so the
tests are examples — and the ones that matter as much are the benign sentences that
must NOT be caught, because a policy that withholds ordinary prose gets switched off.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import api.chat as chat
from application import composer, output_policy
from application.ai.safety.policy import RuleOutputPolicy
from application.ai.safety.stream_gate import OutputGate
from application.ai.safety.settings import SafetySettings, load_safety_settings
from application.ai.settings import AiConfigurationError
from application.capabilities.envelope import Block
from tests.ai_fakes import FlakyRuntime, install_providers

CORPUS = [json.loads(line) for line in
          (Path(__file__).parent / "ai_evals" / "datasets" / "output_policy.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.mark.parametrize("row", CORPUS, ids=lambda r: r["id"])
def test_each_example_gets_exactly_the_expected_codes(row):
    result = output_policy.review(row["text"], allowed_hosts=row.get("hosts", ()))
    assert sorted(result.violations) == sorted(row["expect"]), row["text"]


def test_the_corpus_covers_every_rule_and_has_benign_rows():
    codes = {c for r in CORPUS for c in r["expect"]}
    assert codes == {"url", "email", "phone", "ssn_shape", "ein_shape", "code_fence", "legal_advice"}
    assert sum(not r["expect"] for r in CORPUS) >= 6


def test_a_violation_is_a_code_never_the_text():
    verdict = RuleOutputPolicy().review("mail secret.person@example.com now")
    assert not verdict.ok and verdict.violations == ("email",) and "secret" not in repr(verdict)


def test_the_policy_module_is_standard_library_only_so_it_can_be_vendored():
    import ast

    stdlib = set(__import__("sys").stdlib_module_names) | {"__future__"}
    tree = ast.parse(Path(output_policy.__file__).read_text(encoding="utf-8"))
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert imported <= stdlib, imported - stdlib


# --- the streaming gate --------------------------------------------------------------

def feed_all(chunks, policy=None):
    gate, shown = OutputGate(policy or RuleOutputPolicy()), []
    for chunk in chunks:
        shown.append(gate.feed(chunk))
    shown.append(gate.finish())
    return "".join(shown), gate


def test_clean_text_passes_through_whole():
    shown, gate = feed_all(["Cascade has ", "twelve net ", "new jobs."])
    assert shown == "Cascade has twelve net new jobs." and not gate.blocked


def test_a_link_split_across_chunks_is_held_whole_and_never_shown():
    shown, gate = feed_all(["See ", "https://ev", "il.example/", "x now"])
    assert shown == "See " and gate.blocked == ("url",), "the link is not released, in whole or in part"


def test_text_held_at_the_end_is_released_by_finish_when_clean():
    gate = OutputGate(RuleOutputPolicy())
    assert gate.feed("no trailing space") == "no trailing " and gate.finish() == "space"


def test_nothing_is_released_after_a_block():
    gate = OutputGate(RuleOutputPolicy())
    gate.feed("mail a@b.com now ")
    assert gate.blocked == ("email",) and gate.feed("more text ") == "" and gate.finish() == ""


def test_a_phone_number_is_stopped_before_its_last_digits_are_shown():
    shown, gate = feed_all(["Call ", "404 ", "555 ", "0182 ", "today"])
    assert gate.blocked == ("phone",) and "0182" not in shown


# --- the portal chat path -----------------------------------------------------------

def tokens(frames):
    return "".join(json.loads(p.split("data: ", 1)[1])["content"] for p in "".join(frames).split("\n\n") if p.startswith("event: token"))


def drive(runtime, prompt="Brief.\n\nJSON:\n" + json.dumps({"identified_usd": "31000.00"}), **settings):
    install_providers(runtime, **settings)

    async def go():
        return [f async for f in chat._stream_agent("ReportingAgent", prompt)]

    return tokens(asyncio.run(go()))


def test_clean_prose_streams_unchanged():
    assert drive(FlakyRuntime("p", ["The credit is on the page."])) == "The credit is on the page."


def test_prose_with_a_link_is_withheld_and_the_figures_follow():
    shown = drive(FlakyRuntime("p", ["Details at https://evil.example/offer please."]))
    assert "evil.example" not in shown and "withheld by the output policy" in shown
    assert "- identified_usd: 31000.00" in shown


def test_what_was_clean_before_the_violation_stays_and_the_rest_is_withheld():
    from tests.ai_fakes import ScriptedRuntime

    shown = drive(ScriptedRuntime("p", ["The credit is real. ", "Email ", "partner@example.com ", "for it."]))
    assert shown.startswith("The credit is real. Email ") and "partner@" not in shown and "withheld" in shown


def test_the_policy_can_be_switched_off():
    shown = drive(FlakyRuntime("p", ["Details at https://evil.example/offer please."]),
                  safety=SafetySettings(output_policy=False))
    assert "evil.example" in shown


def test_an_allow_listed_host_may_be_linked():
    shown = drive(FlakyRuntime("p", ["See https://learn.microsoft.com/x for more."]),
                  safety=SafetySettings(output_allowed_hosts=("microsoft.com",)))
    assert "learn.microsoft.com" in shown


# --- the channel path ---------------------------------------------------------------

BLOCKS = [Block("paragraph", text="Annual credit: $3,500")]
FACTS = {"credit": {"annual_credit_usd": "3500.00"}}


def test_the_composer_drops_a_narration_that_breaks_the_policy_like_a_bad_figure():
    composed = composer.compose(BLOCKS, "Read more at https://evil.example/x for details.", FACTS)
    assert composed.narration_used is False and "evil.example" not in composed.text
    assert any(v.stage == "output_policy" for v in composed.guard.violations)
    assert "Annual credit: $3,500" in composed.text


def test_the_composer_keeps_a_clean_narration():
    composed = composer.compose(BLOCKS, "Here is the position for this client.", FACTS)
    assert composed.narration_used is True and composed.text.startswith("Here is the position")


def test_the_composer_honours_an_allow_list():
    composed = composer.compose(BLOCKS, "See https://learn.microsoft.com/x.", FACTS, allowed_hosts=("microsoft.com",))
    assert composed.narration_used is True


# --- settings -----------------------------------------------------------------------

def test_safety_defaults_are_on_and_overrides_parse():
    assert load_safety_settings({}) == SafetySettings(True, True, ())
    off = load_safety_settings({"AI_INJECTION_GUARD": "off", "AI_OUTPUT_ALLOWED_HOSTS": " Learn.Microsoft.com ,example.org"})
    assert off.injection_guard is False and off.output_allowed_hosts == ("learn.microsoft.com", "example.org")
    assert off.disabled_controls == ("injection_guard",)


def test_a_switch_that_is_not_on_or_off_is_a_startup_error():
    with pytest.raises(AiConfigurationError, match="AI_OUTPUT_POLICY"):
        load_safety_settings({"AI_OUTPUT_POLICY": "maybe"})
