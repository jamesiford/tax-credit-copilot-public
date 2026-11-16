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
