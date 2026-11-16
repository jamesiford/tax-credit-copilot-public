# HALT: routes_claims

Hard stop 1: the required fast gate cannot pass with the implemented rules route
without changing files outside this session's allocation.

The whole-solution fast test run failed. A focused rerun confirms that
`Framework.DiscoveryTests.Production_discovery_registers_services_before_build_and_replaces_exactly_one_stub`
and `Framework.RegistryTests.A_real_operation_replaces_only_its_stub_without_ambiguity`
both still require `GET /api/rules` to return **501**. This task explicitly assigns
that operation to this feature and requires a real handler. The implemented
production-discovered handler returns **200**. Both tests are in
`dotnet/tests/TaxCredit.Api.Tests/Framework`, outside the allowed paths.

I inspected the assertions and reproduced the failures; I did not edit the tests,
disable discovery, recognize test callers, return a fake 501, weaken comparisons,
or change shared composition. Updating those two stale test assertions or their
chosen deferred route needs a separately authorized shared-test change.

The same focused run also found a separate integration prerequisite:
`Framework.ProviderSelectionTests.Native_SQL_Blob_and_group_policy_select_real_adapters_without_opening_a_live_connection`
constructs `AddApplication().AddInfrastructure().AddTaxCreditRuntime(...)` directly,
without running feature modules. Mediator handler discovery sees the new handlers,
but their feature-module collaborators are not registered in that test graph.
Validation reports `Unable to resolve service for type ... CapturedRules`,
`RuleCatalogue`, and `ClaimPackageBuilder`. The ordinary API feature-discovery
graph works; its integration tests pass. Do not paper over this distinction with
service-location or a second startup graph.

The owner/conductor must authorize the shared framework-test update and decide
whether direct runtime construction must also compose feature modules. After that,
resume the outstanding semantic discrepancies and full gate work documented in
`ROUTES-CLAIMS-REPORT.md`. The 98% replay gate is **not achieved**.

All work remains local, synthetic and within allocated paths. No push, remote
change, live customer-service access or shared-file edit was made.

## Conductor retry

The reported reset 500 is now fixed within the allocated feature. The default
singleton mediator retained a scoped artifact-byte lease from a package request.
Registering the existing mediator as scoped through the ordinary feature module
releases that lease at request disposal. The same-host regression and diagnostic
probe pass; unchanged conductor-style replay now produces a report rather than
failing during reset.

Final retry evidence: all 12 feature tests pass, build/format pass, and the full
fast suite has 717 passes and the same three shared framework failures (720
tests). The seven complete scenarios still score 156/397, 39.29%, without
waivers. This HALT remains because neither the ownership restriction nor the
two contradictory shared 501 assertions changed. Removing it would falsely
claim that the mandatory hard-stop condition was resolved.

## Second conductor retry

The rejected formula-safety improvement entry was overly broad. Commit
`3054859` confines it to the downloaded Provenance-sheet XML member; the
integrity entry is confined to status. Neither now matches the actual
`package.create` artifact-ID discrepancy, and that discrepancy remains a
failure. No ID draws, money values, comparisons or thresholds were changed.

Build and format pass again; the fast suite again has 717 passes and the same
three shared framework failures. All twelve scenarios complete (1,769
exchanges). Exact-method ownership gives 98/316 raw passing owned cases
(31.01%) on these isolated hosts, without waivers. This differs from both the
older route-shape wrapper score and the supplied external conductor's adjusted
80/316; none is a passing result. See `retry2-summary.json`.

The request to repair failed gates does not remove the task's fixed owned-path
restriction or its explicit requirement to halt when a shared-file change is
needed. The two tests still assert 501 for an operation this task requires to
return a real result. No safe feature-local change can satisfy both. Keeping
HALT and false gate claims is required, not an accepted completion.
