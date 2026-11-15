# Contract: recorded behaviour of the Python API

The Python implementation is the **oracle** for the .NET 10 port. This folder records what it does as data (status codes, bodies, number formats, key order, error shapes, headers) and ships a tool that checks any server against that record. Nothing here changes the product; every file is new and under `contract/`.

Start with [`CONTRACT-REPORT.md`](CONTRACT-REPORT.md). The quirks are in [`FINDINGS.md`](FINDINGS.md).

| Path | What |
|---|---|
| `CONTRACT-REPORT.md` | what was captured, coverage, determinism, normalisations, quirk catalogue, what a default ASP.NET Core host gets wrong, the definition of parity |
| `FINDINGS.md` | things that look wrong, recorded unchanged |
| `COVERAGE.md` | route-by-case matrix (generated) |
| `CONTRACT-INVENTORY.md`, `inventory/` | C1: the surface, generated from the live objects (routes, OpenAPI, channel tools, orchestrator, agents, env vars, data) |
| `harness/` | C2/C4/C5: hermetic in-process app factory (profiles P1, P2, G1, G1L), clock/id/thread freezing, socket guard, sign-in, the gateway |
| `seed/` | C2: the starting state of each profile as JSON Lines (+ `seed/README.md`: tables, counts, load order) |
| `scenarios/` | C3-C5: the scenarios (data); `build.py`/`flows*.py` generate them from the route inventory |
| `recordings/` | the recorded exchanges (JSON Lines; number text and key order preserved), `orchestrator.json`, `agents.json` |
| `oracle.py` | the interpreter pin: 3.12, refused otherwise unless `--allow-other-python` |
| `capture.py`, `normalise.py`, `exchange.py`, `jsontext.py` | the recorder; `normalise.py` holds the two declared normalisations |
| `replay.py`, `compare.py`, `selftest.py` | C6: replay against any server, the comparison, the mutation self-test |
| `docs/` | `capture-log.md`, `normalisation.md`, `AUTH-CONTRACT.md`, `ORCHESTRATOR-SPEC.md`, `mutation-selftest.json` |

## Running anything

`py.ps1` runs the **oracle interpreter, Python 3.12** (the version the product runs on) with this worktree's `backend/` as the working directory. `CONTRACT_PYTHON` overrides the default `C:\Projects\py312-oracle\.venv\Scripts\python.exe`. The recorder, the replay tool, the self-test, the seed exporter and the harness refuse to run on any other minor version unless `--allow-other-python` is given (cross-check only; the output is stamped with the interpreter and zlib build). Use absolute paths for file arguments: the working directory is `backend/`.

### Create the oracle environment (once)

```pwsh
uv python install 3.12
uv venv C:\Projects\py312-oracle\.venv --python 3.12
uv pip install --python C:\Projects\py312-oracle\.venv\Scripts\python.exe -r <repo>\backend\requirements.txt
C:\Projects\py312-oracle\.venv\Scripts\python.exe --version     # Python 3.12.x
```

Another location works too: set `$env:CONTRACT_PYTHON` to that interpreter.

```pwsh
.\contract\py.ps1 -m contract.inventory.generate [--check]        # C1: write / verify the inventory
.\contract\py.ps1 -m contract.scenarios.build                     # regenerate scenarios/*.json from the inventory + flows
.\contract\py.ps1 -m contract.capture record [--scenario NAME]    # record (one fresh process per scenario)
.\contract\py.ps1 -m contract.capture --check [--jobs 4]          # fail if the Python code now answers differently
.\contract\py.ps1 -m contract.orchestrator_capture [--check]      # orchestrator (no model) + agents
.\contract\py.ps1 -m contract.seed_export --profile P1|P2         # the seed
.\contract\py.ps1 -m contract.coverage                            # COVERAGE.md
.\contract\py.ps1 -m contract.replay --spawn-python [--mode strict|semantic] [--profile P1] [--scenario NAME] --out <path-without-extension>
.\contract\py.ps1 -m contract.replay --in-process
.\contract\py.ps1 -m contract.replay --base-url http://localhost:5000 --reset-url http://localhost:5000/__contract__/reset   # the .NET host
.\contract\py.ps1 -m contract.selftest                            # the replay tool can fail: 72 mutations (20 of recordings, 52 of the server answer)
```

### Cross-check on another interpreter (not the oracle)

The recordings are 3.12-recorded; a different interpreter must reproduce them too. Everything below is stamped "NOT THE ORACLE" in its output and in the report JSON.

```pwsh
$env:CONTRACT_PYTHON = 'C:\Projects\GitHub\tax-credit-copilot-public\.venv\Scripts\python.exe'     # e.g. 3.14
.\contract\py.ps1 -m contract.inventory.generate --check                     # needs no flag: the inventory is interpreter-independent
.\contract\py.ps1 -m contract.capture --check --allow-other-python
.\contract\py.ps1 -m contract.replay --spawn-python --mode strict --allow-other-python --out C:\abs\path\crosscheck
.\contract\py.ps1 -m contract.selftest --allow-other-python                  # rewrites docs/mutation-selftest.json: git checkout it after a cross-check
```

The zip/xlsx container size and SHA-256 are **tier D** (`CONTRACT-REPORT.md` section 6, `docs/normalisation.md`): replaced by placeholders at record and replay time while every zip member is still compared. `CONTRACT_SERVER_LOG=<file>` makes `replay --spawn-python` keep the server's stderr.

### What a server under test must offer

Each scenario starts from its profile's seed (`seed/`). The replay tool drives these hooks under `/__contract__/` (see `harness/control.py`): `POST drain` (run every queued run-batch item and finish background recalculation), `POST env` (`{"set":{},"unset":[]}`, used by the "dependency unavailable" scenarios), `POST mint` (`{kind, oid, aud, roles, scp, exp_in, ...}` -> `{"token"}`: a token the server under test will accept, minted with its own test key; used by every authenticated scenario), and optionally `POST reset`. A server that has been given `--reset-url` is reset before each scenario; otherwise start a fresh one per scenario. Clock, ids, tokens and the secrets source must be deterministic as described in `docs/normalisation.md` for the recordings to be comparable byte for byte.

Never push this branch.
