# integrate-W2 log

## Preflight

- Read the complete integration task, all four halt notes, available route
  reports, composition/host architecture, contract findings and auth/determinism
  protocols. The current policy supersedes earlier page-independent-total
  requirements: list metadata must retain recorded semantics.
- Oracle: CPython 3.12.13; imports resolve to this worktree.
- Baseline warning-as-error build and format pass. Fast tests: 960 passed,
  10 failed (970 total). Failures are stale 501 assertions, duplicate test
  probe routes and standalone provider composition missing feature modules.
- Baseline full semantic replay is running against isolated ordinary hosts,
  with explicit scenario profile and auth setup.

## Shared fixture repair

- Discovery/replacement tests now select two actual unimplemented GET operations
  from endpoint metadata. They prove replacement, singleton service discovery
  before Build, a single effective endpoint and an unrelated remaining 501.
  If insufficient stubs remain, they skip with an explicit reason.
- Removed obsolete draft-list and batch-detail test probes; tests now exercise
  the real implemented endpoints, including count-first BigInteger paging.
- Provider-selection validation composes the production feature-discovery
  modules. Runtime trust/limiter assertions now expect real handler statuses,
  while retaining denied-writer, reset and caller-isolation assertions.
- No dependency, threshold, recording or production calculation changed.
- Native-provider validation also exposed the unbound portfolio reference-data
  port. Runtime composition now binds genuine hire dates from the committed
  annual synthetic CSV and reuses the existing worksite label catalogue.
- Shared-repair gate: warning-as-error build, format verification and all
  **970 fast tests pass** (no failures/skips).

## Shared runtime integration

- The default mediator is scoped. Native composition now proves scopes do not
  retain one another's mediator or artifact lease.
- The runtime reports the actual 20 section-9 validation queries. Nine
  supplemental integrity checks remain; neither a literal count nor duplicated
  orphan checks stand in for the contracted query collection.
- Unit-list metadata follows the recorded page-sensitive semantics; independent
  filters still retain their existing reader metadata.
- CSV accounts expose their real source footprint and the established fixture
  display name, just as scope and AI already did.
- AI book ranking and portfolio/unit/employee summaries dispatch the same
  application queries as their pages. Client eligibility reads recorded method
  summaries and uses the existing credit service, including its recorded trail.
  Four ordinary-host regressions exercise these bindings without fake page facts.
- Warning-as-error build, format and **974 fast tests pass**, no skips
  (`artifacts/integrate-shared-final*`). An invalid new test argument was
  corrected to the existing public schema; no schema was expanded.
