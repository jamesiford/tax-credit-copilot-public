# routes_drafts_runs execution log

## Preflight

- Worktree and branch match the W2 allocation; initial tree clean.
- Approved oracle reports CPython 3.12.13. No live services are used.
- Read composition, host, schema provisioning, persistence, sources/auth/AI,
  certified Domain reports, port map, route inventory, contract findings,
  coverage and authentication/normalisation specifications.
- Scope is 23 operations. Shared executor, transaction, source observation,
  selected-year durability and override ordering are inherited, not reimplemented.
- No dependencies added. Existing BCL, mediator and registered adapters suffice.
- Retain the named F-14 valid-request exceptions. F-15 draft-list author checks
  and F-18 disconnected latest-manifest behavior are defects, not features.
- Native provisioning and periodic compute heartbeats remain outside this
  session's ownership; report measured boundaries rather than claim them solved.
## Stage 1 evidence

- Implemented real batch planning, preview, requester-scoped acceptance/replay, visible reads and controls.
- `dotnet build -warnaserror`: passed, zero warnings/errors.
- `dotnet test tests\TaxCredit.Api.Tests --filter FullyQualifiedName~DraftsRuns.BatchTests`: 2 passed (49 seconds).
- The heavy test accepts through ordinary HTTP discovery, launches the existing finite Worker against the accepted database, opens a separate persistence connection, verifies terminal state plus Gold/manifest/claim publication, then replays acceptance and proves drain publishes nothing twice.
- Formatting requires whole-project invocation here: include-path invocations silently selected zero documents. Whole-project whitespace formatting changed only feature-owned files.

## Stages 2 and 3

- Added all remaining client/base-year, draft and program catalogue operations.
- Scoped each owned mediator dispatch at the API boundary after proving root
  handler resolution retained a source reader across P1/P2 resets. Runtime
  overlay precedence itself was correct. No shared lifetime was changed.
- Batch selection now follows portfolio candidate/engagement/declining rules.
  Restricted metadata and liveness are computed only from visible work.
- Draft controls enforce canonical size, depth, year count, UTF-8, optimistic
  versions, validation currency and stable-identity reviewer separation.
- Added real CPython 3.12.13 exported-member oracle with Unicode/numeric edge
  cases; every member byte and per-file hash is compared, not just ZIP shape.
- All 11 owned tests passed, including four heavy integrations (8m31s total).
  Direct P1 TY2025 result is 107/77/72. Actual finite Worker publication and
  same-timestamp save/change/clear/later-save recalculation both passed.
- Fixed omitted preview client ID to return modeled 422 instead of a missing
  dictionary-key exception. Explicit client payroll remains refused.

## Final gates and mandatory stop

- Whole build with warnings as errors passed; whole formatter verification
  passed. The final build/format rerun after the last assertion fix also passed.
- Complete fast suite: 720 tests, 711 passed, 9 failed. Seven non-API projects
  passed. One new lease test assumed Claim refreshed batch status; corrected
  the assertion to the existing queued state preserved by rollback.
- Final owned fast suite: 8/8 passed, including expiry during synchronous
  compute and the preview client-ID regression.
- Eight shared failures remain: five draft fixture endpoint collisions, one
  batch fixture endpoint collision, a placeholder 501 versus real dry-run 202,
  and standalone registration validation without API feature discovery.
- The placeholder assertion and colliding fixtures require unowned test
  changes; hard stop 1 applies. No test suppression or product 501 shim added.
- Three full main scenarios were replayed with fresh absolute diagnostics.
  Raw wrapper group count is 243, 35 passing / 208 failing (14.40%), before
  tier/incidental/improvement handling. No 98% or cap claim was made.
- Full all-scenario classification stopped at the ownership boundary.
  Temporary API helper stopped; no Worker races the replay; nothing pushed.
- See HALT and implementation reports for exact failure names, registration
  seam, override/enqueue atomicity limitation and next integrator actions.
