# Call plan workbook

One workbook, two sheets. Every figure cell holds the text exactly as the tool returned it
(for example the Identified cell holds the string the `book_rank` table showed), stored as text so
a spreadsheet cannot reformat, round or recalculate it. Do not add a formula, a total, a
chart, a sum or a sort that changes the order. The order is the page's order.

## Sheet 1: Call plan (one row per client, in rank order)

| Column | Source | Rule |
| --- | --- | --- |
| Rank | `book_rank`, the `#` column | As returned. |
| Client | `book_rank`, the Client column | As returned. |
| Reason | `book_rank`, the Reason column | The words the page uses. Never replace with your own label or a score. |
| Programme | `book_rank` | As returned; blank if the tool returned none. |
| Tax year | `book_rank` | As returned. |
| Identified | `book_rank` (and `client_situation` for detail) | As returned, with its currency symbol and separators. Blank when the client is "Not calculated". |
| Jobs margin | `book_rank` | As returned. A negative margin is meaningful; do not flip or round it. |
| Trend | `client_trend` | The one-line statement the tool rendered (for example whether the client has been eligible since its base year). Copy the sentence; do not paraphrase it. |
| Last contact | Your Microsoft 365 search | A date and a channel (mail, Teams, meeting), or the words "None found". Read-only. |
| Open thread | Your Microsoft 365 search | A one-line description in your words, or "None found". No figures. |
| Suggested opener | You | Two sentences at most. No figures. Refer to the reason and the contact history. |
| Status | You | "Ready", "Not calculated" or "Needs a name check" (when `client_resolve` asked for help). |

## Sheet 2: Notes

| Row | Content |
| --- | --- |
| Source | "Ranked by `book_rank`; figures from `client_situation` and `client_trend`", plus the date you ran them. |
| Ranking note | The ranking note the tool returned, as written. |
| Unverified claims | The warning about unverified claimed figures, if the tool returned one. |
| Disclaimer | The disclaimer from the tool results, as written. |
| Not done | Anything you could not read, per client. |

## Text for verify_figures

Build the text you pass to `verify_figures` by reading every cell of both sheets, left to right,
top to bottom, one row per line. Include the header row. Dates and counts you added go in
`allowed_context`, not in the guard's facts.
