# HALT: routes_drafts_runs

Hard stop 1: the mandatory whole-solution fast gate requires changes outside
this session's ownership. No unowned files were changed.

## Evidence

`dotnet build -warnaserror` and whole-solution format verification passed.
The complete `Category!=heavy` run finished with 711 passing and 9 failing
tests across 720 tests. One failure was a new lease-test expectation:
claiming a lease does not itself refresh the batch's queued status. Correcting
that assertion leaves all 8 owned fast tests passing. The other 8 failures are:

1. Five cases of
   `Framework.PagingTests.Paging_validation_is_not_a_storage_id_constraint`:
   `AmbiguousMatchException`, two `GET /api/v2/program-drafts` endpoints.
   The shared discovery fixture registers its own route alongside the real
   feature. Its successful response assertion is also the fixture-only
   `{"total":1,"items":0}`, not the product's draft-list contract.
2. `Contract.RuntimeTrustTests.Agent_shape_acting_precedence_original_client_rights_and_delegated_non_elevation_are_real`:
   `AmbiguousMatchException`, two `GET /api/v2/run-batches/{batch_id}` endpoints.
3. `Contract.RuntimeEnvironmentTests.Signed_caller_limits_are_rebuilt_reset_and_not_shared_by_the_acting_user`:
   `Expected: 501`, `Actual: 202` for the valid reader batch dry-run.
   The task explicitly requires retaining that valid-request exception and
   implementing the real operation. Returning the old placeholder would
   defeat the task.
4. `Framework.ProviderSelectionTests.Native_SQL_Blob_and_group_policy_select_real_adapters_without_opening_a_live_connection`:
   standalone `AddApplication().AddInfrastructure().AddTaxCreditRuntime()`
   validates automatically scanned handlers without discovering the API's
   feature module. Dependencies including `BatchAccess` and `DraftLifecycle`
   are therefore missing. Ordinary API discovery does register them.

## Attempts and boundaries

- Implemented all 23 owned operations through ordinary discovery and the
  existing mediator, repositories, executor and publication transaction.
- Ran owned integration tests: 11/11 passed, including finite Worker,
  direct-run, ordered override recalculation and both draft workflows.
- Ran the whole build, formatter and fast suite rather than claiming the
  focused tests were the full gate.
- Reran all final owned fast tests after fixing the lease assertion and the
  omitted preview-client-id regression: 8/8 passed.
- Did not hide a real route from tests, return a placeholder 501, suppress a
  test, modify shared fixtures, loosen replay, or create a second executor.
- Stopped the temporary API helper. Nothing was pushed.

## Required integrator action

Authorize updating the shared framework/contract fixtures to compose with
implemented feature groups, and choose whether standalone provider validation
must discover feature registrations or register feature test dependencies.
The latter is an integration design issue, not claimed fixed here.

Then rerun the whole fast suite and all 12 semantic scenarios. Three main
scenarios were replayed before the stop, but their raw wrapper result is not
the conductor's tier/improvements-adjusted gate. The 98% replay threshold is
not claimed. See `ROUTES-DRAFTS-RUNS-REPORT.md` for exact evidence, remaining
risks, and callable operation contracts.

## Conductor-requested recheck

The resumed request was investigated without changing the allocation, shared
tests, shared registration or replay comparisons. A fresh complete command
chain ran:

```
dotnet build -warnaserror --nologo -v quiet
dotnet format --verify-no-changes --no-restore --verbosity quiet
dotnet test --no-build --filter "Category!=heavy"
```

Build and format passed. The full fast result is now **712 passed / 8 failed /
720 total**: all eight failures are exactly the shared failures enumerated
above. Local output is `dotnet/artifacts/drafts-runs-resume-fast.log`.

The latest conductor's complete semantic output was inspected directly, not
replaced with the policy-free wrapper. Its exact-template denominator is 323,
with 79 passing cases (24.5%). Ten distinct case failures singled out by its
numeric guard were verified from its raw JSON:

| Scenario | Case | Field | Recorded / actual |
| --- | --- | --- | --- |
| p1_auth | reader.run | validation.queries_run | 20 / 17 |
| p1_auth | writer.run | validation.queries_run | 20 / 17 |
| p1_writes | ok.post-api-v2-clients-client-id-runs | validation.queries_run | 20 / 17 |
| p1_auth | reader.batch-dry-run | preview.never_run | 1 / 0 |
| p1_auth | writer.batch-dry-run | preview.never_run | 1 / 0 |
| p1_auth | ratelimit.writer-batch-1 | preview.never_run | 1 / 0 |
| p1_auth | ratelimit.writer-batch-2 | preview.never_run | 1 / 0 |
| p1_auth | ratelimit.reader-batch-1-own-bucket | preview.never_run | 1 / 0 |
| p1_program_drafts | create | draft_id | numeric-looking UUID strings differ |
| p1_program_drafts | second-create | draft_id | numeric-looking UUID strings differ |

These are not all implementation errors that can safely be fixed here:

- The five `never_run=0` answers follow earlier successful direct runs and
  their actual durable manifests. The task explicitly forbids manufacturing
  historical disconnected-manifest behavior. Returning 1 after the accepted
  run would assert a false state. The guard refuses to waive the changed count.
- Draft IDs are UUID **strings**, not figures. Both generators produce valid
  UUIDs with numeric-only hex digits at these counter values. The task
  explicitly forbids burning UUID draws just to reproduce startup artifacts.
  The conductor nevertheless parses the strings as changed numbers and
  rejects the incidental-identity entry.
- `RuntimeCalculationRegistration.cs` injects literal
  `ClientCalculationConfig.Section9QueryCount=17`. The shared
  `GoldValidation.cs` has 20 named static queries plus additional per-table
  checks. The feature returns the runner's result faithfully. Changing only
  the HTTP result to 20 would not repair the shared metadata source; changing
  the authoritative registration/validator contract is outside ownership.

Even ignoring the three query-count cases, those seven rejected cases cap
the attainable result at **316/323 = 97.83%**, below 98%, if every other case
were fixed. Including all ten gives 313/323 = 96.90%. This is a conservative
upper bound, not a claim that the other failures are already resolved.

The integrator must resolve the policy/guard mismatch for UUID strings and
post-publication operational state, as well as grant an explicit shared-file
allocation for fixture/composition and query-count corrections. Removing this
HALT file would conceal an active mandated stop; restoring placeholder 501s,
false `never_run` counts, dummy ID draws or output-only query counts would
violate the task. No such workaround was applied. No replay threshold or
test was loosened, and no new full replay was claimed: the conductor's
complete all-scenario result already demonstrates this boundary.
