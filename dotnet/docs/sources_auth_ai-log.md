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
