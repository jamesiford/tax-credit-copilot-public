# Changelog

All notable changes to the contract artefacts. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- Python **3.12 is the oracle**, enforced in code (`contract/oracle.py`, `py.ps1`): `capture`, `replay`, `selftest`, `seed_export`, `orchestrator_capture` and the harness refuse other interpreters unless `--allow-other-python`, which is stamped in the output. Recordings and seeds re-made on 3.12.13; cross-check on 3.14.2 passes (1,769 / 1,769 strict; `capture --check` 12/12).
- Normalisation rule 2 (`normalise.py`): size and SHA-256 of a zip/xlsx container at 7 listed routes, replaced at record and replay time after a shape check (and, for headers, a check against the body). 8 recorded exchanges changed, all container fields.
- `compare.py` compares zip members one by one; the container bytes are never compared.
- Inventory types are canonical and interpreter-independent (`inventory/typenames.py`); `--check` passes on 3.12 and 3.14.
- Seed manifests carry `content_sha256` (decompressed) beside `sha256` (gzip bytes, zlib-dependent).
- Replay client opens a connection per request (uvicorn closes the socket after a 500 and raced pooled connections).
- Mutation self-test: 72 mutations (20 of recordings + 52 of the server answer); `docs/mutation-selftest.json` has `interpreter` and `results`.
- `FINDINGS.md`: E-1 (had a wrong claim about 3.14 and sqlite) and E-6 rewritten with measured evidence; E-8..E-10 added. `CONTRACT-REPORT.md` section 3, tier D and open question 6 updated.

### Added
- C1 surface inventory generator and its outputs (`contract/inventory/`, `contract/CONTRACT-INVENTORY.md`).
- Hermetic process configuration (`contract/harness/hermetic.py`), clock and id freezing (`contract/harness/freeze.py`).
- C2-C6: scenarios (12), recorder (`capture.py`), 12 recordings, seed export, replay tool (`replay.py`, `compare.py`), mutation self-test, coverage matrix.
- C4: sign-in matrix and `docs/AUTH-CONTRACT.md`.
- C5: channel gateway (REST + MCP), orchestrator without a model, agents publish request, `docs/ORCHESTRATOR-SPEC.md`.
- C7: `CONTRACT-REPORT.md`, `FINDINGS.md`, `docs/normalisation.md`.
