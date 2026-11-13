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
| `POST /api/v2/program-drafts/{id}/preview` | price the draft's year packs on synthetic data; writes nothing |
| `POST /api/v2/program-drafts/{id}/export` | download the deterministic bundle of an approved draft (zip); records the export |
| `GET /api/v2/program-drafts/{id}/export/manifest` | the bundle's manifest and hash, with no status change |
| `POST /api/v2/program-drafts/{id}/withdraw` | close the draft |

## Export bundle

Export needs an **approved** draft and moves it to `exported`, recording who took it. The bundle is a zip, **byte-for-byte the
same every time** for the same draft (sorted names, fixed timestamps, canonical JSON; the response carries `X-Bundle-Sha256`, and
`manifest.json` lists every file's SHA-256). It holds:

- `rules/<program>.json` and `rules/<program>/<year>.json` at their final repository paths (under `backend/`);
- `registry-patch.json`: the registry entry to add, with lifecycle `described` (`calculable` is derived, never typed);
- `validation-report.json` and `review-record.json` (who requested, who decided, the comment, the history);
- `COMMIT-CHECKLIST.md`: who must verify the statute (a person who is neither author nor reviewer, against the primary source), the
  files to place, the tests to add, the changelog line and the gates.

The app **never writes into the source tree in a deployed environment**. For developers only, `ENVIRONMENT=local` together with
`PROGRAM_EXPORT_ALLOW_LOCAL_WRITE=true` lets `write_local: true` write the pack and year-pack files into the rules folder; it never
edits the registry (adding the entry is the human step) and never overwrites a file. Committing the bundle is what makes the
program calculable, for its authored years only: `tests/test_program_draft_export.py` proves it by extracting a bundle into a copy
of the rules folder.

## Preview (no writes)

`POST .../preview` prices the draft's year packs with the engine's own functions (the Average Headcount from the draft's floors,
then the benefit step) over the committed synthetic sample payroll relabelled to the draft's state. It builds the pack from the
draft's documents in memory, touches no repository, run, claim or file, and returns the result without storing it
(`persisted: false`). Every response is labelled **"Preview, not verified, not for filing"** and counts the pack's unverified
flags. It refuses a draft that does not validate, and refuses a client's payroll (`dataset: client`) with HTTP 403 unless
`PROGRAM_PREVIEW_ALLOW_CUSTOMER_DATA=true` or the environment is classified synthetic. A year the sample does not cover is listed
under `declined`, never priced as zero. `tests/test_program_draft_preview.py` proves the preview agrees to the cent with the real
assessment of the same documents installed as a program, and that it reaches no service but the draft store.

The read-only catalog (`GET /api/v2/programs`, `GET /api/v2/programs/{code}`) is open to any authenticated caller.

## In the portal

**Program manager** (navigation: Prove it) sits beside the rule library. `/programs` has two tabs: the **catalog** (every registered
program with its lifecycle badge, authored years, a "Not verified" mark, whether it is calculable and the reason when not, and
engagement counts; sortable and filterable) and the **drafts** list. `/programs/<code>` is one program: its pack, each authored year
with whether it is still flagged and its source, the validator's findings and what blocks calculation. A program that becomes
calculable through a normal deployment appears in the catalog, the run dialog, the scope filters and the engagement controls with no
frontend change, because they all read the registry-derived program list.

**Add a program** (`/programs/new`, then `/programs/draft/<id>`) is a guided flow with a stepper that never blocks and says why a step
is unavailable:

1. **Basics**: code, name, state and optional starting years, with the programs already registered for that state (programs in one
   state are independent: each is calculated and assessed on its own program code). A federal program is shown as not runnable yet.
2. **Program pack**: structured fields for the supported model (a flat per-job credit over a One/Zero headcount) beside a validation
   panel, plus an advanced JSON editor that applies only what parses. Citations are required; an empty number stays `null`.
3. **Year packs**: add a tax year (an empty, flagged skeleton for the program's identity; nothing is copied from another year).
4. **Preview**: the labelled, no-write calculation on the synthetic sample.
5. **Review**: validate, request review, and the reviewer's decision (with the second-reviewer rule).
6. **Export**: the deterministic bundle, its manifest and hash, and the next steps for a person.

The draft **autosaves** after each edit naming the version it read; a conflict stops and says so rather than overwriting. The history
(who did what, and when) is on every step. Every step carries the "Not verified, and not live" notice.

## Storage

Migration `0005` adds `tcc_ops.program_draft`, `program_draft_document` (one row per pack or year, at most 8000 characters each, so
it fits `VARCHAR(8000)`) and `program_draft_event`. SQLite for local development (`RUN_MANIFEST_STORE`); the Warehouse or Azure SQL
when deployed. Apply it with `python scripts/apply-migrations.py --target deployed`; until then `/api/ready` reports
`tables_missing` with that remedy.

## Settings

`PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER`, `PROGRAM_PREVIEW_ALLOW_CUSTOMER_DATA` and `PROGRAM_EXPORT_ALLOW_LOCAL_WRITE`: see
[ENV-VARS.md](ENV-VARS.md).
