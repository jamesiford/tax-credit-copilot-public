# Contract capture log

Running log of decisions, findings and gate results. Newest at the bottom of each section.

## Preflight

- Worktree: `C:\Projects\GitHub\tcc-contract-capture`, branch `contract/capture`, created from `main` (f9da416).
- Interpreter: the main checkout's `.venv\Scripts\python.exe`, working directory `<worktree>\backend`, `PYTHONUTF8=1`.
- **Checkout proof:** `python -c "import domain, sys; print(domain.__file__)"` printed
  `C:\Projects\GitHub\tcc-contract-capture\backend\domain\__init__.py` (inside the worktree). The harness re-asserts this on every
  start (`contract/harness/hermetic.py: assert_checkout`) and halts (hard stop 2) otherwise.
- **Baseline** (`tests/test_architecture.py`, `tests/test_workspace_api.py`, `tests/test_portal_without_reference.py`,
  `tests/test_run_batches_end_to_end.py`): **67 passed, 9 skipped** in 43 s. The 9 skips are all in `test_workspace_api.py`:
  `stakeholder-docs/` was removed from the repository (B05), so the sealed-workspace benchmark cannot stage its inputs.
- Existing files are never edited; `git status` in the worktree shows only `contract/`.

## Decisions

- D1. The brief says "88 routes"; the live app has 97 Starlette routes: 93 API operations (91 distinct paths), of which **18 declare a
  real pydantic `response_model`** and 75 are untyped. FastAPI infers `response_model=dict` from `-> dict`; that constrains nothing,
  so it is counted as untyped (`contract/inventory/generate.py: _is_model`). The remaining 4 routes are FastAPI's own
  (`/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`). The custom-instruction file says 72 routes; `tests/route_inventory.json` is the pinned list.
- D2. The orchestrator is inventoried **without** running `scripts/vendor-orchestrator.py`: it writes the gitignored
  `channel_orchestrator/app/vendor/` (a generated tree outside `contract/`). The backend's own packages of the same names win in
  the test run anyway (`app/__init__.py` appends the vendored path).
- D3. Time is frozen to a constant instant rather than a ticking clock: a tick makes a response depend on how many times the product
  asked, and background tasks would perturb it. `time.perf_counter` is replaced by a 1 ms-per-call counter so measured durations
  are a function of call count.

## Gates

### G1 (inventory regenerates byte-identically; `--check` fails when the product moved)

- First run exposed a real defect in the generator: `response_class` printed a `DefaultPlaceholder` object address, so two runs
  differed. Fixed (unwrap `.value`), then two consecutive runs gave identical SHA-256 for all 7 JSON files and the Markdown.
- `--check` negative test: appending a byte to `inventory/data.json` made `--check` exit 1 naming the file.
