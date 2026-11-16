# HALT: routes_reads

## Trigger

**Hard-stop 1: a change outside the owned paths is needed.** The 29 owned
operations are implemented, but the required fast-test and 100% replay gates
cannot honestly be claimed. Work stops at this committed checkpoint rather
than editing shared code, hiding failures or manufacturing a passing score.

## What happened and what was tried

1. The ordinary feature module and endpoint discovery build successfully.
   Whole `dotnet build -warnaserror` and formatter verification passed. Final
   owned fast cases passed 28/28 in 15 seconds; the annotation/reset case also
   passed before being tagged heavy. Portfolio tests passed 15/15 including P2. Four
   isolated P2 forecast recording comparisons passed. The remaining unreported
   heavy cases are not claimed.
2. The whole fast suite reported **723 passed, 13 failed**. Framework tests map
   their own `GET /api/scope` probes, now colliding with the real scope endpoint
   (`AmbiguousMatchException`). They also assert exactly one matching endpoint.
   Endpoint order is not a valid repair: it leaves the duplicated contract.
   Provider-selection validation calls `AddApplication` without feature
   registration and cannot resolve the newly discovered handlers' collaborators.
3. Six complete scenarios through normal API startup produced **241/514 raw
   ReadsCalc cases passing (46.89%)**. Existing comparer and recordings were
   unchanged. Missing sibling handlers are reported separately, not implemented
   here and not waived as successful owned behavior.
4. Investigation traced ordinary P1-to-P2 source/fiscal mismatches to the shared
   singleton mediator: `Application/DependencyInjection.cs` registers it as a
   singleton; `Messaging/Mediator.cs` resolves scoped handlers from the captured
   root provider. Thus scoped source services retain the first profile.
   Isolated P2 hosts pass full comparisons, whereas the multi-reset normal host
   returns the CSV fixture client and assumed fiscal windows. Fixing handler
   resolution belongs in shared composition, not a feature-level service
   locator, test-name switch or replacement mediator hidden inside ReadsCalc.
5. A separate policy conflict remains: Stage 2 requires page-independent
   population counts, while Python/W1 recordings bound them by `Limit`.
   `unit.limit-1` records 1/1 against the actual 21/10 population; P2 unit detail
   records 3/3 against 26/13. Existing unbounded Gold ports produce honest totals
   and focused tests pass. No numeric waiver or recording edit was made.

## Human/conductor decisions required

- Authorize a shared mediator lifetime/current-scope fix and validate it with a
  P1 -> P2 -> P1 reset test on one ordinary host.
- Update framework probe tests to use a non-business probe URL or define a
  generic real-endpoint override contract; make standalone provider-validation
  tests use the agreed feature composition. Relevant files are outside this
  session's allowed test/API folders and were not edited.
- Reconcile honest unfiltered counts with the unchanged-number replay rule.
  Decide whether to refresh the defective metadata recordings; never waive
  changed calculated figures or silently weaken the comparator.
- Supply the real outer `IPortfolioReferenceData` adapter for separate
  hire-date reference data before wiring sibling portfolio/discovery consumers.
  W1 pay-period data cannot legitimately invent that count.
- Retain the figure-sensitive M-01, first-program pricing and fiscal limitations
  listed in the main report pending their separate owner decisions.

## Preserved state and restart

See `ROUTES-READS-REPORT.md`, both application handoffs, the delimited port-map
addendum, improvements register and `status/routes_reads.json`. No Domain,
Python, shared host, infrastructure, sibling feature or external worktree source
was changed. No package or live integration was introduced. The API/replay
helpers owned by this session were stopped; no unrelated process was killed.

After the shared boundary is settled, rerun the whole build/format/fast gates,
the heavy parent token/year test, the unreported calculation recording cases,
and all six complete scenarios with normal feature discovery. The raw replay
files are local ignored artifacts under `dotnet/artifacts/reads-02*`; the main
report preserves their totals and specific failures independently of those files.
The last local reviewer-attribution correction compiled and passed owned fast
tests but has not received a fresh full replay.
