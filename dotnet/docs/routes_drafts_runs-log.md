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
