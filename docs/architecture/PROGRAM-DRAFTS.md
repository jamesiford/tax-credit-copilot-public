# Program drafts: bringing on a new program from the portal

A draft is a **proposal**. The portal lets a person scaffold a new tax incentive program, fill in its pack and year packs,
validate them, preview a calculation on synthetic data, have a second person review, and export a reviewed bundle for a human to
commit. **A draft has no runtime authority**: nothing that calculates reads one, and the app never writes statute into the
rules folder in a deployed environment. A program becomes calculable only when a person commits the exported files to git and
deploys ([ADR-005](ADR-005-year-versioned-rules.md), [ADR-013](ADR-013-program-registry.md)). Everything a draft holds
is **not verified** until a person verifies each statutory value against the primary source: a draft that validates is well-formed,
not legally correct.

## Lifecycle

```
draft ──validate──▶ draft (clean) ──request review──▶ ready_for_review ──approve──▶ approved_for_export ──export──▶ exported
  │  ▲                                                       │
  │  └──── edit ◀──── needs_changes ◀── request changes ─────┘
  └── (errors) ──▶ needs_changes                  any open status ──withdraw──▶ withdrawn
```

- **Edit** replaces the documents wholesale and names the version the editor read; a stale version is a conflict (HTTP 409).
  Only `draft` and `needs_changes` are editable: a draft under review cannot change under the reviewer.
- **Validate** runs the same validator as `scripts/validate-rule-pack.py` over the stored documents (in memory, never written to a
  folder), plus draft-only rules: the code, state and names agree across documents; the program is not already registered; every
  number has a cited source (`credit.statutory_citation`, each year's `_year_provenance.source`); no `TODO` scaffolding remains; a
  draft may not claim `_verified`. Findings are field-addressed (`file`, `path`, `message`), errors first. Errors move the draft to
  `needs_changes`.
- **Request review** needs a validation of the *current* documents with no errors.
- **Review** approves for export or requests changes (a comment is required). When `PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER` is on
  (default outside `ENVIRONMENT=local`) the reviewer must not be anyone who created, edited or submitted the draft. Approval verifies
  nothing and activates nothing.
- **Withdraw** closes a draft; an exported draft cannot be withdrawn (its files may be committed).
- Every change appends an event (`tcc_ops.program_draft_event`, append-only) with the actor, the time and the statuses.

## API

All routes need the writer role and are person-only (an agent token is refused at the edge). Typed bodies and responses.

| Route | Purpose |
|---|---|
| `GET /api/v2/program-drafts` | page of drafts (`status`, `limit`, `offset`) |
| `POST /api/v2/program-drafts` | create from the scaffold template (`code`, `name`, `state`, `years`) |
| `GET /api/v2/program-drafts/{id}` | one draft with documents, validation, review record, `allowed_actions` and events |
| `PUT /api/v2/program-drafts/{id}/documents` | replace the documents (`expected_version`) |
| `POST /api/v2/program-drafts/{id}/validate` | validate and store the result |
| `POST /api/v2/program-drafts/{id}/request-review` | submit for review |
| `POST /api/v2/program-drafts/{id}/review` | `approve` or `request_changes` |
| `POST /api/v2/program-drafts/{id}/withdraw` | close the draft |

The read-only catalog (`GET /api/v2/programs`, `GET /api/v2/programs/{code}`) is open to any authenticated caller.

## Storage

Migration `0005` adds `tcc_ops.program_draft`, `program_draft_document` (one row per pack or year, at most 8000 characters each, so
it fits `VARCHAR(8000)`) and `program_draft_event`. SQLite for local development (`RUN_MANIFEST_STORE`); the Warehouse or Azure SQL
when deployed. Apply it with `python scripts/apply-migrations.py --target deployed`; until then `/api/ready` reports
`tables_missing` with that remedy.

## Settings

`PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER`, `PROGRAM_PREVIEW_ALLOW_CUSTOMER_DATA` and `PROGRAM_EXPORT_ALLOW_LOCAL_WRITE`: see
[ENV-VARS.md](ENV-VARS.md).
