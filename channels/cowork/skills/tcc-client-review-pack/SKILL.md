---
name: tcc-client-review-pack
description: |
  Builds a client credit review pack for a tax consultant: resolves the client, reads eligibility, trend, jobs at risk and other programmes, runs what-ifs the user names, walks through each open finding for a decision, records confirmed decisions and a claim move to proposed, then authors a Word briefing and a short PowerPoint from the engine's own figures and builds the claim package with a download link. Use when the user asks for a "client review pack", "credit review", "review pack for <client>", "client briefing", "walk me through <client>'s credit", "prepare the claim package", or "resolve the findings for <client>".
license: MIT
metadata:
  author: Tax Credit Copilot
  version: "1.0"
---

# Client credit review pack

For tax consultants. The platform calculates; you present, ask for decisions and author the
documents. Apply the rules in `tcc-figures-and-writes` throughout. In short: quote every
figure exactly as a tool returned it, never produce one yourself, verify every artifact with
`verify_figures`, and make every change in two confirmed steps.

## Non-negotiables

- Documents are built from tool output only. No figure of your own, no rounding, no summing.
- A decision about a finding or a claim is the person's, never yours. Ask; do not assume.
- Each change is one prepare, one preview shown exactly, one explicit confirmation, one commit.
- Do not copy an employee identifier into a document. Findings are about records, not people.
- Put the disclaimer from the tool results in every artifact.

## Procedure

1. **Resolve the client.** Call `client_resolve` with the name the user gave. It never guesses:
   with nothing selected it lists the candidates, even when only one fits. Show them and ask
   ("Do you mean <name>?"). Once the user confirms, call `client_resolve` again with
   `current_client_id` set to the confirmed candidate's `client_id`, and it resolves. Then ask for the **tax year** and
   **state** if the user did not say; offer the years and programmes that `client_situation`
   lists. The programme code you need later comes from there.
2. **Read the position.** Call `client_eligibility` (credit and headcount for the year),
   `client_trend` (movement across years and whether the client has been eligible since its
   base year), `client_at_risk` (counted jobs near a statutory floor) and `client_discovery`
   (other programmes the client may qualify for), plus `client_situation` for the programme and
   year cells. Pass the `client_id`, `tax_year` and `state`. If the answer is `not_calculated`
   or `year_not_authored`, report that in the tool's words and do not report zero. A year with
   no authored rule pack is declined by name, not estimated.
3. **What-ifs (only if the user names one).** Call `simulate` with the worksite, the action and
   the size the **user** gave. Take the worksite identifier exactly as an earlier result showed
   it, or ask. Never choose a number of hires, hours or a wage rate yourself. Present the result
   as returned, and say which year it describes.
4. **Findings.** Call `findings_list` for the client-year. Present each open finding with its
   evidence, as returned, and ask the user for a decision on each one:
   `accept`, `assign` (also ask which worksite keeps the record), `drop` or `flag`, with an
   optional note. Do not suggest a default.
5. **Record each decision, one at a time.** `finding_resolve_prepare` with the user's decision;
   show the preview exactly; ask for confirmation of that change; on clear approval call
   `finding_resolve_commit` with the token, a fresh `idempotency_key` and identical
   `arguments`. Then the next finding. To withdraw a decision, use `finding_reopen_prepare` and
   `finding_reopen_commit` the same way.
6. **Move the claim to proposed (only when the user asks).** `claim_transition_prepare` with
   `status` `proposed` for the programme and year, preview, confirm, then
   `claim_transition_commit`. If the lifecycle refuses the move, quote the reason; do not work
   around it.
7. **Show the working.** Call `calc_walkthrough` for the client-year and keep the trail for the
   appendix: step, inputs, formula, output, citation and the evidence hash, as returned.
8. **Author the briefing and the deck.** A Word briefing and a PowerPoint of at most six slides,
   from tool output only (`references/word-briefing-outline.md`, `references/slide-outline.md`).
   Every figure is copied. Include the disclaimer and a provenance footer: copy the
   `Provenance:` line the tools returned (run, rule pack, assumptions, trail hash). If a value is
   not shown, write "not shown"; never write one from memory.
9. **Build the claim package.** When the user wants it: `claim_package_create_prepare`, preview,
   confirm, `claim_package_create_commit`, then `claim_package_link` with the same `client_id`
   and `tax_year`. Include the link exactly as returned, and say it works once, for the person
   who asked.
10. **Verify every artifact.** Call `verify_figures` on the full text of the briefing, of the
    deck (all slides and notes) and of any message you will send. Pass in `allowed_context`
    the numbers you or the user introduced (dates, slide numbers, the user's what-if sizes) and
    the four provenance values from the footer. Fix each reported figure by quoting the tool's
    wording and verify again. Do not hand over text that has not passed.
11. **Offer a follow-up hold.** Using your own built-in calendar ability, offer to put a
    follow-up on the calendar. The invite body contains **no figures**: a title, the client's
    name and the purpose.

## Output checklist

- [ ] The client was resolved by name with no guessing, and the year and state were the user's.
- [ ] Every figure in the briefing and the deck is copied from a tool result.
- [ ] Each open finding was shown with its evidence and the user decided each one.
- [ ] Each change had its own preview and its own confirmation.
- [ ] The appendix holds the walkthrough exactly as returned.
- [ ] The footer carries the run, rule pack, assumptions and trail hash, or says "not shown".
- [ ] `verify_figures` passed on every artifact. The disclaimer is in each.
- [ ] The package link was given as returned. The calendar invite has no figures.

## If something fails

- `ambiguous` or `client_not_found`: ask for the name again; do not pick a client.
- `not_calculated`: the platform has not looked at that client-year. Say so; stop that part.
- `year_not_authored`: repeat the platform's message; offer the years it covers.
- A commit refused as `not_authorized`: the user can read but not change records here. Finish the
  read-only parts (briefing, deck) and say which changes were not made.
- `confirmation_expired` or `confirmation_replayed`: prepare again, or read the record back
  first (`findings_list`, `claim_cell_history`) before assuming anything.
- A commit that times out: read the record back before trying again; it may have gone through.
- `verify_figures` keeps failing: remove the figure, say so, and tell the user.

Full error wording: `skills/tcc-figures-and-writes` > `references/error-messages.md`.

## Additional resources

- `references/word-briefing-outline.md`: headings and what goes under each.
- `references/slide-outline.md`: the six slides.
- `references/decision-prompts.md`: how to ask for each decision.
