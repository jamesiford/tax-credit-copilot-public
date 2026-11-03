# The write tools

Every write is `<name>_prepare` (changes nothing) then `<name>_commit` (needs the token from
the preview). Arguments to the commit go inside `arguments` and must equal the prepare call's.
Ask for what you are missing; never guess a client, programme, year or unit.

| Pair | Arguments | What the preview shows |
| --- | --- | --- |
| `finding_resolve_prepare` / `finding_resolve_commit` | `client_id`, `tax_year`, `finding_id`, `resolution` (`accept`, `assign`, `drop` or `flag`), optional `note`; `keep_worksite` is required for `assign` | The finding and the decision that would be recorded. A decision is appended, never overwritten. |
| `finding_reopen_prepare` / `finding_reopen_commit` | `client_id`, `finding_id` | The decision that would be withdrawn, leaving the finding open. |
| `claim_transition_prepare` / `claim_transition_commit` | `client_id`, `program_code`, `tax_year`, `status`, optional `decline_reason` | The cell's current status and the status it would move to. The lifecycle's own rules apply. |
| `claim_record_prepare` / `claim_record_commit` | `client_id`, `program_code`, `tax_year`, `status` | A claim the platform did not compute. It is stored as an unverified client assertion, and the preview says so. |
| `engagement_set_prepare` / `engagement_set_commit` | `client_id`, `program_code`, `scope` (`in_scope`, `out_of_scope` or `prospective`), optional `note` | Whether the programme is the firm's mandate for that client, and the previous value. |
| `base_year_set_prepare` / `base_year_set_commit` | `client_id`, `unit_id`, `base_year` | The location and the base year it would move to. It recalculates the client from that year. |
| `claim_package_create_prepare` / `claim_package_create_commit` | `client_id`, `tax_year` | The package that would be built for the client-year. |

After `claim_package_create_commit`, call `claim_package_link` with the same `client_id` and
`tax_year`. It returns a download address that works once, for the person who asked, for a few
minutes. Give the user the address as returned; do not shorten, store or reuse it. If it has
been used or has expired, call `claim_package_link` again.

Status values for the two claim tools: `not_assessed`, `assessed`, `proposed`, `declined`,
`claimed`, `certified`, `amended`.
