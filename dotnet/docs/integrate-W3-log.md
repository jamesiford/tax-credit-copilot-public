# W3 convergence log

## Preflight and baseline

- Read both W3 reports, status files, improvement registers, W2 convergence,
  host architecture, platform risks, findings and normalization contract.
- Worktree started clean on `dotnet/integration`. Oracle is CPython 3.12.13.
  No live services are authorized or used.
- Root strict build and format pass; 1,545 fast tests pass, zero failures/skips.
  Evidence: `artifacts/w3-baseline-fast`.
- Ordinary isolated hosts launched with the conductor contract marker; health
  checked, public semantic replay run from `backend` with the worktree on
  `PYTHONPATH`, then both owned processes stopped.
- API: nine scenarios, 1,514 steps, 2,325 raw differing fields.
  Gateway: three scenarios, 255 exchanges, 528 raw differing fields.
  Evidence: `artifacts/w3-baseline-replay`.
- Existing gateway diagnostic: 233/255 pass (91.37%), 11 fully waived cases,
  56 unresolved fields in 22 cases, no numeric waiver. This is a local policy
  diagnostic, not a claim that the external conductor ran.
- Existing W2 group diagnostic predates the approved F-18 counter exception;
  its draft score rejects 36 explicitly permitted operational-counter fields.
  Its documentation-HTML numeric guard also differs from the conductor.
  Neither historical diagnostic is represented as the current conductor.

## Decisions

- Preserve figure-sensitive M-01 and first-program pricing unchanged.
- Preserve visible unresolved authorization outcomes for owner review rather
  than waive missing person-derived facts or change access on valid requests.
- No dummy UUID draws, canned results, broadened comparisons or new packages.
- Existing standalone gateway composition satisfies the shared-host cause;
  refresh the stale host architecture documentation and prove repeatability.

## Shared query validation repair

- Empty employee queries now return `empty_query` before applying a raw-row
  privacy decision to a request that selects nothing.
- Distinct-column validation distinguishes unknown, blocked and non-category
  columns, returns the `column` field, and runs before person-lane checks.
  No invalid question reaches the provider; valid-row authorization is unchanged.
- Four new focused cases prove those boundaries. The first run exposed that
  a non-category token still reached the earlier lane check; moving distinct
  validation ahead of that check fixed the actual ordering cause.
- Strict build, format and all 1,549 fast cases pass after correction.
  Evidence: `artifacts/w3-query-fixed-fast`.
- Public MCP and REST scenarios: 245 exchanges / 511 raw differences, down
  five from the same two baseline scenarios. Three formerly failed cases now
  pass: MCP empty query, MCP unknown distinct column, REST unknown distinct
  column. MCP 100/103 and REST 126/142 in the existing policy diagnostic.
  No new waiver. Evidence: `artifacts/w3-query-replay`.
- Added `run_wave_replays.py`: ordinary standalone executable launches,
  isolated stores, automatic health/profile/auth setup, exact public replay
  command and owned-process cleanup. Used it for both focused scenarios.
- Updated stale host composition documentation; no shared registration,
  dependency or test weakening was needed.
