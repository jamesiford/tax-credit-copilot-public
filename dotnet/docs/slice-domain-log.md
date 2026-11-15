# Domain slice log

Running log of decisions, findings and gates for branch `dotnet/domain` (from `dotnet/spike`).

## Preflight (2026-11-14)

- Worktree `C:\Projects\GitHub\tcc-dotnet-domain`, branch `dotnet/domain` from `dotnet/spike` (ebcdd04). Nothing pushed.
- Oracle: `C:\Projects\py312-oracle\.venv\Scripts\python.exe`, CPython 3.12.13. From `<worktree>\backend`, `import domain` resolves to `<worktree>\backend\domain\__init__.py`.
- Baseline: `dotnet build -warnaserror` clean; `dotnet format --verify-no-changes` exit 0; `dotnet test`: Domain 18, Architecture 13, Parity 63, all passed.

## DS1 inventory (gate: met)

- `parity/inventory.py` walks the AST import graph; `parity/port_map.py` renders `dotnet/docs/port-map.md` from a verdict table and the computed evidence. `--check` fails on an unclassified module under `domain/` or `tools/` or a stale file.
- Every module in `backend/domain` (22) and `backend/tools` (52 files incl. `code_standards/`) has a row with a reason; plus 19 `application` modules on the calculation path.
- Candidate list confirmed, with these changes against the brief:
  - `tools.portfolio` is **not** in scope for Domain: it reads Gold through `application.services` and `application.queries._client_run`; Application slice. `tools.discovery` depends on it, so `discovery` ports only after the Application port exists (or against an interface). Logged for DS5.
  - `tools.brief_format`, `page_brief`, `portfolio_brief` are agent-brief builders (pure, but belong to the agents slice).
  - `domain.ai`, `ai_errors`, `channel`, `channel_trust` out of scope (own slices).
  - `application.open_year` is pure and tiny; classified Domain candidate.
- Layering finding F-DS1-01: `tools.*` imports `config`, `data.*` (`data.designations`, `data.sites`) and `application.*` (portfolio only). Pure tools that reach for `data.*` or `config.get_settings` (`program_registry`) need their inputs injected in C#.
- Finding F-DS1-02: `tools.credit_math` and `tools.simulation` import `pydantic.Field` (request models). Only the computation ports.
- Python-test mapping in the map is by import regex; modules exercised only through other modules show `-`.
