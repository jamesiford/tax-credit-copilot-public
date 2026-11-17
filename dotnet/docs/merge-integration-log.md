# W4 merge-integration log

## Stage 1: merging and resolving

- Started on clean branch `dotnet/integration` at `a44a07e`.
- Ran `git merge --no-ff dotnet/w4-integration`; the only conflict was the
  rename/rename of `dotnet/docs/HALT-integrate-W3.md`.
- Both renamed files have the identical Git blob
  `33368dbf1181c263624581e087dfc91acf360060`. Preserve both
  `dotnet/docs/INHERITED-W3-RELEASE-BLOCKERS.md` and
  `dotnet/docs/waves/W3-policy-stop.md`, because the deployment and integration
  reports respectively link to them. Remove the obsolete source path from the
  index. No content or historical owner decision is discarded.
- Retain all automatically merged W4 files, the integration-owned ScriptDom
  package entry and the Shadow project reference. No product behavior,
  comparison, threshold or improvement registration changes.
- The repository-root SDK is 11.0.100; run .NET gates from `dotnet` so its
  existing SDK pin selects .NET 10 instead.

## Gate results

- `dotnet --version` from `dotnet`: 10.0.404.
- `dotnet build -warnaserror`: passed, zero warnings and zero errors.
- `dotnet format TaxCredit.slnx --verify-no-changes --no-restore`: passed.
- `dotnet test TaxCredit.slnx --no-build --no-restore --filter
  'Category!=heavy' --verbosity quiet`: 1,559 passed, zero failed, zero skipped
  across eleven test assemblies.
- The required unfiltered Git marker scan reported a binary match in the
  pre-existing compressed golden `parity/goldens/credit_math.jsonl.gz`.
  Its working-file hash and both parent blobs are identical:
  `82849d5c449dd72feaab3620fa9725853a6854f0`. This is not a text conflict;
  `git grep -I -n '<<<<<<<\|>>>>>>>'` found no tracked text markers.
- `git ls-files -u` and `git diff --name-only --diff-filter=U`: empty.
- `git diff --cached --check`: passed. All staged changes are under `dotnet`.
- Pending: merge commit, source-branch ancestry and clean-tree confirmation.
