# Claims, artifacts, findings, rules and audit: partial implementation

**Stopped at hard stop 1. Not accepted: the 98% replay and full fast gates are red.**
See `HALT-routes_claims.md` for the shared-file authorization needed to resume.
All 24 assigned operations have real endpoints/handlers in the ordinary production
discovery graph, but that is not a claim of full semantic equivalence.

## Evidence and gate results

- CPython 3.12.13 oracle imports this checkout. Only committed synthetic seeds
  and synthetic test rows were used. No live Fabric, Foundry, Entra or customer
  system was contacted, and no new dependency/project reference was added.
- Final whole-solution `dotnet build -warnaserror` passed with zero warnings and
  errors. Final whole-solution `dotnet format --verify-no-changes` passed.
- The conductor retry passes **all 12 feature integration tests**, including the
  heavy P2 portfolio test and a new same-host package/download/reset regression.
  The feature run took two minutes; P2 alone took 112 seconds.
- Final whole-solution fast run: **717 passed, 3 failed, 720 total**. All seven
  non-API projects pass; all remaining failures are the shared framework tests
  below. The claim-history test had taken 68 seconds in the reproduced loaded
  run, so it is now heavy under the task policy and retains all its assertions.
  Its artificial 30-second timeout was removed. The P2 test now sets its heavy
  timeout before sending requests and checks reset success.
- Two shared framework tests insist that `GET /api/rules` remain **501**; this
  task requires its implementation. The provider-selection test also validates
  auto-discovered handlers without invoking the feature module that registers
  their collaborators. Neither issue was hidden by changing production behavior
  or forbidden files.
- Formatting initially identified four owned import-order issues. Project-scoped
  formatting did not correct those diagnostics; explicit import ordering did.
  Final whole-solution verification passed.
- The retry reproduced and fixed the conductor's reset 500. The shared default
  mediator is a singleton that resolves handlers from its root provider. A
  package handler therefore retained the scoped artifact-generation lease until
  host disposal. The feature registers the existing mediator as scoped through
  ordinary pre-Build registration: no service-location workaround, second
  provider, reset bypass or changed shared file. Same-host create/download/reset
  and subsequent publication pass.
- `probe_claims_reset.py` launches and stops its own ordinary host on an
  OS-assigned port. `revision-reset-before.json` reproduces package 201 followed
  by reset 500 and no replay report. `revision-reset-after.json` shows reset 200
  and an actual report from unchanged `contract.replay --reset-url`; that replay
  still exits 1 for semantic differences. Report generation is not acceptance.
- Final gate logs: `revision-build-final.log`, `revision-format-final.log`,
  `revision-tests-feature-final.log`, and `revision-tests-fast-final.log`.

### Complete scenario replay, unchanged semantic comparator

Latest evidence: `revision-replay/board.json`, per-scenario `*-board.json`, and
`revision-replay/raw/*.json` / `*.md`. The retry reproduces the original
`replay-complete-1` counts below. Full scenarios, including sibling setup
and unrelated exchanges, ran against separate ordinary hosts, each on an
OS-assigned port with an isolated SQLite/byte directory.

| Scenario | Group cases | Raw passed | Raw failed |
|---|---:|---:|---:|
| p1_reads | 141 | 85 | 56 |
| p1_writes | 151 | 26 | 125 |
| p1_query_edges | 34 | 7 | 27 |
| p1_artifacts_ai | 12 | 6 | 6 |
| p1_auth | 32 | 18 | 14 |
| p1_workspace_unavailable | 2 | 1 | 1 |
| p2_reads_writes | 25 | 13 | 12 |
| **Total** | **397** | **156** | **241** |

**39.29% raw, not 98%. No adjusted/waived score is claimed.** The wrapper classifies
some CORS/OPTIONS exchanges by matching route shape rather than exact method.
Raw failures therefore include framework behavior as well as genuine feature
work. The improvements register is explicit, but no comparison was relaxed and
the runner does not apply waivers.

Examples to triage on resumption:

- Error-array English, redirect/HEAD/CORS headers and extra API-relative Location
  account for incidental differences. Do not copy framework accidents.
- Rules `recent_changes` use actual filesystem mtime, while the Python recording
  freezes it. Do not hardcode a fixture timestamp in production for this score.
- The W1 CSV source book calls its synthetic account `Synthetic fixture`; the
  recording calls it `Reference Dataset Client`. Decide the shared fixture/book
  contract rather than inventing customer names in this feature.
- Missing sibling operations consume different deterministic-ID sequences. For
  example the artifacts scenario's `boot.unit` is a ReadsCalc 501; package IDs
  subsequently differ. IDs are still generated through the injected source.
- `p1_workspace_unavailable` exposes a genuine remaining gap: portfolio currently
  propagates dependency errors rather than reproducing Python's degraded rows,
  null counters and per-client unavailable state.
- Oversized claim/engagement program codes and rule-verification attribution can
  reach storage bounds and produce 500. These need explicit request-boundary
  classification, not a blanket InvalidOperationException-to-409 catch.
- P2 `portfolio.after-writes` includes DraftsRuns run/ingestion setup, whose
  unimplemented sibling operations are not successes of this feature.

## 24-operation evidence map

All endpoint files below are under
`src/TaxCredit.Api/Endpoints/ClaimsArtifactsRules/`; handlers are under
`src/TaxCredit.Application/Features/ClaimsArtifactsRules/`. Test file names are
relative to `tests/TaxCredit.Api.Tests/ClaimsArtifactsRules/`.

The host performs recorded request validation and access classification before
dispatch. JSON errors retain `detail` families rather than universal
ProblemDetails. Queries read real ports; commands run through the in-house
mediator authorization/audit pipeline. Authenticated attribution overrides
supplied actors. The named F-14 valid-request reader exceptions remain unchanged.

| Operation | Endpoint file / application request | Sources and side effects | Evidence / failure family |
|---|---|---|---|
| POST /api/clients/{client_id}/packages | PackageEndpoints / Packages.CreatePackage | Stored Gold + claims + latest completed run; immutable bytes first, then metadata/supersession; Writer | PackageTests; package.create/create-again/no-year/unknown-client/year-uncalculated; 201/409/422 |
| GET /api/clients/{client_id}/artifacts/{artifact_id} | PackageEndpoints / Packages.DownloadArtifact | Metadata existence, client ownership/visibility, prefix/content validation, bytes, access audit | PackageTests; artifact.download/wrong-client/unknown; 200/403/404/422/503 |
| GET /api/audit/channel | AuditEndpoints / Audit.GetChannelAudit | Person-only repository read with user/time/tool/limit filters; no gateway execution | RuleAuditTests; p1_auth agent.audit-channel; 200/403/422 |
| GET /api/claims/coverage/{client_id} | ClaimEndpoints / Claims.GetClientCoverage | Client-scoped claims/engagements, certified Coverage | ClaimTests + p1_reads coverage; 200/validation detail |
| GET /api/claims/coverage | ClaimEndpoints / Claims.GetPortfolioCoverage | Stored portfolio claims/engagements, certified totals | p1_reads/p1_writes coverage cases; 200/validation detail |
| GET /api/claims/cell/{client_id}/{program_code}/{tax_year} | ClaimEndpoints / Claims.GetCellHistory | Current and superseded cell history | ClaimTests; 200/404/422 |
| POST /api/claims | ClaimEndpoints / Claims.RecordClaim | Certified ProgramClaim; exact current duplicate boundary; append/supersede; Writer | ClaimTests; claims.create-money-* / create-duplicate; 201/409/422 |
| POST /api/claims/cell/{client_id}/{program_code}/{tax_year}/transition | ClaimEndpoints / Claims.TransitionClaim | Certified lifecycle transition and appended history; Writer | ClaimTests + AssessmentTests; 200/404/422 |
| PUT /api/claims/engagement | ClaimEndpoints / Claims.SetEngagement | Real scoped engagement history; Writer | p1_writes engagement cases; 200/422 |
| POST /api/claims/assess | AssessmentEndpoints / Claims.AssessClient | Certified ClientAssessment multi-year sweep, payroll/fiscal ports, real claim sink; named Open exception | AssessmentTests; reader.assess/writer.assess; 200/404/422 |
| GET /api/claims/lifecycle | ClaimEndpoints / Claims.GetLifecycle | Certified status/provenance/outcome/engagement enums, no write | p1_reads lifecycle captures; 200 |
| GET /api/v2/portfolio | PortfolioEndpoints / Portfolio.GetPortfolio | Stored claims, source book/footprint, authored coverage; no engine | ClaimTests heavy now passes, complete P1/P2 captures; 200/422; degraded path incomplete |
| GET /api/v2/clients/{client_id}/situation | AssessmentEndpoints / Claims.GetClientSituation | Recorded claims + certified CoverageSituation + book name; no engine | P1/P2 client situations and unknown.situation-unknown; unknown is assessed=false, not zero |
| GET /api/rules | RuleEndpoints / Rules.ListRules | Real flat pack catalogue, metadata, practitioner lookup; no write | RuleAuditTests + p1_reads; 200; conflicts with two shared stale 501 assertions |
| POST /api/rules/{code}/verify | RuleEndpoints / Rules.VerifyRules | Existing PackValidator + durable practitioner lookup; named Open exception | RuleAuditTests + reader.rules-verify; 200/404/422 |
| GET /api/rules/ingested/{state} | RuleEndpoints / Rules.GetIngestedRules | Real captured configs and per-value provenance | RuleAuditTests; 200/404/422 |
| GET /api/rules/ingested/{state}/refresh | RuleEndpoints / Rules.RefreshRules | Captured freshness/status; Writer classification despite GET; live retrieval unbound | RuleAuditTests; captured 200, live 503, unknown 404 |
| GET /api/rules/ingested/{state}/proposals | RuleEndpoints / Rules.GetRuleProposals | Explicit captured GA NEEDS_KEY and empty proposals | RuleAuditTests; GA 200, unsupported state 404 |
| POST /api/rules/ingested/{state}/apply | RuleEndpoints / Rules.ApplyRules | Writer; honest unavailable external ingestion boundary, no pretend mutation | RuleAuditTests; captured 404/422/503; no live-success claim |
| GET /api/rules/ingested/{state}/changelog | RuleEndpoints / Rules.GetRuleChangelog | Known captured config, no fabricated applied history | p1_reads/rule cases; 200/404 |
| GET /api/findings/{client_id}/{tax_year} | FindingEndpoints / Findings.ListFindings | Certified QcDetector + real decision overlay; policy vs instance grain | FindingTests + p1 artifacts boot.findings; 200/404/422 |
| POST /api/findings/{finding_id}/resolve | FindingEndpoints / Findings.ResolveFinding | Durable scoped decision/detail/attribution, append/supersede; Writer | FindingTests; assign needs keep_worksite; 200/422 |
| POST /api/findings/{finding_id}/reopen | FindingEndpoints / Findings.ReopenFinding | Close old decision, preserve history, append reopen audit; Writer | FindingTests; independent from payroll calculation; 200/422 |
| GET /api/findings/{client_id}/{finding_id}/history | FindingEndpoints / Findings.GetFindingHistory | Client-scoped immutable decision history | FindingTests repository/route captures; 200/validation detail |

## Package fidelity, privacy and duplicate behavior

`PackageTests.Seeded_package_matches_every_recorded_member_and_download_is_audited`
compares all **13 uncompressed XLSX members**, in order, against the recorded
download: names, sizes and SHA-256 match. This covers sheet XML, dates, styles,
properties and relationships, not merely Excel appearance or ZIP container bytes.
The sheet order is Coverage, Locations, Installments, Provenance, Disclaimer.
Explicit allowlists retain typed cells and money strings. Row counts are a JSON
object, not serialized dictionary-entry arrays.

The package reads Gold/claim/run rows and never payroll or an engine. Tests scan
members for employee-id, record-token and tax-id column leakage; the allowlists
contain no employee identifiers/names/tax IDs. This is synthetic/local proof,
not a new certification of production data. Generated attribution and recorded
provenance remain present. A literal `=1+1` in attribution is an inline string,
with no spreadsheet formula elements.

Repeated package creation returns 201 with a **new full UUID generation**.
The recorded F-5 500 is not reproduced. The immutable byte write precedes
metadata publication; first-generation bytes are not overwritten and old
metadata is superseded. The download checks real size/hash, returns no-store,
the actual content digest and safe file metadata; its Location is API-relative,
never a storage URL/SAS. Served, denied, missing and corrupt-byte attempts on
registered artifacts are audited. Unknown identities return 404 without a
foreign-key-invalid audit row.

An identical direct claim assertion returns **409**, separately from legitimate
later same-cell evidence, lifecycle transitions and assessment refreshes, which
append history. `ClaimTests` proves decline/re-assess history and cell isolation.
Decimal money remains delegated to the certified domain; constants were not
changed.

## Partial modules and integration contracts

- Assessment orchestration delegates to certified `ClientAssessment`, preserving
  selected/all-year sweeps and the prior year as an input. An initial claim's
  identity/time is normalized through host seams; its calculated fields are not
  reimplemented. Refresh retains the existing decision/filing fields and appends
  new evidence. Fiscal metadata flags assumptions; a real window does not
  masquerade as an assumption note.
- `IIngestionQcDecisions.Snapshot(client, year)` supplies a fresh certified
  `QcResolutionStore` to an explicitly opted-in ingestion read.
  `ResolveIngestionQc` is a mediator Writer command backed by `ILookupStore`,
  namespace `ingestion_qc`. It is separate from finding lifecycle decisions.
  ReadsCalc can resolve this port through the ordinary feature graph; no
  ReadsCalc file or certified run writer was changed. CAP-10 remains: annotations
  are **not** globally applied to run computations.
- Portfolio/situation use existing claim/source/Gold seams and certified claims
  helpers, not an absent future ReadsCalc class. The future reusable binding is a
  stored-read portfolio page service accepting claims, client book, guarded
  footprint and priceable-state readers; it must retain full-history trend
  independently of year filtering and typed degraded-read semantics. This
  feature's incomplete degraded orchestration is not that completed service.
- Rule verification uses a separate global `rule_verification` lookup.
  Display-only legacy catalogue pins remain distinct from operational filing
  assertions. Rules retrieval beyond the captured surface remains unbound,
  consistently unavailable rather than a claimed successful live application.

## Deployment and owner-sensitive limits

All exercised persistence is **local SQLite and immutable local fake-Blob bytes**,
not deployed Warehouse/Blob permission or transaction evidence. No operator
migration was attempted. Native `tcc_ops.finding_audit` still needs the operator
provisioning identified by W1b.

Preserved figure-sensitive behavior requiring owner review: captured ingestion
overriding year-resolved wage basis/measuring date/pay codes (M-01), first-program
credit pricing in multi-program states, and CAP-10's unapplied QC-drop helper.
F-14 reader assessment/verification outcomes stay unchanged under the explicit
task exception; do not silently tighten them during integration. Strict fiscal
leap shifts, SQL/projector zero-worksite differences, native AVG, and live
publication/Blob permissions are not certified by these tests.

Reproduce the focused feature tests from `dotnet` with:

```powershell
dotnet test tests\TaxCredit.Api.Tests\TaxCredit.Api.Tests.csproj --filter "FullyQualifiedName~ClaimsArtifactsRules&Category!=heavy"
```

For the complete 12-test feature check, including the slow synthetic P2 reset
and same-host reset regression, omit `&Category!=heavy`.

`replay_claims.py` invokes the unchanged replay wrapper, starts/stops a separate
ordinary host per scenario, verifies readiness, uses OS-assigned ports, and
retains raw diagnostics. Use a fresh absolute `--out` directory. Its database and
byte subdirectories are temporary synthetic state, not report artifacts to commit.
