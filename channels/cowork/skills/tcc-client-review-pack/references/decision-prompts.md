# Asking for decisions

The person decides. Offer the options the tool allows and nothing else, with no default and no
nudge. Show the evidence first, exactly as `findings_list` returned it.

## A finding

> **<Finding title>** (open). <Evidence as returned.>
> What would you like to do? **accept** it as it stands, **assign** it to a worksite (tell me which
> worksite keeps it), **drop** it, or **flag** it for someone else. You can add a note.

After the answer, call `finding_resolve_prepare` and show the preview exactly. Then:

> That would record: **<what the preview says>**. Shall I record it? (yes / no / change it)

Only an explicit yes commits. "Looks fine", "ok go on to the next one" and silence do not. If in
doubt, ask once more.

## Several findings

Take them one at a time, in the order returned. Do not offer "accept all". One confirmation covers
one change.

## Moving the claim to proposed

> The claim for **<programme>, <year>** is currently **<status as returned>**. Do you want me to move
> it to **proposed**? I will show you exactly what changes before I do it.

Then `claim_transition_prepare`, the preview exactly, an explicit yes, `claim_transition_commit`.

## A change of mind

If the user wants to undo a recorded decision, use `finding_reopen_prepare` and
`finding_reopen_commit` the same way. A decision is appended to the record, never erased, so say
that the earlier decision stays in the history.
