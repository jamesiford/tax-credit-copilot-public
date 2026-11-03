# Word briefing outline

Title: `<Client> — credit review, <programme>, tax year <year>` (the year is the user's; the
others come from the tool results). Every figure below is copied from the named tool's result.
Where a table was returned, reproduce it row for row.

| Section | Source | Content |
| --- | --- | --- |
| 1. Summary | `client_situation`, `client_eligibility` | Three to five sentences in your words, then the key lines copied exactly: the client's position and the credit figure and headcount. No figure appears in your own sentences without being a copied line. |
| 2. Eligibility for the year | `client_eligibility` | The returned heading, paragraph and table, as written. State the method the tool states. |
| 3. Movement across years | `client_trend` | The returned table, and the sentence on whether the client has been eligible since its base year, as written. If the tool says nothing is held after the base year, say that; it is not a "no". |
| 4. Jobs at risk | `client_at_risk` | The returned statement and table. It describes a completed year: what would have to change for counted jobs to fall out. It does not predict that they will. Keep that framing. |
| 5. Other programmes | `client_discovery` | The returned list, as written. These are possibilities from the rule-pack library, not findings. |
| 6. What-ifs | `simulate` | One short subsection per what-if the user asked for: the question in the user's words, then the result as returned. Mark any open-year figure as a run-rate estimate, as the tool does. |
| 7. Findings and decisions | `findings_list`, the writes | Each finding as returned with the decision the user made and the confirmation that the change was recorded. Findings you did not decide are listed as open. |
| 8. Claim status | `claim_cell_history` or the commit result | The programme-year's status as returned, and whether it was moved to proposed. |
| 9. Package | `claim_package_link` | The download link, as returned, and that it works once. |
| Appendix A. Calculation | `calc_walkthrough` | The full trail: step, inputs, formula, output, citation, and the evidence hash. |
| Footer (every page) | Tool results | `Provenance:` line as returned; the disclaimer as returned; "Prepared by Copilot Cowork from Tax Credit Copilot results. Not tax advice." |

## Rules

- No sentence of yours contains a figure.
- Keep the user's decisions in their words; do not rephrase a decision into a recommendation.
- No employee identifiers, names or record tokens.
- Page numbers and the date are yours. Pass them in `allowed_context` when you verify.
