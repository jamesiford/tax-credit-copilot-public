# sources_auth_ai session log

## Resumed preflight

- The conductor requested removal of the ownership-conflict halt and creation
  of the required report/status. This is treated as specific authorization for
  this session's required documentation paths, not for other product paths.
- Branch remains `dotnet/w1-sources_auth_ai`; no push, remote change, or live
  Fabric, Entra, Foundry, or Blob experiment is authorized or performed.
- CPython oracle verified as 3.12.13. An explicitly configured import resolves
  `application.source_ports` to this worktree's `backend`.
- Gate failure was environmental: `TCC_PYTHON` was unset. Every parity command
  in this run sets it to the designated CPython 3.12 executable.
- Read certified domain report, port map, platform risks, authentication
  contract, normalisation, contract report/findings, and DS7/IN/CAP evidence.
  Domain remains unchanged; its certified parser and pipeline are reused.
- Source/fiscal, auth/limiter, and AI runtime implementation have independent
  owned scopes. Artifact bytes, shared package pins and final documentation/
  solution gates are coordinated separately. No routes or skeleton hooks added.

## Artifact design

- Byte stores remain separate from Persistence-owned metadata, prefixes,
  existence/visibility checks and download audit.
- Local publication uses a same-directory temporary file and a no-overwrite
  rename: readers never see a partly written final object. Existing targets
  become a typed conflict, not overwrites.
- Logical paths reject traversal, absolute/drive/UNC/backslash escape forms.
  Local storage is development-only and reports that it is not deployed
  durable storage.
- Blob operations use injected clients and create-only conditions. Only
  object-not-found becomes absence; authentication/network failures propagate
  as typed dependency errors without transport details.

## Package reconciliation

- Direct licences checked in the installed NuGet manifests and public upstream
  MIT licences: SqlClient 7.1.2, Azure.Identity 1.17.1 and Blob 12.26.0.
- Initial Blob 12.30.1 / Identity 1.21.0 restore failed NU1605: their Azure.Core
  graph requires DI abstractions 10.0.9, while the shared baseline pins 10.0.0.
  Selected stable compatible SDK versions rather than editing another session's
  shared package declaration or suppressing a downgrade. Final restore/build
  must verify this graph. Integration can upgrade the shared graph together.
- No new package with commercial licensing; JsonSchema.Net 8.0.5 left intact.

## Oracle failure reproduction and correction

- Re-ran the existing `FamilyFuzzTests` and `DifferentialFuzzTests` with
  `TCC_PYTHON` explicitly set, using existing binaries while adapter work
  continued independently.
- Result: 8 passed, 0 failed, 0 skipped; 14 minutes 12 seconds on this shared
  machine. No fuzz count, seed, comparison or threshold was reduced.
- The old oracle failure is resolved. The final solution gate will additionally
  build and run all non-heavy tests, including the new adapter tests.
- Existing unowned parity tests include long-running cases without a heavy
  trait. They remain unchanged; only new volume tests receive the required tag.

## Artifact source tracking

- Existing `artifacts/` ignore rules also match the required `Artifacts/`
  source folders on Windows. Force-staged only their nine explicitly selected
  source/project files (no binaries, payroll or generated outputs).
- Artifact slice commit: `1e43cdc`. The isolated artifact matrix is implemented;
  execution remains dependent on the concurrently authored AI project compiling.
  No test success is inferred from compilation blocked in another scope.

## Verified source and trust stages

- Source slice commit `4571401`: 72 fast tests initially, then 20 more actual
  certified-pipeline fiscal bridge tests. Final 92 fast + 1 heavy passed,
  93 total in 39 seconds. P2 comparison covers 197,094 rows and selected method
  outputs, with reversed-order checks; SQL aggregate semantics tested offline.
- A genuine existing Domain boundary remains: unrepresentable leap shifts return
  assumed calendar after the fiscal port has successfully read a valid base
  rule. The rich adapter refuses, but the Domain port lacks requested year/
  convention. Both explicit regression probes are documented, Domain is
  unchanged, and S2 is partial/needs_human rather than claiming equivalence.
  The certified behavior is preserved pending an owner-authorized seam change;
  no unauthorized Domain edit or duplicate fiscal resolver was attempted.
- Auth: 147 fast cases passed, production/test build zero warnings/errors, owned
  format verified. Independent writer grants/failures, source booleans, tenant/
  acting-header/role matrix and real registration are tested.
- Limiter key corrected to original caller oid. Fully replenished-only eviction
  fixes the unsafe-LRU churn allowance; active/depleted keys cannot be evicted.
  Relevant deliberate differences are in the improvements register.
- Artifacts: 39 fast cases passed. The SDK's redundant default-scope slash is
  canonicalized by an audience-bound credential wrapper; a storage challenge
  cannot acquire a token for another resource. The original exact audience
  assertion was not weakened. Atomic/path/error/cancel/credential cases pass.

## Integrated gate discipline

- Initial whole build passed with zero warnings/errors; whole format found one
  imports-order issue in an owned source test, subsequently corrected.
- Root-directory CLI discovery selected the installed SDK 11 toolchain while
  targeting net10.0. Final gates are run from `dotnet/`, so its `global.json`
  selects the verified SDK **10.0.404** and excludes preview SDKs.
- A concurrent rebuild collided with a running Windows testhost's loaded
  assemblies. Stopped only the named build/test sessions, not processes by
  name. The partial run is not claimed as a complete gate; final build then
  format then all-fast tests run serially with the pinned SDK.
- Final source clarification found malformed override dates under assume could
  still reach calendar fallback; corrective tests and lookup-boundary validation
  were requested before the final gate.
- The Python SQL/projector disagreement on zero worksite can affect program
  selection. SQL must preserve Python's COALESCE behavior pending owner review,
  while the projector retains Python's falsy-worksite fallback. It is not
  unilaterally reconciled as a numeric improvement.
- The source corrections are complete: malformed client/global override dates
  now fail at lookup parsing even under assume, source-wins precedence remains,
  and SQL COALESCE is restored. An explicit test records the zero-worksite
  projector/SQL discrepancy without repricing either path. SDK10 source tests:
  108 fast + 1 heavy, all passed in 1 minute 26 seconds; full format passed.
- The first pinned-SDK whole build exposed three SDK11-only collection-expression
  constructor initializers in AI. The correction uses ordinary C#14 constructors,
  not preview mode or a changed SDK; the complete gates must rerun afterward.
- The compatibility correction passed 128 owned AI runtime tests and full
  format under SDK10.0.404; committed as `bb911ad`. The final serial whole
  solution build passed with zero warnings/errors (30.40 seconds), and whole
  format passed. The complete non-heavy suite is running with explicit
  CPython3.12; its pending result is not yet claimed.
- That complete run passed Domain18, Sources108, Auth147, Parity152 and AI167,
  but failed one architecture rule: three public exception bases were neither
  sealed nor abstract. The rule is preserved. ModelException is sealed;
  source/auth bases become abstract with concrete sealed refusals. Exact
  exception assertions retain their checks and name the new concrete types.
  The full build/format/fast gate must rerun after this correction.
- Final serial SDK10 gate passed: whole build zero warnings/errors in
  24.22 seconds, whole format exit0, and all 605 non-heavy tests passed with
  no failures/skips. Counts: Domain18, Sources108, Auth147, AI167, Parity152,
  Architecture13. Parity took 12 minutes 29 seconds with CPython3.12.13.
  Existing Persistence/API projects have no matching fast tests, not proven
  adapter coverage. No fuzz count, threshold or architecture rule was weakened.
- Architecture correction committed as `f811424`. Source volume evidence
  remains 1 heavy test/197,094 rows. No HTTP replay, private certification or
  live transport/model claims are added. S2 remains the documented Domain
  strict-leap-shift boundary; no other implementation work remains.
- Final report/register and then status are committed locally. The status
  head points to the preceding verified implementation/report commit, avoiding
  an impossible self-reference. Final checks cover JSON, ownership, no halt,
  report presence, no remote tracking branch and clean committed tree.
