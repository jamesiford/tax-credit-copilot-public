# Ask evidence contract

The Ask workspace has two panes. The left is the conversation, which the model
narrates. The right is **evidence**, which the platform renders. This document
is what the backend stream needs to emit for the right pane to fill. Until it
does, the pane shows a "Show on page" link for each capability the plan named,
and nothing breaks.

> The model narrates; the numbers come from the engine. No figure in the evidence
> pane is model prose, and the browser never computes, rounds, re-formats or
> re-orders one. It draws the strings it is given.

The frontend half is `frontend/src/lib/evidence.js` (framework-free: it defines
and validates the contract), `frontend/src/api.js` (`chatEventRouter`, which
accepts the event) and `frontend/src/components/ask/` (which draws it). Nothing
in `backend/` was changed to produce this document.

## The event

`POST /api/chat` already streams Server-Sent Events: `status`, `plan`,
`agent_start`, `token`, `agent_end`, `calculation_trail`, `clarify`, `done`. This
adds one **optional** event:

```
event: evidence
data: { ...an evidence item... }
```

- It may be sent zero, one or many times in a turn, anywhere before `done`.
- A client that has never heard of it ignores it, and **this client ignores any
  event name it does not know**, so the stream can grow without a coordinated
  release.
- An item that breaks the contract is **dropped, never repaired**: a repaired
  figure is a figure nobody produced. The pane says how many blocks it dropped.

## The item

It is shaped like the platform's tool-result envelope.

```jsonc
{
  "id": "ev-eligibility-1",          // optional. A re-sent id REPLACES the earlier item.
  "tool": "eligibility",             // required. A capability from the `plan` event.
  "kind": "evidence",                // optional: "evidence" (default) | "confirmation"
  "title": "Eligibility",            // optional. The tab label; defaults to `tool`.
  "facts": { "client": "…" },        // optional. Scalar facts the platform stands behind.
  "blocks": [ /* see below */ ],     // required (non-empty) for kind "evidence"
  "provenance": {                    // optional. Every key optional, unknown keys dropped.
    "run_id": "run-0123456789ab",
    "rule_pack": "ga_jtc/2023",
    "trail_hash": "b1946ac9…",       // SHA-256 over the calculation trail, shown in full
    "produced_at": "2026-08-26T12:00:00Z"
  },
  "disclaimer": "Computed by the calculation engine from payroll. Not tax advice."
}
```

### Every figure is a string

`"539"`, `"410.13"`, `"-4.0"`, `"$31,185"`. Write the exact text a reader should
see; the UI prints it as it arrived. A JSON number is accepted and printed as its
own digits, but `410.10` as a number is `410.1`, so **send strings**.

### Blocks

| `kind` | Fields | Drawn as |
| --- | --- | --- |
| `kpis` | `title?`, `rows: [{ label, value, sub?, tone? }]` | A row of tinted tiles (`KpiTile`). |
| `table` | `title?`, `columns: [string]`, `rows: [[string]]`, `align?: ["left"\|"right"]` | A dense table (12 px, 28 px rows). A row whose width differs from `columns` is dropped, not padded. |
| `callout` | `title?`, `text`, `tone?` | An inset assessment (`Callout`): the derivation sentence. |
| `text` | `title?`, `text` | A paragraph. |
| `list` | `title?`, `rows: [string]` | A bulleted list. |

`tone` is one of the `--state-*` families: `neutral`, `above-min`, `below-min`,
`partial`, `base-year`. Anything else is read as `neutral`. A tone is a
**reading** (a verdict or a status), never a brand colour, so the platform cannot
paint a block in the selection blue.

An unknown block `kind`, a block with no usable content, or a malformed row is
dropped. An item with no renderable block is dropped entirely.

### Tabs and counts

One tab per item, in the order sent, labelled `title` (else `tool`). The count
chip is the row count of the item's **first table**, and is absent when the item
has none: "Locations (3)", like "Who to call (4)", says whether it is worth a
click.

## Confirmation items (write flow, inert today)

Every write lands on a number on a filed return, so a write is two steps: the
platform previews it, a person confirms. An item with `kind: "confirmation"`
carries what *would* be recorded:

```jsonc
{
  "id": "ev-confirm-1",
  "tool": "record_decision",
  "kind": "confirmation",
  "title": "Confirm a decision",
  "confirmation": {
    "token": "confirm-token-1",          // opaque; echoed back by the callback
    "summary": "Count E00200 at GA_MAC_OPS for 2025-02.",
    "blocks": [ /* the preview, same block kinds as above */ ],
    "expires_at": "2099-01-01T00:00:00Z", // ISO 8601; shown verbatim
    "confirm_label": "Confirm",           // optional
    "cancel_label": "Cancel"              // optional
  }
}
```

`ConfirmCard` draws the preview, the expiry, and two buttons. It **does nothing
by itself**: Confirm and Cancel call `onConfirm(item)` / `onCancel(item)` on
`AskWorkspace`, and with no `onConfirm` the Confirm button is disabled and says
confirming is not connected. An expired confirmation cannot be confirmed. It
never confirms on a timer or without a click. The write itself (the endpoint
that takes `confirmation.token`) is the backend's, and is not defined here.

## Development without a backend

In a **development build only**, `?askFixture=1` replays the fixtures in
`frontend/src/lib/askFixtures.js` through the same router the real stream uses:
a plan, the agents' tokens, two evidence items (and a confirmation if the
question mentions "confirm" or "decision"), and a clarification if it says
"their". The fixtures are invented and customer-neutral. A production build
contains neither the branch nor the fixtures.

`frontend/src/lib/evidence.test.js` and `components/ask/AskWorkspace.ui.test.jsx`
pin the contract, including the numbers-verbatim test: every figure the pane
shows is a string the fixture sent.

## When there is no evidence

The pane shows a "Show on page" chip for each distinct capability in the `plan`
event, linking to the existing view that holds the same answer for the current
client, year and method (`frontend/src/lib/evidenceRoutes.js`). A capability that
needs a client, with none selected, is shown **disabled with its reason**, not
hidden. A capability the table does not know is shown by name and offered no
link, never guessed at. Keep the table in step with `CAPABILITIES` in
`backend/api/chat.py`.
