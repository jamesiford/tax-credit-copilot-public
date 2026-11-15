# Sources, API trust, AI and artifact bytes

Session: `sources_auth_ai`; branch: `dotnet/w1-sources_auth_ai`.
This report is updated with final gate results before the finish commit.

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

## Package ownership and oracle setup

Package versions added only inside the `sources_auth_ai` marked section:
Microsoft.Data.SqlClient 7.1.2, Azure.Identity 1.17.1 and Azure.Storage.Blobs
12.26.0. Their installed manifests and upstream licences identify MIT.
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
dotnet build -warnaserror
dotnet format --verify-no-changes
dotnet test --filter 'Category!=heavy'
```

No user/machine environment variable is changed on this shared machine.

The previously failing oracle-dependent fuzz groups now pass with this setup:
8 passed, 0 failed/skipped, 14 minutes 12 seconds on the shared machine. No
comparison, fuzz count or threshold was weakened. These legacy tests are outside
the owned paths and retain their existing categories.
