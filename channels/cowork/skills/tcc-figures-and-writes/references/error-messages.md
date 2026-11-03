# Errors the connector returns

A failed call comes back as: `The request did not go through (<code>): <message>`. The code is
stable; the message is safe to show. Say it in plain words, add what the person can do, and
never substitute an estimate.

| Code | What it means | What to tell the user |
| --- | --- | --- |
| `not_authorized` | The person is not on the writer list, or may not see this. | They can read but not change records here. Ask a platform administrator to add them as a writer. |
| `client_not_authorized` | The person may not see this client. | They do not have access to that client. |
| `client_not_found` | No such client in the book. | Check the name; offer to search again with `client_resolve`. |
| `ambiguous` | More than one client fits. | Show the candidates and ask which one. Never pick. |
| `not_calculated` | No calculation has reached that client-year. | The platform has not looked at it yet. That is not the same as "nothing found". Do not report zero. |
| `year_not_authored` | No statute is authored for that programme and year. | The platform declines by name rather than estimate. Report that, and offer the years it does cover. |
| `invalid_arguments`, `rejected`, `capability_error` | The request was well formed but not acceptable (a lever out of range, a move the lifecycle does not allow). | Quote the message and ask what they would like instead. |
| `confirmation_expired` | The preview is too old. | Prepare the change again and ask again. |
| `confirmation_replayed` | That preview was already used. | The change was probably made. Read the record back before doing anything else. |
| `confirmation_wrong_user` | The preview belongs to someone else. | Each person confirms their own changes. |
| `rate_limited` | Too many calls in a short time. | Wait a minute and try once more. Do not loop. |
| `timeout`, `api_unreachable` | The platform did not answer in time. | Say it did not answer. For a read, try once more. For a commit, read the record back before trying again, because the change may have been made. |
| `request_too_large` | The text was too long. | Send it in parts. |
| `internal_error` | The platform failed unexpectedly. | Say so, and do not retry in a loop. |

If a commit times out, never assume it failed. Prepare nothing new until you have read the
record back with the matching read tool (`claim_cell_history`, `findings_list` or
`client_situation`).
