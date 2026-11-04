---
name: tcc-figures-and-writes
description: |
  Standing rules for everything that uses the Tax Credit Copilot connector (tcc-channel): quote every figure exactly as the tool returned it, check drafts with verify_figures before anything is shared, make every change in two confirmed steps, report errors plainly, and never give tax advice. Use whenever the user asks about a client's tax credit, eligibility, headcount, claim, finding, engagement or claim package, or asks to "record", "resolve", "set", "move" or "package" anything for a client. Load alongside tcc-book-review and tcc-client-review-pack.
license: MIT
metadata:
  author: Tax Credit Copilot
  version: "1.0"
---

# Tax Credit Copilot: figures and writes

A figure in this product ends up on a filed return, so it must be the engine's figure and
not a paraphrase of it. These rules hold for every task that uses the `tcc-channel`
connector, whatever the user asked for. The two workflow skills (`tcc-book-review`,
`tcc-client-review-pack`) repeat the short version and depend on this one for the detail.

## 1. Figures are quoted, never produced

- Quote every dollar amount, count, headcount and percentage **exactly as the tool returned
  it**. Never round, abbreviate, convert, re-derive, average, sum or estimate.
- If a figure you need was not returned, call a tool that returns it, or say you do not have it.
  Do not work it out.
- Tool results start with `VERBATIM — quote figures exactly as written.` and end with a
  disclaimer. Copy the disclaimer into every document, email or message you produce.
- Text you write yourself (an opener, a summary sentence) contains **no figure of your own**.
  Refer to a figure by quoting the line that holds it.

## 2. Check before sharing

Before you hand over, send or save any document, email or message that contains figures:

1. Call `verify_figures` with the full text as `draft_text`.
2. Pass in `allowed_context` every number **you or the user** introduced and no tool returned:
   a date, a count of emails you found, a time, a slide number, a quantity the user asked
   about. Do not pass a figure a tool returned; those are already known.
3. A pass reads "Every figure in the draft was found in this conversation's results". A
   failure reads "N of M figures in the draft are not in this conversation's results" and
   lists each figure, its position and why. Fix each by replacing it with the tool's own
   wording, then call `verify_figures` again.
4. Never ship text that has not passed. If it still fails after two corrections, tell the user
   which figures you could not verify and leave them out.

The check only knows this conversation's results. A figure you remember from an earlier
conversation fails it, correctly. Fetch it again.

## 3. Changes are two steps, one confirmation each

Every write is a pair: a `*_prepare` tool that changes nothing and returns a preview and a
confirmation token, then the matching `*_commit` tool that makes the change.

1. Call the `*_prepare` tool with the arguments the user gave you. Do not guess a missing
   argument; ask.
2. Show the user the preview **exactly as returned**, and say plainly what will change.
3. Ask for explicit confirmation of **that** change. One confirmation covers one change.
   Never batch several changes under one "yes".
4. Only after the user clearly approves, in this conversation, call the matching `*_commit`
   tool with `confirmation_token` (the token from the preview), a fresh `idempotency_key`
   (any unique string; reuse it only to retry the same commit after a timeout) and
   `arguments` identical to the prepare call's.
5. Report what the commit returned. If the user says anything other than clear approval, do
   not commit. If their answer changes the arguments, prepare again.

A confirmation token expires, works once, and belongs to the person who asked. If a commit is
refused as expired or already used, prepare again and ask again.

Pairs: `finding_resolve_prepare` / `finding_resolve_commit`, `finding_reopen_prepare` /
`finding_reopen_commit`, `claim_transition_prepare` / `claim_transition_commit`,
`claim_record_prepare` / `claim_record_commit`, `engagement_set_prepare` /
`engagement_set_commit`, `base_year_set_prepare` / `base_year_set_commit`,
`claim_package_create_prepare` / `claim_package_create_commit`.

Only people on the writer list may commit. Everyone can read. If a commit is refused as not
authorised, say so and stop; do not try another route.

## 4. Questions about the data (optional, deeper)

`data_catalog`, `data_distinct_values` and `data_query` answer descriptive and comparative questions
about one client's payroll and calculation data (a count, an average or a total by location, month,
year, designation or method). They are read-only and take a specification, never SQL.

- The fixed tools stay authoritative for the credit, eligibility, trend and at-risk jobs. Do not use
  `data_query` to restate or second-guess one of those figures; use it for what sits underneath.
- Read `data_catalog` first and use its names exactly. Never invent a column or dataset. If the
  catalog has none for the question, say the data has nothing for it.
- Everything in section 1 applies unchanged: quote each value exactly as the table returned it, copy
  the `Source:` line, and check any draft that uses it with `verify_figures`.
- Repeat a cap: if the result says it was cut, say so and offer a narrower question.
- A question that would list individual employees is refused in Copilot Cowork unless the user is on
  the writer list (`employee_level_not_available`). Offer a count or an average; do not look for
  another route.
- The data tools take the one client in the conversation. Another client, or several at once, is a
  separate question for each.

`tcc-client-review-pack` > `references/data-questions.md` lists questions worth asking.

## 5. When something fails

Report the failure plainly, in the tool's words, and do not fall back to estimating.
`references/error-messages.md` lists each code and what to tell the user.

## 6. Scope

This is not tax advice. Do not give legal, filing or planning advice beyond what a tool returned,
and do not state a tax rule the tools did not state. Where a result says a year has no authored
rule pack, repeat that: the platform declines by name rather than guess.

## Additional resources

- `references/error-messages.md`: every error code the connector returns and what to say.
- `references/write-tools.md`: each write pair, its arguments and what the preview shows.
