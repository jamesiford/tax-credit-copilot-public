# Changelog

All notable changes to the contract artefacts. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- C1 surface inventory generator and its outputs (`contract/inventory/`, `contract/CONTRACT-INVENTORY.md`).
- Hermetic process configuration (`contract/harness/hermetic.py`), clock and id freezing (`contract/harness/freeze.py`).
- C2-C6: scenarios (12), recorder (`capture.py`), 12 recordings, seed export, replay tool (`replay.py`, `compare.py`), mutation self-test, coverage matrix.
- C4: sign-in matrix and `docs/AUTH-CONTRACT.md`.
- C5: channel gateway (REST + MCP), orchestrator without a model, agents publish request, `docs/ORCHESTRATOR-SPEC.md`.
- C7: `CONTRACT-REPORT.md`, `FINDINGS.md`, `docs/normalisation.md`.
