"""A rule-based guard against text that tries to instruct the model. [AI-07]

Prompt injection is a person (or a document a person controls) writing into a
field the model will read, in a voice meant to be obeyed: "ignore your
instructions", "you are now…", a forged `system:` turn. The defence in depth is:

1. untrusted text is FENCED and labelled as data (`untrusted.py`);
2. this guard refuses to SEND a prompt that carries such an attempt;
3. whatever the model says passes the output policy and, on the channel, the
   numeric guard — and no model produces a figure at all [ADR-004].

When this guard fires the model is not called. The reader still gets the engine's
figures (the same degraded answer as an outage) and the router falls back to
keyword routing, which cannot be talked into anything. A false positive therefore
costs some prose, never an answer — which is why the rules can be strict.

Rules are explicit phrases over normalised text (NFKC, case-folded, invisible
characters removed, whitespace collapsed), plus a letters-only pass for the few
high-confidence phrases so spacing tricks ("i g n o r e") do not hide them. The
verdict names RULES, never the matched text.

Limits, stated: this is pattern matching. A new phrasing will get past it, and a
model can be steered by text that contains no command at all. That is why it is one
layer of three, and why the corpus in `tests/ai_evals/datasets/injection.jsonl` is
the thing to extend when a new attempt is seen.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from application.ai.safety.untrusted import unwrap


def _clean(text: str) -> str:
    """NFKC, no invisible/format characters, case-folded. Line breaks kept."""
    text = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf").casefold()


def normalise(text: str) -> str:
    """`_clean` with whitespace collapsed, for phrase matching."""
    return re.sub(r"\s+", " ", _clean(text)).strip()


def letters_only(text: str) -> str:
    """The text reduced to a-z, so spacing, punctuation and digits cannot hide a phrase from the scan."""
    return re.sub(r"[^a-z]", "", _clean(text))


_OBJ = r"(?:instructions?|rules?|prompts?|directions?|guidelines?|constraints?|restrictions?|programming)"
_WORDS: dict[str, "re.Pattern[str]"] = {
    "override_instructions": re.compile(
        rf"\b(?:ignore|disregard|forget|override|bypass|discard|drop|skip)\b(?: \w+){{0,3}} {_OBJ}\b"),
    "override_facts": re.compile(
        r"\b(?:ignore|disregard|override|replace|contradict)\b(?: \w+){0,3} (?:json|facts?|figures?|numbers?|data|brief|engine)\b"),
    "persona_switch": re.compile(
        r"\b(?:you are now|from now on,? you|you will now act|pretend (?:to be|you are|that you)|roleplay as|simulate being)"
        r"|(?:^|[.!?:] |\bplease |\byou (?:must|should|will|can|could) |\bnow |\bjust )act as (?:if|though|an?|the|my)\b"),
    "reveal_prompt": re.compile(
        rf"\b(?:reveal|print|show|repeat|output|display|leak|tell me|what (?:is|are|was|were))\b(?: \w+){{0,4}} (?:system|hidden|initial|original|your|the above|above) (?:prompt|message|{_OBJ})\b"),
    "forged_role": re.compile(
        r"(?:<\|(?:im_start|im_end|system|assistant|user|endoftext)\|>|\[/?inst\]|<</?sys>>|</?s>)\s*(?:###\s*)?(?:system|assistant|developer)\s*(?:prompt|message)?\s*:"),
    "role_markers": re.compile(r"<\|[a-z_]+\|>|\[/?inst\]|<</?sys>>"),
    "fence_spoof": re.compile(r"<<<\s*untrusted|end untrusted\s*>>>"),
    "jailbreak": re.compile(r"\b(?:jailbreak|developer mode|dan mode|do anything now|no restrictions|without (?:any )?(?:restrictions|limits|filters))\b"),
    "new_instructions": re.compile(rf"\b(?:new|updated|real|actual|additional) {_OBJ}\b ?[:\-]"),
    "exfiltrate": re.compile(
        r"\b(?:send|post|upload|forward|email|exfiltrate|transmit)\b(?: \w+){0,6} (?:to|at) (?:https?://|www\.|[\w.-]+@)"),
    "encoding_evasion": re.compile(r"\b(?:base64|rot13|hex)\b(?: \w+){0,4} (?:encode|decode|encoded|decoded)|\b(?:encode|decode)\b(?: \w+){0,4} (?:in|as|into|using) (?:base64|rot13|hex)\b"),
}
_COMPACT = {
    "override_instructions": ("ignorepreviousinstructions", "ignoreallinstructions", "disregardpreviousinstructions",
                              "ignoreyourinstructions", "ignoretheabove", "forgetyourinstructions"),
    "persona_switch": ("youarenow", "pretendtobe"),
    "reveal_prompt": ("revealyoursystemprompt", "printyoursystemprompt", "showyoursystemprompt", "repeatyoursystemprompt"),
}


#: A forged conversation turn: a line that starts as a system/assistant message would.
_LINE_TURN = re.compile(r"(?m)^[ \t>*#-]*(?:system|assistant|developer)(?: (?:prompt|message))?[ \t]*:")


@dataclass(frozen=True)
class InjectionVerdict:
    """Which injection rules fired. Names only, never the matched text."""

    rules: tuple[str, ...] = ()

    @property
    def flagged(self) -> bool:
        return bool(self.rules)


class PromptInjectionGuard:
    """Scan a prompt. Stateless; safe to share."""

    def scan(self, text: str) -> InjectionVerdict:
        text = unwrap(text)
        spaced, compact = normalise(text), letters_only(text)
        hit = {name for name, rule in _WORDS.items() if rule.search(spaced)}
        hit |= {name for name, phrases in _COMPACT.items() if any(p in compact for p in phrases)}
        if _LINE_TURN.search(_clean(text)):
            hit.add("forged_role")
        return InjectionVerdict(tuple(sorted(hit)))
