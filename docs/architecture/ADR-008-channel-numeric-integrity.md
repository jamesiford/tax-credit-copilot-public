# ADR-008 — Numeric integrity for the Microsoft 365 channel

**Date** 2026-11-02 · **Status** Accepted, **as built** (finalised in CH-12, 3 Nov 2026) ·
**Partially implements** [ADR-004](ADR-004-agentic-workflows.md) §3 · Context for the whole channel: [ADR-009](ADR-009-m365-channel.md)

## Context

[ADR-004](ADR-004-agentic-workflows.md) §3 specified a `NumericIntegrityMiddleware`
and `{{placeholder}}` substitution so that "the numeric guarantee becomes a
mechanism rather than an argument". None of it was built. What exists is the
weaker guarantee that `.github/copilot-instructions.md` states as its honest
limit: agents hold no tools, so they cannot *compute* a number — but a model that
is handed a figure can still *misstate* it, and the portal chat streams that
prose to the screen unchecked.

The Microsoft 365 channel (Teams, Copilot Chat, Cowork) changes what that costs.
Its promise is that **every figure shown is exactly the engine's figure**, to
people who will read it to a client and may put it in a memo. "Exactly" cannot be
an instruction to a model. It has to be a check that fails closed.

A second constraint shapes the design. The orchestrator that will run the channel
is a hosted agent in a container with no copy of this repository, so whatever
enforces the guarantee must be small enough to vendor and free of the application's
dependencies.

## Decision

### 1. A capability returns facts, and the platform renders them

Every channel tool is a capability (`application/capabilities/`) returning a
`ToolResult`: `facts` (the engine's numbers, untouched), `blocks` (text and table
rows the platform rendered from those facts through one formatter, `format.py`),
`provenance` and the standing disclaimer. A reply is assembled from `blocks`.
No model is involved in producing a figure *or* in rendering one.

### 2. A narrator may add prose, but never a figure

`ChannelNarratorAgent` writes one to four connective sentences around the blocks.
It is handed the **names** of the facts that exist, never their values
(`composer.narrator_brief`), and refers to a figure only by placeholder:
`{{facts.credit.annual_credit_usd}}`, optionally `{{facts.x|money}}`. A model that
has not seen a number cannot copy it as a digit; the guarantee does not rest on the
model obeying an instruction.

### 3. The guard runs twice, with zero tolerance

`application/numeric/guard.py` extracts every numeral from a piece of text —
plain, grouped, decimal, negative (`-3`, `(3)`), money, percentage, abbreviation
(`$3.5K`, `1.2 million`), the two ends of a range, a number beside a unit, an ISO
date, a `TY2023` token — and accepts it only if it is one of:

- **a fact.** Exact `Decimal` equality: no rounding allowance, no "close enough".
  An abbreviation is accepted only if the formatter would have printed exactly
  that spelling, so `about $3.5K` for 3,540 is rejected while `$3.54K` is not.
  A percentage is accepted only for a fact a placeholder has said is a ratio or a
  percentage, because 0.125 headcount is not 12.5%.
- **the reader's own numeral**, passed explicitly by the caller as `AllowedContext`:
  a number in their question ("5 hires"), a tax year or client id in scope. It is
  never inferred from the narration.
- **structural**, from a deliberately narrow list: a list marker at the start of a
  line, a step number, an ordinal up to the tenth.

Characters that look like digits but are not ASCII digits (full-width, Arabic-Indic,
vulgar fractions) are **rejected, not normalised**, as is a figure split by a thin or
no-break space (`3 500`): no formatter emits them, so their only use is evasion.

`application/composer/assemble.py` applies the guard at two points:

1. **Before substitution**, to the narrator's raw words (`check_raw`). Any digit
   outside a placeholder that the reader did not supply rejects the narration —
   even one that happens to equal a fact. The model typed a number.
2. **After substitution**, to the whole reply against the fact index. This is
   defence in depth against a formatter bug; the first gate trusts the formatter,
   the second does not.

If either fails the reply is the platform's blocks and the disclaimer, nothing
else. The composer never softens, rounds or patches a sentence, and it returns the
violations (with the nearest fact, so a changed digit is obvious) for the audit
row. If the blocks themselves fail — a formatter is wrong — no figure is shown at
all, with a notice. The disclaimer is appended to every reply.

### 4. The guard has to be shown to bite

A test that passes with and without the guard proves nothing, so the suite holds
a mutation test: for every numeral in a valid reply it flips one digit and requires
the guard to refuse the result, and a meta-test replaces the guard with one that
approves everything and requires that same loop to fail. The same loop is run over
the blocks of every capability, so CH-01's rendering is held to CH-02's guard.

### What is built, and what is still only specified

| Built here | Still specified in ADR-004 |
| --- | --- |
| Placeholder substitution through one formatter | MAF `WorkflowBuilder` workflows |
| The numeric guard and the composer | Checkpointing and human-gated resume |
| A narrator that is never shown a value | `TenantScopeMiddleware`, `CostGuardMiddleware` (the budget is built as a decorator: AI-04) |
| Fallback to platform blocks on any rejection | Structured-output field-by-field comparison for authored artifacts |
| A prompt-injection screen and an output policy (AI-07, below) | `PromptInjectionMiddleware` as MAF middleware — the same check runs today as a service-level screen |
| `verify_figures` over the gateway's conversation ledger, and the provenance line in the MCP text (below) | A shared, durable ledger; binding each numeral to the fact it cites |

The guard and composer are plain functions rather than `ChatMiddleware`. The
hosted orchestrator (a later work package) calls them in code; wrapping them as
middleware when MAF workflows land changes the call site, not the check.

## Safety of the words, not only the figures (AI-07)

The numeric guard decides whether a figure is the engine's. It does not decide
whether the words around it are ones the product will say. Two further controls,
both rule-based and both explainable in a sentence:

- **Untrusted text is fenced and screened going IN.** Anything a reader typed
  reaches a model only through `UntrustedText`: between markers, with a reminder
  that it is data, with forged markers defanged. `PromptInjectionGuard` — in
  `NarrationService`, the one place every model call passes — refuses to send a
  prompt carrying an instruction-override attempt ("ignore your instructions",
  "you are now…", a forged `system:` turn, a spoofed fence). The model is not called;
  the reader is told so and still gets the engine's figures, and the router falls
  back to keyword routing, which cannot be talked into anything. A false positive
  therefore costs prose, never an answer.
- **Prose is reviewed going OUT.** `application/output_policy.py` (standard
  library only, vendored beside the numeric guard) flags links to hosts not on an
  allow-list, email addresses, phone numbers, SSN/EIN shapes, code blocks, and the
  narrator presenting itself as counsel or guaranteeing an outcome (audit safety,
  entitlement). On the channel, `compose` drops a narration that breaks it exactly
  as it drops one with a bad figure. On the portal, `OutputGate` reviews the reply as
  it streams: text is held to the last word boundary and everything that would be
  released is reviewed whole first, so a link or address is never shown, in whole or
  in part; what a reader has already seen has always passed.

**Hedging a figure (CH-15c).** The numeric guard proves a numeral is the engine's, not that a sentence leaves it alone: a narrator once called an exact credit "rounded". `application/composer/hedging.py` rejects, structurally, any narration with an approximation qualifier (about, roughly, approximately, around, nearly, almost, rounded, up to, close to, or so, more or less) within three tokens of a figure, where a placeholder counts as a figure. It rejects rather than reads, so "not rounded" is rejected too, and a rejection degrades like every other: the engine's own answer without the commentary. It does not catch rank prose ("position 1" is a substituted value the guard accepts); the narrator prompt forbids it and `tests/ai_evals` flags it.

Violations are recorded as rule codes. The offending text is never repeated into a
log, a span or an error, because it is exactly what must not be repeated.

**Stated limits.** These are patterns. A new phrasing will get past them, and text
containing no command at all can still steer a model; that is why they are two layers
beside a third (no model produces a figure), and why
`tests/ai_evals/datasets/injection.jsonl` is the thing to extend when an attempt is
seen. A phone number can have its first digits shown before the last are stopped.
Both controls default on; setting either `off` is logged at startup.

## Writes (CH-05)

The same rule governs a write: the preview a person agrees to must be the row
that lands. A channel write is a `_prepare` and a `_commit`. Prepare builds the
real mediator command (so a request the command would refuse never gets a token),
derives the proposed state from that command's own pure functions, writes nothing,
and mints a single-use token bound to the person, the tool and the exact arguments.
Commit presents the token, the same arguments and an idempotency key, and sends
the command through the mediator, where the writer policy decides again. A retry
with the same key replays the first outcome. The preview blocks are rendered from
facts like every other capability and pass the same guard. The full flow is in
`application/confirmations.py` and `application/capabilities/writes.py`.

## Documents authored elsewhere: `verify_figures` (CH-06, CH-10, CH-11)

The composer protects a reply the platform assembles. Cowork assembles its own, and a Word briefing cannot be
built in code, so a second control exists for text the platform did not compose: **`verify_figures`**, a tool that
runs the same numeric guard, at zero tolerance, over a draft.

- **Against what.** Not facts the caller supplies (a caller choosing its own facts would be marking its own
  homework) but the gateway's **conversation ledger**: every `facts` block it returned in this conversation, kept in
  memory, bounded and expiring. What the caller *may* supply is `allowed_context`: the numerals the author or the
  reader introduced (a date, a count of emails found, a slide number) and, for a footer, the identifiers it quotes.
- **What it returns.** `pass` or `rejected`, with each offending token, its position and why, and the count checked.
  A figure that cannot be traced is reported, never waved through: after a restart the ledger is empty and every
  figure fails, which is the strict direction.
- **What the model is handed.** The MCP text for a result is rendered by the platform from the envelope's blocks,
  starts with `VERBATIM — quote figures exactly as written.`, carries a **provenance line** (run, rule pack,
  assumption set, trail hash; the label says "trail hash", not "sha256", because the guard reads the digits of a
  digest as numerals) and ends with the disclaimer. A footer is therefore copied, not composed, and an altered
  digit in it fails the check once the four values are passed as `allowed_context`.
- **Where it is proved.** `tests/channel/test_workflows*.py` drive whole workflows over REST and MCP: a document
  built only from returned blocks passes, and every one-figure mutation of it is rejected; a capability whose words
  disagree with its facts is caught by the envelope scan and by `verify_figures`; a forgotten ledger says no.

**Two limits found while proving it, stated rather than fixed.** The guard matches **values**. A wrong figure that
equals another real figure in the same conversation (`$1` beside a real count of 1) is not seen; the tests pin
this and the mutation helper leaves such collisions out. And `client_resolve` asked even for one exact name when no
client was selected, so a skill had to confirm and call it again with `current_client_id`; the guard is not involved,
but a workflow that guessed would have named the wrong client. *Update (CH-15e): the channel's `client_resolve` now
returns `resolved: true` for exactly one exact name or alias and still asks about a partial or ambiguous one.*

## Consequences

**Good.** On the channel path a wrong figure cannot reach a reader: it is either
the engine's rendering or the reply degrades to the engine's own blocks. The
guarantee is testable offline, and the same files run unchanged in the orchestrator
container (`application/capabilities/format.py`, `envelope.py`, `catalog.py`,
`application/numeric/guard.py`, `application/composer/assemble.py` import only the standard
library and each other).

**Costs.** Strictness has a price. A narrator that writes "the 11th hire", or any
digit it was not given, loses its sentence and the reader gets tables without prose.
That is the intended direction: a rejected sentence is an inconvenience, a wrong
figure on a tax return is not. Digits inside a *string* fact — a citation, a date —
are accepted anywhere in the final text (they are the engine's own words); the
strict gate on the model's raw output is what keeps a model from using that door.

**What this does not cover — said plainly.**

- **The portal chat's figures are still not number-checked.** The portal streams
  the narrator agents' prose to the browser. It takes its *briefs* from the same
  capabilities, so its figures are the engine's, but nothing checks what the model
  says about them. Since AI-07 that prose is at least screened and reviewed by the
  injection guard and output policy; the numeric guard still runs only on the
  channel path.
- **Number words are not numerals.** "twelve" is invisible to the guard. The
  narrator's prompt forbids them for figures; the guard does not, because a guard
  that guessed at English would be wrong in both directions.
- **Meaning is not checked.** A narration that places a correct figure in a false
  sentence ("your credit rose by {{facts.credit.annual_credit_usd}}") passes. The
  guard proves a figure is the engine's, not that the sentence is true. Narrator
  instructions and review, not this check, address that.
- **Cowork composes its own answers.** A skill can tell it to quote verbatim, and `verify_figures` (built; see
  above) lets it check a draft against the conversation's own results, but that is a weaker guarantee than the hosted
  orchestrator's: the check is a step the model is told to run, a ledger that is per process forgets on restart,
  and the guard compares values. The setup guide and the demo script say so in plain words.
