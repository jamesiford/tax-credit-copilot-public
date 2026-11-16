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
