# Questions worth asking of the data

Only for the optional "go deeper" step. Read `data_catalog` first and use its names exactly: the
columns below are the ones it lists today, and the catalog is the authority if it changes. The
fixed tools answer the credit, eligibility and trend; the data tools show what sits underneath
and never restate those figures.

| The user asks | Tools, in order | What the data adds | Authority for the headline figure |
| --- | --- | --- | --- |
| Which locations carried the headcount? | `data_catalog` (`unit_month_summary`), `data_query` | Average headcount by worksite for the year and method | `client_eligibility` |
| Which months drove the average? | `data_query` on `unit_month_summary` | The twelve monthly headcounts, summed across locations or by worksite | `client_eligibility` |
| How many employees did each method find eligible, by year? | `client_trend`, then `data_query` on `run_method_summary` or `employee_eligibility` | Both methods side by side, labelled; never merged | `client_trend` and `client_eligibility` |
| How many were counted under Min-Max but not Pay Period? | `data_query` on `employee_eligibility` (counts only) | A count, never a list of people | `client_eligibility` |
| Where did the credit come from, by location? | `client_eligibility`, then `data_query` on `unit_year_master` | Annual credit and eligible jobs per worksite and year | `client_eligibility` |
| How does a designation or tier affect the threshold? | `data_distinct_values` for `designation`, then `data_query` on `unit_year_master` | The threshold and its source per worksite | `client_eligibility` |
| Which pay codes does the payroll use, and how often? | `data_distinct_values` for `pay_code`, then `data_query` | Counts of pay periods by code | none: descriptive only |
| What is the spread of weekly hours for the people near the floor? | `client_at_risk`, then `data_query` on `employee_eligibility` (aggregates) | A count or average by band; never named rows | `client_at_risk` |
| Why did the year's headcount fall at the end? | `client_trend`, then `data_query` on `unit_month_summary` | When it moved, by month and location; not why | `client_trend` |
| Which runs exist and under which rules? | `data_query` on `run_manifest` | The run, rule pack and assumption sets behind a figure | `calc_walkthrough` |

## How to word the answer

- Copy the returned table and its `Source:` line. Call it data, not a finding.
- If the result says it was capped, say so and offer a narrower question.
- If the catalog has no column for the question, say the data has nothing for it.
- A question about another client, or about several, is not answered here: the data tools take
  the one client in the review.
- Individual employees are refused in Copilot Cowork unless the user is a writer. Offer a count
  or an average by location, month or year.
