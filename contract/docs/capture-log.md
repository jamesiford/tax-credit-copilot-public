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

### Decisions added during the run

- D4. Each scenario runs in a fresh process. A P2 build takes ~80 s (four synthetic clients through the engine), so scenarios are few and coherent and `capture` runs them 4-wide.
- D5. Harness-only seams (never edits to product files): `harness/gold.py` (SQLite `SELECT DISTINCT TOP n`), `harness/freeze.py` (clock, ids, secrets, git commit, rule mtimes, zip member times, background recalculation thread, sqlite date adapters), `harness/control.py` (`/__contract__/drain|env|mint`, one request at a time, deferred work finished before the next request), `harness/auth.py` (Entra with a run-time RSA key), `harness/gateway.py` (profile G1/G1L).
- D6. Scenario variables and a `{{token.<name>}}` placeholder keep minted tokens out of every file.
- D7. Over a real socket two header values cannot be sent by an HTTP client (`Bearer ` with a trailing space, a blank acting-user header); the cases were changed/dropped rather than faked.

### Gates (final)

- **G1** inventory regenerates byte-identically; `--check` exits 1 when the product or the file differs: PASS (8 files).
- **G2** two builds of each profile give identical seed manifests (P1 18,111 rows, P2 390,660); API figures equal seed rows: PASS.
- **G3** every route has at least one recording (93/93; 82 with a success, 11 explained in `COVERAGE.md`); `capture --check` identical twice in a row, three-wide, all 12 recordings: PASS. Orchestrator recording `--check` identical.
- **G4** strict replay against a real `uvicorn` in a separate process: 1,769/1,769 identical; in-process: identical. Mutation self-test 20/20.
- Baseline tests (preflight) were not re-run at the end because no product file changed (`git status` outside `contract/` is empty).

### Process findings worth keeping

- The first `--check` runs found real sources of volatility; each was frozen at its source (see `normalisation.md`). The most instructive: a background recalculation thread whose id draws raced the next request only under CPU load.
- `magnitude=999999999` on `/api/simulate/portfolio` hangs the recorder (F-1); the case is excluded and logged.

### Revision 2: Python 3.12 oracle

- Recordings re-made on CPython 3.12.13 (zlib 1.3.2); 8 records changed, all container size/hash fields (normalisation rule 2). Seeds regenerated: decompressed content identical, 13 .gz files differ in bytes only; manifests gained `content_sha256`.
- **G3** `capture --check` identical twice in a row on 3.12.13, and once on 3.14.2 (cross-check). **G4** strict replay 1,769/1,769 against a real uvicorn (3.12.13), in-process 1,769/1,769, cross-check on 3.14.2 1,769/1,769. Mutation self-test 72/72 (20 recording mutations + 52 container mutations) on both interpreters.
- Inventory `--check` passes on 3.12 and 3.14 from the one committed file.
