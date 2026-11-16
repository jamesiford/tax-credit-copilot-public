# Sources, API trust, AI and artifact bytes

Session: `sources_auth_ai`; branch: `dotnet/w1-sources_auth_ai`.
Adapter evidence and the remaining certified-Domain boundary are stated below.

## Scope and evidence boundaries

The implementation provides Application ports and Infrastructure registration,
not HTTP routes, middleware, prompt agents, Gold/operational repositories or
exporters. Domain calculation and its certified CSV/parser code are unchanged.
Source metadata and artifact metadata/auditing are distinct from bytes.

All transport evidence is hermetic: fake HTTP/analytics clients, ephemeral
signing keys and committed synthetic/materialized fixtures. No live Fabric,
Entra, JWKS, Foundry, model or Blob call was performed. The prior connectivity
spike proved only a token-authenticated Warehouse connection, not source
freshness, metadata, throughput or source-version equivalence.

The original documentation-ownership halt was removed following the conductor's
explicit request to fix that gate and write this report and finish record.
No generalized permission to change other product paths was inferred.

## Integration contracts

### Payroll, SQL and fiscal sources

Rich Application source ports bridge the existing Domain `IPayrollSource`,
`IFiscalRuleSource` and `IProgramWageSource`; no second calculation engine or CSV
state machine was introduced. `AddTaxCreditCsvSources` reuses the certified
Infrastructure parser, keeps the fixture tenant isolated and never opens SQL.
`AddTaxCreditSqlSources` composes analytics access and accepts explicit fallback
configuration. `AddTaxCreditProgramWages` supplies the deferred committed
annual-payroll wage adapter to the existing RuleLibrary.

| Port | Owned capability |
|---|---|
| `IClientPayrollSource : IPayrollSource` | Fixture identity, client/portfolio payroll, three fiscal resolution methods |
| `ISourceReader` | Configuration state, accounts/book and payroll footprint |
| `ISourceCatalogue` | Payroll scope aggregates and synchronous shared scope |
| `ISourceFingerprintReader` | Fresh per-account count/max marker |
| `ISourceLookupReader` | Active client/global lookup candidates; Persistence supplies storage |
| Original `IFiscalRuleSource` / `IProgramWageSource` | Certified resolver bridge / existing percentage-of-wages credit path |

Source mapping/projection carries lineage and named coercion/default/drop
controls. The engine still trims fiscal windows, filters short periods and
collapses rows. SQL uses mapped, validated identifiers, explicit columns,
parameterized tenant/key conditions and bounded 900-ID batches. Analytics
connections and metadata caches are separate from Warehouse operational/Gold
pools. Source caches are instance/reset scoped.

`EntraAnalyticsTokenProvider` supports only
`https://database.windows.net/.default`, with injected credential acquisition,
expiry/refresh and cancellation. SqlClient connections are encrypted with
certificate validation; errors are redacted. No token was obtained from Entra
in this session.

Fiscal precedence is source rules first; only explicitly enabled classified
dependency failure can select a configured bounded fixture fallback. Missing or
unreadable source rules then consult client overrides before global overrides.
Malformed rules and typed strict failures are not outage fallback. SQL logical
lakehouse sources hold client fiscal rules; CSV does not. Source/provenance
diagnostics distinguish missing rules, unreadable sources and calendar assumptions.
Persistence implements the narrow lookup reader; these adapters do not own its
storage or migrations. Seeds carry inferred provenance rather than pretending
to be customer-authored classifications.

Version markers are deterministic account count/max-modified fingerprints, not
Delta IDs or historical snapshots. They cannot detect count/max-preserving
updates, cannot establish SQL endpoint freshness, and are not transactional
observations across source metadata and other reads. No Silver/OneLake/REST
version alternative or live type metadata was validated.

Verified source evidence: 72 fast tests; all 47 CSV parser golden cases;
the committed public 81/51/49 certification; generated aggregate SQL executed
offline through SQLite. One explicitly heavy test passed in 39 seconds:
197,094 projected P2 rows and controls matched CPython 3.12.13, and selected
GA TY2024 averages/eligible-ID sets matched for both methods, including reversed
input ordering. SQLite verifies fixture SQL semantics, not Fabric/T-SQL behavior.
No private 10,236/539/656 certification is claimed.

The wage adapter's existing RuleLibrary result is the recorded NY percentage-
of-wages path: average wage 101,528.17 and per-job benefit 6,599, not reimplemented
credit arithmetic. Materialized rows have deterministic fixture order. Selected
methods were checked under reversed order, but no general ordering guarantee
is asserted for live SQL without an authored ordering. First-row-sensitive
canonical collapsing remains the engine's responsibility (CQ-05).

Final source verification added actual `ClientRunResolver`/`ClientCalculation`
bridge tests; subsequent override/query corrections passed **108 fast + 1 heavy**,
109 total in 1 minute 26 seconds under SDK 10.0.404. Missing,
unreadable, unconfigured and malformed strict rules stop before payroll/engine/
persistence; valid source and override provenance and both conventions survive
the bridge. The materialized fallback is explicitly named in the window note.

**S2 remains partial at one certified-Domain boundary.** A stored leap window
2024-02-29 through 2025-02-28 cannot shift to `begins` TY2025 or `ends` TY2024.
The rich adapter refuses with `FiscalRulesMissing`, but the existing certified
Domain resolver substitutes an assumed calendar window. Its
`IFiscalRuleSource.RulesWithOverrides(accountId)` receives neither requested
year nor convention, so an adapter cannot reject that specific shift.
`FiscalPipelineBridgeTests` documents both cases and proves the calculation
reaches a rejecting payroll sentinel after substitution; no engine or
persistence executes in those probes. Domain remains unchanged. Resolving this
needs an owner-approved contextual fiscal-port overload, preserving inward
layering and the pure `WindowFromRule` helper. No blanket guarantee of strict
leap-shift rejection is claimed, and no duplicate fiscal arithmetic was added.

Malformed stored override date strings are parsed at the lookup boundary and
raise `FiscalRulesMissing` even under `assume`, before calendar substitution.
Tests cover client/global overrides, source-wins precedence, impossible/null
dates, timestamp suffixes and valid extended/basic/week ISO forms.

Python has a separate valid-input inconsistency: projection uses falsy-worksite
fallback while SQL uses `COALESCE(worksite, location)`. With zero worksite the
projector can return `SC` while SQL returns an empty state. Both Python paths
are preserved, with an explicitly named needs-human regression test. Replacing
SQL with `NULLIF` would affect program selection and potentially figures;
that reconciliation is not authorized here.

Source error contracts are sealed descendants of abstract `SourceFailureException` with `Code`,
`Dependency` and `Remedy`; messages equal safe codes, without raw upstream inner
exceptions. They include `source_not_configured`, `source_unavailable`,
`source_query_rejected`, `source_schema_mismatch`, `source_table_missing`,
`fiscal_rules_missing`, `unmapped_pay_codes`, `account_too_large`, and
`unsupported_nonfinite_payroll`. The last retains the existing FZ-04 Numerics
boundary rather than replacing non-finite payroll with a fabricated value.
Its concrete refusal is `UnsupportedNonfinitePayroll`; host catches may use
the abstract base. `ModelException` is sealed and classifies AI failures by kind.
Schema exceptions carry logical table/missing fields; size/code exceptions carry
counts/limits. Cancellation propagates. Host mapping must distinguish dependency/
strict refusals from invalid configuration and programming/query faults, using
the recorded route's error family rather than framework ProblemDetails.

Fiscal diagnostics retain `SourceState` (`present`, `empty`, `unreadable`,
`unconfigured`), provider (`source`, `materialized_fixture`, `override`,
`assumed_calendar`) and `FallbackUsed`. Successful empty source reads do not
activate outage fallback. The lookup port selects active client/global candidates
and checks inclusive effective dates. SQL unknown-client projection is null;
known empty-client projection is non-null and empty. Both yield no payroll,
but the distinction remains available. Unconfigured concrete reads throw.

Fingerprint kind is `account-count-max-modified-v1`: fresh raw count includes
projection-excluded rows; modification status is `column_missing`, `empty`,
`all_null` or `present`. Missing maxima remain null. Encoding includes count,
normalized maximum, status and sorted mapping hash, not client/server/database
identifiers. Provenance distinguishes real SQL from
`materialized-P2-offline-analytics-substitution-count-max` and unknown transports.

`SqlClientSource.ClearCache()` forwards to `SourceScanner.ClearCache()`.
Missing tables are not cached. Payroll, aggregates and fingerprints are uncached;
reconstruct CSV adapters to reload their upstream cache, and replace mapping/
lookup resolver instances when policy changes. Program wages are read on demand.

### Artifact bytes

`Application.Ports.Ai.Artifacts.IArtifactByteStore` publishes a new logical
object with `PutAsync` and returns exact bytes or null with `GetAsync`.
Persistence must perform artifact/client/batch existence lookup before
visibility checks, then apply metadata/prefix checks and record access.
The byte adapter cannot authorize a client, supersede metadata or audit a
download.

`ArtifactByteRegistration.AddLocalArtifactBytes` requires the explicit
environment `local`. `IsDurable` is false. An App Service deployment must use
`AddBlobArtifactBytes`; its HTTPS URL contains no key, SAS, userinfo or query.
The credential is injectable, otherwise `DefaultAzureCredential` is used.
Registration does not acquire credentials or contact Blob.

Local writes use a same-directory, create-new temporary file, flushed before
no-overwrite rename. Concurrent writers cannot replace the winning object and
readers do not see partial final bytes. Logical paths reject traversal,
absolute/drive/UNC/backslash/alternate-stream forms, empty/dot segments and
Windows device aliases. Existing reparse points are refused. This is a local
development adapter: the process must exclusively control its root and its
ancestors. It is not a sandbox against a malicious concurrent filesystem owner
swapping directory links.

Blob upload conditions are `If-None-Match: *`, with the supplied content type.
Only 404 `BlobNotFound` is absence; missing container, access denial, credential
failure and network/service failure are not empty bytes. Duplicate paths expose
`artifact_exists`/409; unsafe paths expose `invalid_artifact_path`/422; dependency
failures expose `artifact_store_unavailable`/503. Cancellation remains
`OperationCanceledException`. Error strings contain neither upstream bodies nor
credential/file-system diagnostics.

The W2 package-create handler must map the duplicate conflict to the JSON
`detail` family (F-5); it must not overwrite the previous blob. E-6 permits
portable container encodings, never changed stored bytes or member hashes.
Tests use binary/empty data, concurrent publication, unsafe path matrices,
cancellation, SDK fake HTTP requests and injected credentials.

### Host state and reset

Every scenario should use fresh dependency-injection scope/instances and a new
local artifact root or isolated fake Blob transport. Immutable byte stores have
no destructive reset operation: metadata/reset ownership belongs to the host,
which must not erase production artifacts. Source, token, budget, limiter and
provider reset contracts are documented with their final implementations below.

### API authentication and authorization

`IApiTokenValidator` separates RS256 signature/lifetime verification from
delegated/app-only extraction. Required claims are `exp`, `iat`, `iss`, `aud`;
the issuer is the configured tenant's v2 issuer, and both the bare application
audience and its `api://` form are supported. The lifetime skew is 60 seconds.
Gateway audiences, roles/scopes and `X-Acting-*` headers are not API alternatives.
`oid`, `roles` and `scp` retain their API meanings.

`IApiTrustService` exposes the host sequence: public bypass, bearer validation,
acting-user binding, agent-forbidden metadata, then normalized client selection.
For an agent, `X-TCC-Acting-User` is parsed before the forbidden-write decision:
the recorded missing-header case is 400, the validated forbidden call is 403
(F-16). A delegated caller's acting header is ignored and cannot promote identity.
JWT/credential/JWKS errors are typed, sanitized failures rather than anonymous
success. Host response shaping must retain the JSON `detail` family and add
`WWW-Authenticate: Bearer` for authentication refusals.
Catch abstract `ApiAuthException` for its `StatusCode`, `Code` and `Challenge`;
sealed `AuthRefusalException` represents request refusals and
`AuthDependencyException` represents identity-provider failures. No upstream
body or credential diagnostics become the exception detail.

JWKS retrieval is injectable, bounded to five seconds, with bounded documents
and key counts, coalesced refresh, one-hour cache, five-second refresh cooldown
and reset. Configured Graph retrieval has bounded replies, classified failures,
cancellation and a one-minute refresh cooldown. No live retrieval was tested.
Host composition supplies clocks, HTTP transports and configured authority;
tests use ephemeral RSA keys.

Writer sources log classifications, fail closed on unreadable/nonboolean answers,
permit a successful independent source to grant, and never cache failed group
checks. The agent caller's principal selects client visibility; the bound person
attributes writes. Batch existence lookup precedes visibility, counters and
paging. Artifact authorization stays with the Persistence-backed auditing
handler. These ports provide no employer-binding guarantee.

W2 policy handoff: F-14 cases `reader.assess`, `reader.run`, `reader.rules-verify`
and `reader.batch-dry-run` require explicit policy review; consistent writer
services must not silently change their recorded valid-request outcomes.
F-15 `agent.read-draft-list` is not solved by inventing a query author or
impersonating the acting user. Person-only audit-read metadata is separate.

The initial direct auth matrix passed 123 cases and 49 CPython-backed oracle
cases passed in 18.61 seconds. Final registration/security cases require the
new MIT concrete DI 10.0.0 test pin. **Final auth matrix: 147 passed**, zero
failures/skips, three seconds; build zero warnings/errors and owned format clean.

### Per-caller limiter

The key is `(kind, principal.Oid)`, never an acting-user substitution.
Continuous monotonic refill and a single synchronized bucket update prevent
concurrent overspending. Retry seconds are `floor((1 - tokens) / rate) + 1`.
Only signed-in callers spend tokens; the host adds `Retry-After` and maps the
code/reason/remedy into structured 429 `detail`.

Only fully replenished buckets may be evicted. When bounded capacity has no
safe candidate, a new key is refused rather than displacing a depleted key and
granting fresh allowance. Instance reset is exposed for hermetic scenarios;
limits remain per-process and settings are validated at startup.
Tests cover depletion, refill edges, concurrent calls, rollback, churn and reset.
Python's unsafe bounded-LRU counterexample granted four requests for three
rotating keys with capacity two; this adapter refuses overspending.
The API's four current rate-limited operations already refuse agents before the
limiter, so the task-required original-caller key changes no reachable current
agent authorization result. G1's gateway six-per-minute policy is not adopted.

### AI contracts, wire, safety and resilience

Application `Ports/Ai` defines roles/readiness, injected provider specifications,
narration/chat requests, text/tool/usage/end events, ordered hops, safe errors,
token acquisition, guards, budget reservations and telemetry.
`AddTaxCreditAi` accepts definitions, provider factories, HTTP transports,
telemetry, clocks and configuration. It does not register prompt agents,
publishing, tools or routes.

Injection and egress guards execute before providers and token acquisition.
Identifier refusal applies to every policy/provider, while trail hashes are not
treated as identifiers. External blocking and aggregate-only policy are distinct.
Reader-authored fences/`JSON:` cannot replace separately supplied trusted facts.
The Unicode 15 casefold/compatibility resource is CPython-generated: 6,340
mappings, 30,137 compressed bytes. All 47 injection corpus rows were checked
against the explicitly configured CPython 3.12 oracle.

Fake-wire coverage includes OpenAI v1 model-in-body and Azure deployment-in-URL
dialects; streaming and non-streaming text, usage and fragmented tool events;
API-key/OAuth/Entra auth; auth-header precedence; Retry-After seconds/dates;
audience/expiry checks; coalesced token refresh; cancelled refresh waiters;
generation-safe invalidation and HTTP 401 invalidation. Bare chat models may
return tool events, but agent runtimes discard them and nothing executes tools.
Injected Foundry seams classify both synchronous and streamed failures.
Errors/reprs exclude prompts, upstream bodies, headers and raw inner exceptions.

Composition is observation, guards, bulkhead, breaker, retry, event-gap timeout,
per-attempt accounting, provider. Tests prove active total deadlines, first/later
event gaps, a single half-open probe, no health penalty for shedding, one breaker
failure per logical request, cancellation and abandoned-stream cleanup.
Neither retry nor provider switching occurs after text or caller-visible tool
output. No client/policy failure is retried.

UTC-day budgets reserve atomically before calls and settle each physical attempt
once using reported usage or explicit four-character estimates. Failed attempts,
retries, cancellation and abandonment are accounted for without duplicate
charges. Overall budget refusal propagates instead of trying another provider.
Budgets are per-process guardrails, not invoices; reported usage can exceed an
estimate.

Scripted degradation renders trusted facts unchanged, emits one unavailability
notice per request, preserves caller fallback, labels interrupted output and
explicitly identifies truncation. These typed events are for W2 framing; no SSE
endpoint was added, and downstream numeric-guard integration remains later work.

Telemetry uses Activity/Meter name **`TaxCredit.Ai`**. Exporters are skeleton-owned.
Only registered provider/role/model labels, outcome, hops, timing, usage, degraded
and cancel fields are recorded; no prompt text or principal identifiers.
Use `ITokenBudget.Reset()`, `CircuitBreaker.Reset()`, `ModelRouter.Reset()`,
token-cache `Invalidate()` and a fresh request-scoped `DegradationState`.
Reset/dispose only after streams close; the host owns clients and credentials.
Opaque OAuth audience binding relies on the trusted acquisition source, and
injected transports must honor cancellation.

**Verified S5:** 128 fast tests, zero failures/skips; the complete AI test project
including artifacts passes 167 cases. Owned build is warning-free and format
clean. Live model behavior, SDK publishing, real endpoint framing and exporter
transport were not tested.

## Package ownership and oracle setup

Package versions added only inside the `sources_auth_ai` marked section:
Microsoft.Data.SqlClient 7.1.2, Azure.Identity 1.17.1 and Azure.Storage.Blobs
12.26.0, plus Microsoft.Extensions.DependencyInjection 10.0.0 for actual
registration tests. Their installed manifests and upstream licences identify MIT.
Existing JsonSchema.Net 8.0.5 and shared DI 10.0.0 pins remain unchanged.

The initial newest-SDK attempt failed NU1605 because its Azure.Core graph
requires DI 10.0.9. Compatible stable SDK versions were selected instead of
changing another session's package declaration or suppressing the downgrade.
Integration should reconcile driver/credential pins with Persistence and may
upgrade the entire shared dependency graph together.

The missing `TCC_PYTHON` gate failure is resolved at the test process source.
CPython 3.12.13 was checked; imports resolve to this worktree's `backend`.
The parity resolver deliberately has no process-global default, so the conductor
must set the variable in its gate process too:

```powershell
$env:TCC_PYTHON = 'C:\Projects\py312-oracle\.venv\Scripts\python.exe'
Set-Location C:\Projects\GitHub\tcc-dotnet-w1-sources\dotnet
dotnet --version # 10.0.404; SDK discovery depends on this working directory
dotnet build -warnaserror
dotnet format --verify-no-changes
dotnet test --filter 'Category!=heavy'
```

No user/machine environment variable is changed on this shared machine.

The previously failing oracle-dependent fuzz groups now pass with this setup:
8 passed, 0 failed/skipped, 14 minutes 12 seconds on the shared machine. No
comparison, fuzz count or threshold was weakened. These legacy tests are outside
the owned paths and retain their existing categories.

## Final mechanical gates

Run serially from `dotnet` under SDK **10.0.404**, with the explicit
CPython **3.12.13** oracle above:

| Check | Final result |
|---|---|
| Whole solution `dotnet build -warnaserror` | Passed; zero warnings/errors, 24.22 seconds |
| Whole solution `dotnet format --verify-no-changes` | Passed |
| Whole solution `dotnet test --filter 'Category!=heavy'` | Passed; 605 tests, zero failures/skips |
| Domain / Sources / Auth / AI / Parity / Architecture | 18 / 108 / 147 / 167 / 152 / 13 passed |
| Additional source volume comparison | One heavy test passed; 197,094 P2 rows and selected method results |
| Halt/report/status/improvements | No halt file; report nonempty; both JSON records parse |

The final parity project took 12 minutes 29 seconds. Existing Persistence/API
test projects contain no matching non-heavy tests; no coverage is inferred
from those empty selections. No HTTP replay group is claimed: endpoint/host
composition remains with later waves, while adapter matrices exercise their
recorded contracts.

All changes are committed locally on `dotnet/w1-sources_auth_ai`; nothing was
pushed. The finish record's `head` identifies the preceding verified
implementation/report commit; the status-only commit is its child. Ownership
was checked against the allowed adapter/port/package paths and the specifically
authorized session documents.

**Remaining scope limit:** S2 is partial solely at the existing strict
leap-shift Domain seam described above. Its owner decision and the unchanged
figure-affecting Python inconsistencies are explicit `needs_human` entries,
not claims of integration or live-service certification.
