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
accepts the event) and `frontend/src/components/ask/` (which draws it). The
backend half is `backend/api/chat/evidence.py` (shapes a capability's `ToolResult`
into an item) and `evidence_tap.py` (emits it); see "What the portal chat emits".

## Status

| Part | State |
| --- | --- |
| `evidence` item, kind `evidence` | **Emitted** by `POST /api/chat` (CH-15d), one item per capability that ran. |
| `confirmation` item | **Inert, by design.** The portal chat has no write flow: nothing in `/api/chat` can record a decision, so there is nothing to preview or confirm. The frontend still validates and draws the kind (`ConfirmCard`) so the channel's write flow can reuse it; the portal backend never sends one. Writes in the portal go through the page's own forms and the mediator, not through chat. |
| `kpis` block | Defined and drawn, **not emitted**: no capability renders tiles today. |

## What the portal chat emits

One `evidence` event per capability that ran, built from that capability's
`ToolResult` envelope (`tool`, `facts`, `blocks`, `provenance`, `disclaimer`,
`warnings`). It is sent **ahead of the next frame the pipeline yields**, so the
evidence for a capability arrives before the narration of it and always before
`done`. Every other event, and every field of them, is unchanged. Mapping:

| Envelope | Evidence item |
| --- | --- |
| (the chat intent that ran) | `tool` and `id` (`ev-<intent>-<n>`) and a fixed tab `title` (`Who to call`, `Situation`, `Eligibility`, `At risk`, `Trend`, `All programmes`, `Other programmes`, `What-if`, `Calculation`). `tool` is the **intent** named in the `plan` event, not the envelope's own tool name (two intents share `client_discovery`). A re-sent id replaces the earlier tab, so the latest answer for a capability wins. |
| `paragraph` / `callout` | `text` / `callout` block, text verbatim. |
| `heading` | The `title` of the block that follows it (a heading with nothing after it is a `text` block). |
| `bullets` | `list` block. |
| `table` (header row first) | `table` block: `columns` = the header, `rows` = the rest. No `align`: the platform does not guess. |
| `facts` | Top-level scalar facts as strings; nested values are left out. |
| `provenance` | `run_id`, `rule_pack` (= `rule_pack_version`), `trail_hash` (= `trail_sha256`); a field the envelope does not hold is absent. `assumption_set_id` and `source` have no slot in the contract and are not sent. |
| `warnings` | One `callout` (`tone: partial`, title `Note`) each. These are caveats such as "the claimed side is an unverified assertion", and must not be lost. |
| `disclaimer` | `disclaimer`. |

Text and rows pass through **character for character**: no model text, no
reformatting, every figure the string the platform wrote. A result with no
blocks emits no event. The golden file `frontend/src/lib/askBackendShape.json`
holds two real items; `backend/tests/test_chat_evidence.py` compares the backend's
output to it and `components/ask/AskWorkspace.backend.test.jsx` reads the same
file through the real stream reader, so the two halves cannot drift apart.

### Who sees employee rows

A capability the catalog marks `sensitive` (`client_at_risk`, `employee_drill`,
`findings_list`), or one the catalog does not know, has its table **withheld**
unless the caller is a signed-in principal (`principal.authenticated`, so never
under `AUTH_MODE=none`). The table is replaced by a text block that keeps the
count ("12 rows withheld. Employee-level rows are shown to a signed-in user
only.") and the item's `facts` are emptied, because an empty table would read as
"nobody". Today none of these capabilities renders a row that names an employee
(D-08), so this rule is a guard on the next one that does. Employee rows were
never sent to the model, and are not now: the narrator is handed `facts`, never
`blocks`.

## The event

`POST /api/chat` already streams Server-Sent Events: `status`, `plan`,
`agent_start`, `token`, `agent_end`, `calculation_trail`, `clarify`, `done`. This
adds one event (emitted since CH-15d; a client may still see none, for example
from the scripted stub stream):

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
