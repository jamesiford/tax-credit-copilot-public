# W4 shadow observer

**No traffic switch or live certification.** Run from `dotnet` with SDK 10.0.404 and CPython 3.12. The configured oracle is `C:\Projects\py312-oracle\.venv\Scripts\python.exe`. Product code, recordings, normalisations and producer registers are immutable inputs.

## Offline boundary

```powershell
dotnet build TaxCredit.slnx -c Release
dotnet build tests\TaxCredit.Shadow.Tests\TaxCredit.Shadow.Tests.csproj -c Release
dotnet run --no-build -c Release --project spikes\shadow\TaxCredit.Shadow.csproj -- --self-test
& C:\Projects\py312-oracle\.venv\Scripts\python.exe -B spikes\shadow\run_tests.py
dotnet test tests\TaxCredit.Shadow.Tests\TaxCredit.Shadow.Tests.csproj -c Release
```

The executable compile-links the original platform guard, exercises its 20 forbidden/11 allowed fixtures, validates three closed templates through a stricter SELECT-only overlay and runs three synthetic ownership/recovery cases before admission. It cannot execute SQL. The old platform runner/cleanup is never invoked. Synthetic ownership tests preserve pre-existing/replaced objects, clean acknowledged invocation objects in `finally`, retain failed drops and reconstruct an invocation ledger. Scratch is unused live; this is not native metadata-cleanup proof.

Build the owned test project explicitly: the shadow executable is an out-of-solution project reference, and a solution-only build left its previous binary unchanged in this environment. Admission checks the exact new self-test schema and refuses a stale binary.

The comparison bridge reads at most 4 MiB from stdin and returns a fixed payload-free schema. It uses public `contract.compare`, semantic `split` and `normalise.apply` in memory. Whole-record/content equality booleans are separate from semantic equality. No expected/actual, scalar hashes, raw values, dynamic field names, filenames, URLs or exception text are emitted. Changed money/scale/type/status, null/presence, array/event/member order, member content and header/body integrity remain failures. Only existing declared container normalisations apply; trails, canonical and per-file hashes are not exempt.

## Synthetic evidence

```powershell
& C:\Projects\py312-oracle\.venv\Scripts\python.exe -B spikes\shadow\hermetic.py --baseline
& C:\Projects\py312-oracle\.venv\Scripts\python.exe -B spikes\shadow\policy.py
& C:\Projects\py312-oracle\.venv\Scripts\python.exe -B spikes\shadow\paired_performance.py
& C:\Projects\py312-oracle\.venv\Scripts\python.exe -B spikes\shadow\cross_surface.py
& C:\Projects\py312-oracle\.venv\Scripts\python.exe -B spikes\shadow\deviations.py
& C:\Projects\py312-oracle\.venv\Scripts\python.exe -B spikes\shadow\evidence.py --gates
& C:\Projects\py312-oracle\.venv\Scripts\python.exe -B spikes\shadow\evidence.py --capture-live
& C:\Projects\py312-oracle\.venv\Scripts\python.exe -B spikes\shadow\evidence.py --write
```

Use fresh `dotnet\artifacts\w4-integration\baseline`, `paired` and `cross-surface` directories. Existing output causes refusal; retain/move a specific old attempt within the worktree before a new invocation. Logs/raw replay are allowed **only** for these isolated synthetic hosts. Each host gets a distinct SQLite/local-artifact root and local temp directory; inherited live settings are scrubbed. The public oracle harness disables `.env`, blocks outbound sockets and builds the requested seed profile. It has no reset control: a fresh P1 process is already the correct world. Native hosts use the public scenario-specific reset/auth/writer/rate setup, never an extra unqualified reset after it.

Release DLLs are launched directly from `dotnet`, avoiding root SDK selection inside the older replay launcher. No independent Worker is started during reset. Gateway application services compose in-process; a separate API listener is not its dependency. Synthetic fixture `GIT_COMMIT` stays under the public harness/host fixture rules; actual product/binary revisions are recorded separately rather than injected into replay payloads.

Historical heavy executable tests explicitly launch **Debug** API/Worker DLLs even when their test assembly is Release. Build these prerequisites before that gate:

```powershell
dotnet build src\TaxCredit.Api\TaxCredit.Api.csproj -c Debug
dotnet build src\TaxCredit.Worker\TaxCredit.Worker.csproj -c Debug
dotnet test TaxCredit.slnx -c Release --no-build --filter 'Category!=heavy' -m:1
dotnet test TaxCredit.slnx -c Release --no-build --filter 'Category=heavy' -m:1
dotnet format TaxCredit.slnx --verify-no-changes --no-restore
```

Run paired performance with no other owned tests/builds/replays active. Six alternating pairs per route, concurrency one: first post-readiness/setup read plus five warm reads, pooled loopback HTTP. Timing includes send/body parsing, excludes setup/comparison; no supported tails, live SQL split, true machine-cold state, production write baseline or SLO is claimed. Failed observations remain counted. Canonical cross-surface checks compare complete `facts`, not incompatible transport envelopes; all mandatory gateway audit remains in isolated state.

`policy.py` is a current-policy projection over unchanged raw synthetic reports, **not an external conductor run**. Status and missing/value failures are not free error text. Numeric exceptions require exact registered F-18 operational leaves. `g1_` is always standalone gateway; controls, sealed and unassigned cases retain separate denominators. Current sub-40 waiver exemption is explicit. `deviations.py` inventories every historical register blob reachable through register history, deduplicating identical entries without losing source files/IDs and retaining withdrawn/narrowed scopes.

## Explicitly admitted live mode

Only the following command is accepted; no endpoint/token/account arguments:

```powershell
& C:\Projects\py312-oracle\.venv\Scripts\python.exe -B spikes\shadow\observe.py --live
```

Supply these **runtime-only** inputs through an approved operator mechanism, never command-line literals, `.env` dumps or committed files:

| Input | Meaning |
|---|---|
| `SPIKE_SHADOW_APPROVED=yes` | Current session approval; does not itself admit any request |
| `SHADOW_CAPACITY_CHECK` | Current conductor read-only admission script path |
| `SHADOW_PYTHON_ORIGIN`, `SHADOW_DOTNET_ORIGIN` | Reviewed existing HTTPS origins; root only, no embedded credentials/query |
| `SHADOW_PYTHON_BEARER`, `SHADOW_DOTNET_BEARER` | Same permitted acting person/rights, host-valid audiences |
| `SHADOW_SOURCE_ODBC`, `SHADOW_SOURCE_TOKEN` | Read-only principal and runtime access token; driver 18, encrypted, certificate validation, read-only intent; no UID/PWD/auth/trace flags |
| `SHADOW_ACCOUNT`, `SHADOW_YEAR` | Approved selection; values never enter evidence |
| `SHADOW_TRUSTED_INGRESS`, `SHADOW_EMPLOYER_BINDING` | `reviewed` only after genuine authenticated-ingress/employer-binding review |
| `SHADOW_MATCHED_CALLER_RIGHTS`, `SHADOW_MATCHED_SOURCE_AND_GOLD` | `reviewed` only after paired rights/source/destination review |

These attestations are prerequisites, **not authentication or a substitute for proof**. Current conductor output is captured in memory and classified. The inherited guard and correct-checkout oracle run before its SQL check. Effective database/schema/table write rights are then refused before a fingerprint/HTTP request. Tracing is disabled on the client connection. No connection string, token, endpoint or native error is rendered.

The catalogue admits only settled public health, bounded Gold eligibility (GA_JTC, 25 rows, first page, fixed filters) and draft listing (25 rows, writer entitlement preserved). Each response is JSON-only and uncompressed, at most 1 MiB, 64/32-KiB headers (including duplicates), depth 30, total deadline 15 seconds, concurrency one; redirects/proxies are disabled. Compressed responses are refused before decompression/body consumption. Pair order is Python/.NET then .NET/Python, two pairs per group, no retry. Program/method and page are fixed; eligibility returns both stored methods. Source count/max is observed before/after; unavailable/changed markers, non-success responses and repeat drift are inconclusive. Equal markers cannot detect all edits or SQL synchronization lag.

Gateway tools, narration, AI, sealed workspace, rule claim-scans, mutations and ticket/artifact access are excluded live, including apparently read-only tool calls with mandatory audit. A missing approval/capacity/credential/endpoint/proof returns explicit per-group unmeasured counts. Never provision, activate, create scratch, grant access, invoke live model/Graph diagnostics or write Gold/ops/source/Blob to complete a sample. Terminal diagnostics contain only safe categories, route/path templates, ordinals, equality, counts and timings. There is no live raw-report writer or payload temporary file.

See [FINAL-REPORT.md](../../docs/FINAL-REPORT.md) and [CUTOVER-RUNBOOK.md](../../docs/CUTOVER-RUNBOOK.md) for obligations and the independent writer/rollback procedure.
