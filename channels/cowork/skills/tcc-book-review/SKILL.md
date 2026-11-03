---
name: tcc-book-review
description: |
  Runs the Monday book review and call plan for an account or sales team: ranks the whole client book by why each client is worth calling, pulls each client's situation and trend, finds the last contact and open threads in the user's mail, Teams and calendar, and produces an Excel call plan, Outlook drafts and a To Do list, with optional confirmed engagement-scope updates. Use when the user asks for a "book review", "Monday review", "call plan", "who should we call this week", "which clients should I call", "prepare my call list", or "review my book".
license: MIT
metadata:
  author: Tax Credit Copilot
  version: "1.0"
---

# Monday book review and call plan

For an account or sales team. The platform ranks; you gather context and write the plan. Apply
the rules in `tcc-figures-and-writes` throughout. In short: quote every figure exactly as a tool
returned it, never produce one yourself, check every document and draft with `verify_figures`
before it is shared, and make every change in two confirmed steps.

## Non-negotiables

- No figure you worked out. No rounding, summing, averaging or converting.
- Nothing is sent. Outlook items are drafts only.
- A change to a client's record is one prepare, one preview shown exactly, one explicit
  confirmation, one commit. Never batch.
- Put the disclaimer from the tool results into the workbook and into every draft.

## Procedure

1. **Rank the book.** Call `book_rank` with `limit` 8 (or the number the user asks for, up to
   25). No client needs to be named. Show the returned table as it came: rank, client, reason,
   programme, tax year, identified credit and jobs margin. If the result carries the warning
   that some rows rest on an unverified claimed figure, carry that sentence into the plan.
   If it says no client has been assessed, say so and stop: that is not "nobody to call".
2. **Read each client.** `book_rank` returns names, not ids. For each client, in rank order:
   call `client_resolve` with the name exactly as returned. A name taken from `book_rank` is
   exact, so it answers `resolved: true` with the `client_id`; use it without asking the user
   anything. Only if it answers `resolved: false` and lists several candidates, ask the user and
   never pick. Then call `client_situation` and `client_trend` with the `client_id`. If either answers `not_calculated`, mark that client "Not calculated" in the
   plan and leave its figures blank. Do not report zero.
3. **Find the last contact.** Using your own built-in Microsoft 365 abilities (mail, Teams
   chat and channel messages, calendar), look for the most recent contact with each client and
   any open thread, such as a question nobody has answered. Read only. Say for each client what
   you found and what you did not find ("no contact found in mail, Teams or calendar").
   Never infer a contact you did not see. Dates you report are yours, not the engine's.
4. **Write the call plan.** Create an Excel workbook, one row per client, following
   `references/call-plan-workbook.md`. Figures are copied from the tool results. The suggested
   opener is two sentences at most, written by you, and contains **no figure**. It may name the
   reason ("on the line", "identified credit") and what the contact history showed.
   Then offer, for the clients the user selects: an Outlook **draft** per client
   (`references/outlook-draft-and-todo.md`) and a To Do list. Never send. Do not create items
   for clients the user did not select.
5. **Offer engagement updates.** For each client the team accepts, offer to record whether the
   programme is the firm's mandate. Ask for the programme (from the table's Programme column),
   the scope (`in_scope`, `out_of_scope` or `prospective`) and an optional note. Then run the
   write one client at a time: `engagement_set_prepare`, show the preview exactly, ask for
   confirmation of that change, and only on clear approval `engagement_set_commit` with the
   token, a fresh `idempotency_key` and the same `arguments`.
6. **Verify.** Call `verify_figures` with the full workbook text (every cell, row by row) and
   again with each draft body. Pass in `allowed_context` the numbers you introduced: dates,
   counts of messages you found, row numbers you added. Fix every reported figure by quoting
   the tool's wording and verify again. Do not hand over text that has not passed.
7. **Summarise.** Tell the user, in separate lists: what was written (the workbook, and any
   engagement changes committed, each read back), what was only drafted (Outlook drafts, To Do
   items) and nothing else. Name anything you could not do and why.

## Output checklist

- [ ] The ranking table matches `book_rank` row for row, in the same order.
- [ ] Every figure in the workbook and drafts is copied from a tool result.
- [ ] The suggested openers contain no figure.
- [ ] Every client shows what contact was found, or that none was.
- [ ] `verify_figures` passed on the workbook text and on each draft.
- [ ] Each engagement change had its own preview and its own confirmation.
- [ ] Nothing was sent. The disclaimer is in the workbook and every draft.

## If something fails

- `not_calculated` for a client: mark the row "Not calculated" and carry on with the others.
- `ambiguous` from `client_resolve`: ask the user which client; do not guess.
- `rate_limited` or `timeout`: wait a minute, retry once, then report which clients are missing.
- A commit refused as `not_authorized`: say the user can read but not change records here, and
  stop the write flow. The plan and drafts are unaffected.
- `verify_figures` keeps failing: remove the figure, say you removed it, and tell the user.
- Your own search of mail, Teams or the calendar returns nothing or is unavailable: say so on the
  row. An empty search is a finding, not a gap to fill.

Full error wording: `skills/tcc-figures-and-writes` > `references/error-messages.md`.

## Additional resources

- `references/call-plan-workbook.md`: the workbook's sheets and columns.
- `references/outlook-draft-and-todo.md`: the draft template and the To Do format.
