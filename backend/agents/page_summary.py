"""PageSummaryAgent — the headlines of one page, in the page's own figures.

29 Sep: the page-opening banners were replaced by a collapsed "Copilot summary"
that a reader opens when they want the story rather than the grid. This agent
writes it. The brief is built by `tools/page_brief.py` from the payload the page
itself was served, so the summary cannot describe a different answer from the
one on screen; it can only choose what to lead with and say it plainly.
"""
from __future__ import annotations

from .factory import AgentRecord, register_agent

NAME = "PageSummaryAgent"
INSTRUCTIONS = """\
You are the page summary writer for the Tax Credit Copilot.

The host application hands you a JSON brief for ONE page the reader is looking
at: `subject`, a list of `facts` (each already computed and formatted),
`caveats` that must not be contradicted, and supporting `data`.

Write 2-4 markdown bullets. Each bullet is a headline an advisor could repeat:
what needs attention, what is going well, what would change the answer.

1. Lead with what needs attention: a location below its minimum or behind
   pace, a client on the line, an employee just short of a floor.
2. Quote every figure EXACTLY as it is written in `facts` or `data`. Do not
   round, add, subtract, average or convert. If a figure is not in the brief,
   do not state one.
3. Keep each bullet to one sentence of at most 30 words. Never name the
   page's `subject` — the reader is already on its page. Bold the name of each
   location, client or employee a bullet is about, and nothing else: never a
   figure, a label or a phrase. No labels before the sentence.
4. Say where things STAND. Never state an outcome that has not happened —
   not "missed", "lost", "will fail" or "will qualify" — and never describe a
   figure as more or less than the facts say it is.
5. If a caveat applies to what you say, say it in the same bullet, briefly:
   an open year's "on track" is a forecast, not a qualification; a placeholder
   wage floor is not the published figure; "not assessed" is not a zero.

Hard rules:
- Never invent a number, a name, a deadline, a statute or a citation.
- Never recommend an action the facts do not support.
- No preamble, no heading, no closing line. Bullets only.

Tone: plain, specific, no jargon, no emojis.
"""

AGENT_PROFILE = {
    "tab_label": "Page Summary",
    "summary": "Writes the collapsed Copilot summary at the top of each page, from that page's own figures.",
    "responsibility": (
        "Read the JSON brief built by tools/page_brief.py for the page on screen and pick "
        "the two to four headlines that matter, quoting its figures exactly."
    ),
    "inputs": [
        "JSON brief: page, subject, facts[], caveats[], data",
    ],
    "outputs": [
        "Streamed 2-4 markdown bullets in the page's Copilot summary panel",
    ],
    "tools": [
        "tools/page_brief.py · portfolio_brief / client_brief / unit_brief / employee_brief — "
        "pure shaping of the payload the page was served",
        "tools/page_brief.py · unsupported_figures — every number in the summary is checked "
        "against the brief and flagged on screen if it is not there",
    ],
    "determinism": (
        "The brief is deterministic: it is the page's own payload, reformatted. Wording "
        "varies; figures are pinned by the brief and checked after the summary is written."
    ),
}


def build(*, project_client, project_endpoint, credential, model) -> AgentRecord:
    return register_agent(
        project_client=project_client,
        project_endpoint=project_endpoint,
        credential=credential,
        model=model,
        name=NAME,
        instructions=INSTRUCTIONS,
        temperature=0.2,
        profile=AGENT_PROFILE,
    )
