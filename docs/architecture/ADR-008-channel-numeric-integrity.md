# ADR-008 — Numeric integrity for the Microsoft 365 channel

**Date** 2026-11-02 · **Status** Accepted · **Partially implements** [ADR-004](ADR-004-agentic-workflows.md) §3

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

`application/numeric_guard.py` extracts every numeral from a piece of text —
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

`application/composer.py` applies the guard at two points:

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
| A narrator that is never shown a value | `TenantScopeMiddleware`, `PromptInjectionMiddleware`, `CostGuardMiddleware` |
| Fallback to platform blocks on any rejection | Structured-output field-by-field comparison for authored artifacts |

The guard and composer are plain functions rather than `ChatMiddleware`. The
hosted orchestrator (a later work package) calls them in code; wrapping them as
middleware when MAF workflows land changes the call site, not the check.

## Consequences

**Good.** On the channel path a wrong figure cannot reach a reader: it is either
the engine's rendering or the reply degrades to the engine's own blocks. The
guarantee is testable offline, and the same files run unchanged in the orchestrator
container (`application/capabilities/format.py`, `envelope.py`, `catalog.py`,
`application/numeric_guard.py`, `application/composer.py` import only the standard
library and each other).

**Costs.** Strictness has a price. A narrator that writes "the 11th hire", or any
digit it was not given, loses its sentence and the reader gets tables without prose.
That is the intended direction: a rejected sentence is an inconvenience, a wrong
figure on a tax return is not. Digits inside a *string* fact — a citation, a date —
are accepted anywhere in the final text (they are the engine's own words); the
strict gate on the model's raw output is what keeps a model from using that door.

**What this does not cover — said plainly.**

- **The portal chat is unchanged.** `api/chat.py` still streams the narrator agents'
  prose to the browser unvalidated. It takes its *briefs* from the same capabilities
  now, so its figures are the engine's, but nothing checks what the model says about
  them. The channel path validates narration; the portal path does not.
- **Number words are not numerals.** "twelve" is invisible to the guard. The
  narrator's prompt forbids them for figures; the guard does not, because a guard
  that guessed at English would be wrong in both directions.
- **Meaning is not checked.** A narration that places a correct figure in a false
  sentence ("your credit rose by {{facts.credit.annual_credit_usd}}") passes. The
  guard proves a figure is the engine's, not that the sentence is true. Narrator
  instructions and review, not this check, address that.
- **Cowork composes its own answers.** A skill can tell it to quote verbatim and
  `verify_figures` (declared, not yet built) lets it check a draft, but that is a
  weaker guarantee than the hosted orchestrator's.
