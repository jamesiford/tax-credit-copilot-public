# ADR-013 — Program registry and pack validation

**Date** 2026-11-12 · **Status** Proposed (registry, schema, validator, scaffolding and the derived run state are implemented; the portal workflow follows) ·
**Relates to** [ADR-005](ADR-005-year-versioned-rules.md) (statute is versioned by tax year, authored in git).

## Context

Programs are registered by two hardcoded dictionaries in `tools/credit_math.py` (`STATE_TO_PACK`, `PROGRAM_CODE_TO_PACK`);
federal programs are found by a separate path; pack shape is checked only by tests; the Rules page is read-only. Adding a
program means editing code, and nothing says what a valid pack is. At the same time, ADR-005 forbids statute reaching the
engine from anywhere but an authored, version-controlled year pack.

## Decision

1. **Registry as data**: `backend/rules/programs.json` holds one entry per program: code, name, jurisdiction (`level`,
   `code`), pack file, status (`draft | described | calculable | retired`), supported models, aliases. Several programs may
   share a state; federal programs are entries without a state key. `STATE_TO_PACK` and `PROGRAM_CODE_TO_PACK` remain
   importable and are derived from the registry with identical observable contents.
2. **`calculable` requires** at least one authored year pack (or a flat pack the engine supports today) that passes
   validation. A program without that is `described`, as today.
3. **JSON Schema** (`backend/rules/schema/rule-pack.schema.json`, with `schema_version`) for packs and year packs. A pack
   naming an unsupported model is rejected, not ignored. A year pack must carry its own `tax_year`, must not inherit from
   another year (no `extends`/base), and keeps a `_prototype_verification` flag until a human removes it.
4. **Tools**: a validator CLI (schema, cross-checks against the registry, no-inheritance) and a scaffolding CLI that writes a
   *draft* pack and registry patch.
5. **Portal workflow, export only.** The portal lists the catalog, keeps drafts in `tcc_ops`, validates, previews a draft
   calculation **in memory with no writes**, and exports a bundle (pack files, registry patch, checklist) for a human to
   review and commit. **A draft never has runtime authority**: nothing reads statute from a database (ADR-005).
6. **Not verified.** Every new or draft pack is labelled "not verified" in the UI and carries the prototype flag; the product
   never asserts that a program's values are legally correct.
7. **Defaults.** The `state="GA"` default on run requests is derived from data (registry and the client's footprint) with a
   deprecated fallback and a warning.

## Consequences

A program using supported credit and headcount models is added by data. A program needing a new calculation model still
needs engine work; the seam is `tools/credit_math.py` and `domain/calculation/`, and the validator names what is
unsupported. The rules-ingestion agent stays Georgia-only.

## Deliberately not done

No runtime activation of statute from a database or the portal; no inheritance of statute across years; no automatic
verification; no new calculation models; no extension of the ingestion agent.

## Implementation notes

- The registry file is `backend/rules/registry/programs.json`, not `backend/rules/programs.json`: packs are discovered with
  `rules/*.json`, so a manifest in that folder would be read as a pack. `RULES_DIR` and `PROGRAM_REGISTRY_FILE` move it.
- The stored lifecycle is `draft | described | retired`; `calculable` is derived from authored year packs and a typed one is refused.
- The state default on the run request, the run command and the base-year command is derived from the client's payroll and the
  registry; the old `"GA"` survives only as a deprecated fallback that warns. Read queries keep their defaults (follow-up).
- A year skeleton is written as `<year>.draft.json`, which the engine does not read, so a half-filled file can never make a
  program look calculable.
- **Several programs per state (F04c).** The program is the key. `Registry.for_state` / `programs_for_state` list a state's programs in
  manifest order (the first is its default and what `STATE_TO_PACK` shows); `program_for_code` looks one up. `resolve_statute` and
  `resolve_client_run` are program-first (`program_code` wins; a disagreeing state is `ProgramStateConflict`; a federal or unknown
  program is `ProgramNotRunnable`). A state with several calculable programs resolves to the first with a logged warning on the run
  path and asks (404 listing them, `require_program`) on a read. `tools/program_credit.py` holds the credit math keyed by program;
  the state-named functions are wrappers over the default program. `tools/pack_lookup.pack_file_for` finds any program's pack.
  Which rows a program prices is defined once (`program_rows`). Federal programs stay not runnable. Gold, manifests and claims were
  already program-keyed; the reads were not (`latest_run` returned the latest run of any program), so `program_code` now threads
  through the Gold read port. No migration. Limits: capability tool inputs other than `base_year_set` do not yet take a program,
  and the client-wide trend still reads the latest run (open-questions).
- See [ADDING-A-PROGRAM.md](ADDING-A-PROGRAM.md).
- **Portal drafts (F05).** Decision 5 is implemented as option A: drafts live in 	cc_ops.program_draft* (migration 0005), are validated in memory by the same validator, previewed on synthetic data with the engine's own functions and no writes, reviewed by a second person, and exported as a deterministic bundle for a human to commit. The registry still says nothing is calculable until the files are in git. The read capability program_catalog exposes the catalog (never a draft) to Teams and Cowork. See [PROGRAM-DRAFTS.md](PROGRAM-DRAFTS.md).
