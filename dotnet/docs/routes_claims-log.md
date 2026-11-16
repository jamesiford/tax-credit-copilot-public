# routes_claims implementation log

## Preflight

- Branch `dotnet/w2-routes_claims`, initially clean. Only the allocated feature,
  endpoint, test and .NET documentation paths will change. No push or live service.
- Oracle verified: CPython 3.12.13; `application` imports this worktree's backend.
- Read the W1 domain, persistence, sources/auth/AI and W1b composition reports,
  schema provisioning, host architecture, route registry, contract findings,
  coverage, auth contract and contract report sections 4-5.
- The registry assigns exactly 24 operations to this feature. Ordinary production
  feature discovery is the registration seam; shared project files stay unchanged.
- Existing `ClientAssessment` already implements selected/all-year sweeps and
  status-preserving refresh. `QcResolutions` is certified but deliberately absent
  from the run writer (CAP-10). Neither is to be reimplemented.
- Packages use the live five-sheet stored-result builder, not the sealed exporter.
  The current Python service uses a fresh generation segment. Recorded F-5 is an
  older immutable-path collision; repeat creation will remain immutable and have
  an explicit request-boundary outcome.
- No dependencies added. First prototype uses BCL ZIP/XML; package XML/member
  compatibility, not Excel appearance, is the acceptance criterion.
- Native `tcc_ops.finding_audit` remains an unapplied operator prerequisite.

## Stage 1

- BCL ZIP/XML implementation passed both real-host package tests (17.8 seconds
  combined on the warm run). Every one of the 13 uncompressed members matched
  the recorded name, order, size and SHA-256, including dates/styles/properties.
- Workbook scans reject employee-id, record-token and tax-id column leakage.
  Only explicit stored-result allowlists reach sheets.
- Fresh generations use the full injected UUID. Truncating its prefix collided
  under deterministic IDs and could also reduce production entropy. Bytes are
  published before metadata. Repeats return 201, supersede only live metadata,
  and preserve earlier bytes. Wrong-client downloads are audited as denied.
- XML line endings are normalized to LF independently of the checkout OS.
  Text remains inline text, including formula-like input.
- Whole-solution warning-as-error build passed. No package/project changes.

## Stage 2 progress

- Claim commands use the certified domain lifecycle, readings and money; direct
  identical assertions return 409, while transitions and assessment refreshes
  append history. Coverage, situation and portfolio read stored claims only.
- Assessment delegates the complete sweep to `ClientAssessment`, normalizing
  only initial identities/time through host seams and attaching fiscal metadata.
- Preserved the named valid-request F-14 assessment exception (`Policy.Open`);
  other new command policies are Writer.
- P2 seed import exceeds the fast-test budget. The P2 integration test is
  heavy; its earlier bounded 60-second run was aborted during the P2 integration
  test. The exact blocking call was not established; it is not a behavior result.
  P1 remains the focused fast integration gate.

## Stage 3 and composed verification

- Findings list/resolve/reopen/history use real persistence. Focused integration
  proves visible decisions, append/supersession, immutable resolve/reopen audit,
  assign validation, and client isolation without applying annotations to runs.
- The ingestion-QC application contract is a separate lookup namespace with
  client/year-scoped certified snapshots; its command goes through the mediator.
  A test proves a fresh scope and reset; no ReadsCalc or writer file was changed.
- Rules use the existing registry, captured ingestion and PackValidator.
  Practitioner decisions persist through the lookup store. Captured refresh,
  NEEDS_KEY proposals and apply's 404/422/503 distinctions are exercised without
  live retrieval. The named F-14 reader verification exception remains Open.
- Channel audit uses real metadata storage and repository filters; a test proves
  pending/completed collapse, time bounds and limits. Person-only access remains
  enforced by the host and handler.
- Added artifact missing/corrupt-byte tests and a formula-like attribution test.
  Registered failures are audited, corrupt bytes never stream, and literal text
  never becomes a formula. Successful creation has an API-relative Location.
- Added a small three-year assessment test with real claim persistence. A sweep
  records all years; targeted refresh retains the proposed decision and prior-year
  base without mutating another year/program. This test passes in 3 seconds.
- Fixed typed-dictionary wire normalization, which the first replay exposed as an
  array of key/value pairs for package row counts. The package test now checks the
  actual JSON object shape in addition to the uncompressed members.
- No packages were added. Openpyxl-derived static OOXML assets carry their MIT
  copyright/license in `openpyxl-assets-LICENSE.txt`.

## Hard stop

- Whole-solution fast run: 4 failures, 718 passes, 722 total. Seven non-API
  projects pass. Three framework failures reproduce on a focused rerun; the
  fourth was the feature claim test's 30-second timeout under parallel load,
  which passes in isolation.
- Two shared framework tests explicitly require the newly assigned `/api/rules`
  operation to remain 501. A third bypasses feature-module registration while
  validating auto-discovered feature handlers. These are not silently waived.
- `HALT-routes_claims.md` records hard stop 1. No shared tests/composition files
  were changed and no further feature implementation was attempted after the
  conflict was established.
- Replay diagnostics retain raw differences, including sibling 501s and their
  downstream deterministic-ID effects. No comparison or threshold was loosened.
  The report distinguishes focused proof from incomplete semantic acceptance.
- All seven complete relevant scenarios finished on fresh, OS-assigned local
  ports and separate stores: 397 group-classified cases, 156 raw passes, 241
  failures (39.29%). The P2 scenario completed; its earlier integration-test
  timeout is not evidence that P2 endpoints cannot answer. No adjusted score is
  claimed. The diagnostic runner now exits nonzero for a red raw board.
- Final whole-solution build: passed, zero warnings/errors. Final whole-solution
  format verification: passed, after explicitly sorting four import blocks
  (the project formatter had left those diagnostics untouched).
- All ten focused feature tests passed together in 49 seconds. The QC reset
  test reached 23 seconds under concurrent verification load and is now heavy.
  No product behavior changed after that passing test run.
- Removed only the inspected synthetic probe/replay state directories; retained
  complete raw scenario diagnostics and reproducible probe/replay scripts.
- No local replay host remains. An attempted reuse of port 5187 encountered a
  sibling worktree's listener, so that attempt was stopped without terminating
  the sibling process; final scenario evidence exclusively uses OS-assigned
  ports and separate state. Initial multi-scenario reset failures were not
  repaired or claimed as passing; fresh-per-scenario hosting avoided that
  unverified shared-control issue.
