# Contract: recorded behaviour of the Python API

The Python implementation is the **oracle** for the .NET 10 port. This folder records what it does as data and ships a tool that checks any server against that record. Nothing here changes the product.

Layout (filled in stage by stage; see `docs/capture-log.md` for status):

| Path | What |
|---|---|
| `inventory/` | C1: generated surface inventory (routes, OpenAPI, channel tools, orchestrator, agents, env, data) |
| `harness/` | C2: hermetic in-process app factory, clock/id freezing, socket guard |
| `seed/` | C2: the starting state of each profile, exported as data |
| `scenarios/` | C3: scenarios (data) |
| `recordings/` | C3-C5: the recorded exchanges (JSON Lines) |
| `capture.py`, `normalise.py`, `replay.py` | C3 / C6 tools |
| `docs/` | log, normalisation proofs, auth contract, orchestrator spec |

## Running anything

```pwsh
.\contract\py.ps1 -m contract.inventory.generate            # write the inventory
.\contract\py.ps1 -m contract.inventory.generate --check    # fail if the product moved
```

`py.ps1` uses the main checkout's virtualenv with the working directory set to this worktree's `backend/`. Do not push this branch.
