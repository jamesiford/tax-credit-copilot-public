## Your role

Implement the 24 operations in `claims_artifacts_rules` using application features under `dotnet\src\TaxCredit.Application\Features\ClaimsArtifactsRules`, endpoints under `dotnet\src\TaxCredit.Api\Endpoints\ClaimsArtifactsRules` and tests under `dotnet\tests\TaxCredit.Api.Tests\ClaimsArtifactsRules`. The surface includes claims/coverage/lifecycle/engagement, assessment, portfolio and client situation, findings, packages/downloads, rules/ingested rules and channel audit.

The route registry assigns `GET /api/v2/portfolio` and `GET /api/v2/clients/{client_id}/situation` here, although the ReadsCalc brief mentions portfolio. ReadsCalc owns deferred `tools\portfolio`/`tools\discovery` application work, not these HTTP routes. Existing certified claims, coverage and credit modules are dependencies, not code to port again. Shared host, persistence implementations, byte adapters, other endpoint groups and web retrieval internals are outside this feature's implementation scope.

## Preflight

Read `dotnet\docs\DOMAIN-SLICE-REPORT.md`, `dotnet\docs\port-map.md`, the claims/coverage, validation and CAP sections of `dotnet\docs\findings.md`, `dotnet\docs\PERSISTENCE-REPORT.md`, `dotnet\docs\SOURCES-AUTH-AI-REPORT.md`, `dotnet\docs\COMPOSITION-REPORT.md`, `dotnet\docs\COMPOSITION-SCHEMA-PROVISIONING.md` and `dotnet\docs\HOST-ARCHITECTURE.md`. Read `contract\CONTRACT-REPORT.md` sections 4-5, `contract\FINDINGS.md`, `contract\COVERAGE.md`, auth documentation and this group's scenarios/recordings.

Build a 24-operation evidence map from `dotnet\docs\route-groups.json` and `dotnet\src\TaxCredit.Api\Contract\routes.generated.json`. Include source dependencies, trust metadata, failure shapes, persistence side effects and any cross-group setup captures. Use ordinary W1b composition: persistence and byte stores are real, feature modules configure services before Build, and exact endpoint method/templates replace their own stubs. Do not introduce another startup graph.

Reconcile partial `application\assessment.py`, `assessment_claims.py` and `qc_resolutions.py` with the existing `ClientAssessment`, `ProgramClaim`, `QcResolutions` and W1 stores before choosing remaining work. The snapshot port map predates real stores and the composition repairs. Also inspect `backend\application\claim_package.py`, `claim_package_service.py`, artifact services and the corresponding tests: the live package builder is not the sealed-reference `tools\build_approval_package.py`.

## Stage 1: settle package fidelity and persistence seams first

Prototype the package service against real seeded Gold and claim repositories before completing the broad route set. `application\claim_package.py` specifies five sheets, in order: Coverage, Locations, Installments, Provenance and Disclaimer. Preserve their explicit column allowlists, typed cell values, per-sheet row counts, generated attribution and provenance. This builder reads stored results; it never calculates payroll and never needs private reference data.

The XLSX is a ZIP whose uncompressed members are still compared by name, size, hash and order. A workbook that looks the same in Excel is not evidence that the recorded member contract holds. Establish compatibility for the actual workbook XML, styles, relationships, properties and dates using the recorded package download and `test_package_app.py` before committing to a serialization approach. Existing package ownership does not include shared package/project files; first determine what the prepared projects and BCL ZIP/XML support. Record a precise dependency obstacle if a required library cannot be referenced within the allocated paths.

Compose package creation with `IArtifactByteStore` and `IArtifactRepository`: create bytes, publish immutable storage, then record accurate metadata/supersession. Downloads look up existence and client ownership before visibility decisions, validate metadata/prefix rules, and record access outcomes including missing bytes and refusals. Return API-relative links, content type/name, no-store and actual content hashes, not storage credentials.

Use `contract\recordings\p1_artifacts_ai.jsonl` cases `package.create`, `package.create-again`, `package.no-year`, `package.unknown-client`, `package.year-uncalculated`, `artifact.download`, `artifact.wrong-client` and `artifact.unknown`. F-5's recorded duplicate is a 500; the W1 byte adapter exposes a typed immutable-object conflict. Inspect the current generation-bearing path in `claim_package_service.py` rather than assuming the report's older run/hash-only path description. Establish a deliberate duplicate outcome at the request boundary without overwriting bytes or inventing metadata success after failed storage.

Checkable result: one package travels from seeded Gold/claims through the real byte/metadata services to an authorized download; member comparison is demonstrated, repeat-create behavior is explicit, and no employee identifiers/names/tax IDs appear in workbook contents.

## Stage 2: implement claims, assessment, portfolio and situation

Implement create, assess, engagement, coverage-by-client and portfolio coverage, cell read, cell transition and lifecycle. Use Domain `ProgramClaim`, claim readings, `Coverage` and situation logic for derived amounts/status, and W1 repositories for history. Complete only the missing application orchestration from the three partial modules. Assessment must retain its selected/multiple-year sweep and claim refresh semantics; do not replace it with a single requested-year calculation.

F-8 concerns duplicate create requests, not a prohibition on legitimate later same-cell history. Choose the supported claims-design request outcome and test it separately from transition/assessment appends. W1 storage identity collisions currently throw `InvalidOperationException`; classify the known duplicate boundary specifically, not every invalid operation as a conflict. Read history after reopening and prove that another client/program cell remains untouched.

Implement `GET /api/v2/portfolio` and client situation with recorded filters, ordering, totals, paging and money. Cover `p1_query_edges:portfolio.scope`, `portfolio.sort-bogus`, `portfolio.order-bogus`, `portfolio.status-bogus`, `portfolio.repeated-limit`, `portfolio.offset-past-end` and `unknown.situation-unknown`. Compare P2 `portfolio.limit-2-offset-1`, `portfolio.near`, `portfolio.program`, each client's situation and `portfolio.after-writes`.

ReadsCalc's future portfolio builder is not on this parallel session's base. First inventory what can be assembled from existing W1 claim/Gold/source ports and certified coverage/situation helpers. Keep any local route orchestration in this feature; describe the exact reusable ReadsCalc service binding needed at integration instead of depending on an absent future class or copying its calculation algorithms.

Use `test_claims_api.py`, `test_claim_repository_contract.py`, `test_coverage_totals.py`, `test_assess_sweeps_all_years.py`, `test_fictional_program_end_to_end.py`, `test_multiple_programs_per_state.py` and the recorded money cases `p1_writes:claims.create-money-*` and `claims.create-duplicate`.

Checkable result: claims writes and transitions append correct durable history, coverage/situation/portfolio report consistent recorded values, and assessment sweeps the intended years without altering the certified pipeline.

## Stage 3: findings, rules and audit surfaces

Implement findings list, resolve, reopen and history through `IFindingRepository`, preserving policy-versus-instance identity, resolution detail, actor/time, reopening audit and client/year isolation. Complete the application integration of `qc_resolutions` while preserving the distinction between ingestion QC resolution and findings lifecycle. ReadsCalc owns ingestion HTTP routes; publish/document a minimal usable application contract if those routes need this feature's new integration, without editing their files or assuming their new implementation is present.

CAP-10 records that the certified run command does not apply the QC-drop helper. Resolution annotations may affect their specified read path; wiring them into the writer would be a different figure-changing operation, not completion of this route task. Test resolution visibility and reopen history independently of run computation.

Implement rules listing, verify, ingested state, refresh, proposals, apply and changelog, including their recorded unavailable/not-configured surface. Verify uses existing pack validation and rule-library behavior. Apply has no hermetic successful recording because live ingestion is absent; exercise its captured 404/422/503 distinctions and make the external boundary explicit, rather than claiming a verified live success. The mutating GET refresh needs the existing access classification, not treatment as an innocuous cached read.

Implement channel-audit reads with the existing person-only metadata and repository filters; no gateway implementation belongs here. Use `test_ingestion.py`, `test_routers_through_the_mediator.py`, `test_rules_ingestion.py`, `test_channel_audit.py`, `test_audit_alerts.py` and the group's auth cases. W1b already retains the named F-14 `reader.assess` and `reader.rules-verify` valid-request exceptions; a new command annotation must not accidentally change those outcomes.

Checkable result: all remaining registered operations reach real application handlers, finding decisions survive reopening, audit reads enforce their distinct actor restrictions, and unavailable rule retrieval remains an honest dependency response.

## Stage 4: exercise the composed routes and expose remaining limits

Exercise new handlers through ordinary production feature discovery and seed-backed composition, including authorization before data access, request validation, duplicate/conflict boundaries, package download audit and scenario reset. Use complete relevant P1/P2 scenarios with fresh absolute diagnostic paths. `p1_artifacts_ai` has ReadsCalc and findings setup captures, and `p2_reads_writes` includes run writes from DraftsRuns: report those dependencies separately from owned feature failures.

Write `dotnet\docs\ROUTES-CLAIMS-REPORT.md` with the 24-operation/case map, completed partial-module behavior, package member results, duplicate decision, workbook privacy evidence, cross-feature contracts and any unavailable prerequisite. Distinguish local SQLite/fake-Blob proof from deployed Warehouse/Blob behavior. Include the unresolved operator provisioning for `tcc_ops.finding_audit`; this session is not an operator migration.

Checkable result: a subsequent integrator can locate each endpoint/handler/test and reproduce package, claims and findings behavior without treating a missing sibling route or live ingestion service as a tested success.

## Traps to expect

- `CONTRACT-REPORT` sections 4-5 distinguish validation arrays, string/object `detail` and top-level dependency errors. Existing JSON wire helpers preserve these; an all-purpose ProblemDetails response does not.
- F-9 and `findings.md` C-01/C-02: claim money retains Decimal scale and tie behavior. Actual deployed money DDL is DECIMAL(19,4), as corrected by Persistence, not the contract report's shorthand. Storage scale is not a reason to recalculate response money.
- F-17's unknown sort/status behavior is parameter-specific. Check captured schemas and handlers before adding enum refusals that were never specified.
- E-6 excludes container encodings, not XLSX XML/member contents, per-file hashes, provenance or stored byte integrity. A general ZIP exemption would miss a broken export.
- Pack validation already reconciles Python/library verdicts, keywords and paths; 764 corpus documents have different violation counts and wording is documented. Reuse `PackValidator` and the pinned adapter, not a new validator.
- `findings.md` M-01, C-09 and CAP-06/CAP-10 name figure-sensitive behavior. The transactional runner already repairs partial publication rollback; neither a route-level recomputation nor global QC application is needed.
- Strict fiscal leap shifts, SQL/projector zero-worksite differences, native AVG and live publication/Blob permissions remain unverified or owner-sensitive. Feature tests do not certify them.

## Evidence this plan is based on

- `dotnet\docs\DOMAIN-SLICE-REPORT.md`, `dotnet\docs\port-map.md` and `dotnet\docs\findings.md`: certified claims/coverage and the exact assessment/QC application remainder.
- `dotnet\docs\PERSISTENCE-REPORT.md`: durable same-cell histories, explicit identity conflicts, tenant-scoped reads, metadata/access auditing and actual monetary DDL.
- `dotnet\docs\SOURCES-AUTH-AI-REPORT.md`: immutable local/Blob byte stores, typed conflict/dependency failures and existence-before-visibility handoff.
- `dotnet\docs\COMPOSITION-REPORT.md`, `dotnet\docs\HOST-ARCHITECTURE.md` and `dotnet\docs\COMPOSITION-SCHEMA-PROVISIONING.md`: real feature composition, F-14 authorization exceptions and unapplied native finding-audit provisioning.
- `dotnet\docs\route-groups.json`: portfolio/situation and all 24 operations belong here.
- `contract\CONTRACT-REPORT.md`, `contract\FINDINGS.md`, `contract\COVERAGE.md` and the named recordings: F-5/F-8/F-9/F-17, error shapes and package/member comparison.
- `dotnet\docs\pack-validation-deviations.md` and `parity\export_claims.py`: existing validation/claims evidence, not an assignment to recertify Domain.
- `backend\application\claim_package.py` and `claim_package_service.py`: five-sheet stored-result workbook and current generation-bearing immutable path; the sealed-reference exporter is a different tool.
