# Walking skeleton: host, wire format, hooks, route registry, replay board

Session `skeleton` of wave `W1`. You run unattended: nobody will answer questions, so do not ask any.
Worktree: `C:\Projects\GitHub\tcc-dotnet-w1-skeleton` (branch `dotnet/w1-skeleton`, created from `dotnet/integration`).

---

## Pre-approved decisions (policy)

The owner decided these in advance. Follow them without asking. If something needs a decision that is not covered here, choose the reading closest to the documented design and the Python behaviour, record it in STATUS.json under `needs_human`, and continue.

- **parity**: Equivalent behaviour, not bug-for-bug. The target is the designed functionality and the contract a client depends on: the same routes and methods, authentication and authorisation, request and response fields and their types, the meaning of each status code, money as a decimal string with its scale, and the same calculated figures for the same valid input. Do not reproduce defects, accidents of Python, FastAPI or Pydantic, or artefacts of the recording harness (plain-text error bodies, key order, number lexemes such as 5.0 versus 5, byte-level headers and wording, HEAD and trailing-slash quirks, reflected CORS headers). Never write code whose only purpose is to reproduce a defect or a framework artefact. Where the Python behaviour is a bug or an accident, implement what the design, the ADRs, the docs or sound engineering intend, and record it in dotnet/docs/improvements/<session>.json (see improvements_register). If the same issue turns up naturally in the .NET code, that is acceptable; note it as a finding.
- **parity_tiers**: The replay runs in semantic mode (values equal; key order and number lexeme free). Tier A (certified-figure routes and every gateway tool result): the values must be equal, and a changed figure is never an improvement. Tier B (everything else with a JSON body): values equal. Tier C (error responses): keep the error shape family (a JSON body with `detail`, as the clients read it) and the right status; the message text is free. Tier D (zip and xlsx container bytes, timing, model output): out of scope. Anything else that differs from a recording for a good reason goes in the improvements register, not into reproduction code.
- **python_oddities**: Fix defects instead of reproducing them. F-2 to F-6 (plain-text 500s): return the JSON error family with the correct status, a 4xx where the cause is a client error, and never a stack trace. F-8 (duplicate claims): handle duplicates as the claims design intends (idempotent or a 409), and record which. F-14 to F-16 (inconsistent writer checks): apply the writer check consistently to every route that writes. F-1 (a GET that never returns because magnitude is unbounded): bound it and refuse out-of-range values with a 422. F-17 and every other entry in contract/FINDINGS.md: apply the same principle; read the finding first. Exception: if fixing something would change a calculated figure, a stored value or an authorisation outcome for a valid request, keep the Python result, and list it under needs_human as a fix candidate for the owner.
- **oracle**: CPython 3.12 is the only oracle interpreter. The recordings, goldens and seeds were made on it.
- **target**: net10.0 only. Do not use .NET 11 features or preview packages unless a decision below names them.
- **delta_read**: No Delta library at runtime. Payroll is read over the lakehouse SQL analytics endpoint behind an IPayrollSource port. For the data-version stand-in use the design recommended in dotnet/docs/PLATFORM-RISKS.md if that file exists; otherwise use a per-account fingerprint of row count plus the maximum modified date, record it with each run, and list the limitation.
- **warehouse_writes**: Use multi-row parameterised INSERT batches (the Python adapter's method) unless dotnet/docs/PLATFORM-RISKS.md proves a faster supported bulk path on Fabric Warehouse. Retry on SQL errors 24556, 3960 and 1205. Never use EF Core migrations against Fabric Warehouse.
- **mediator**: Use the in-house mediator (ADR 0003). No MediatR, and no libraries with commercial licences. Check a package's licence before adding it and record it in the session log.
- **scope_cuts**: Out of scope: the 10 sealed /api/workspace routes (answer exactly what the recordings show when the reference extract is absent), tools/reference_*, web retrieval inside tools/rules_ingestion beyond its HTTP surface, the mock AI gateway, and the ops scripts (migrations, grants, seeding, smoke checks), which stay in Python for now.
- **external_systems**: Never contact live Fabric, Foundry, Entra or any customer system unless the session's task names it and its approval variable is set. The hermetic seeds under contract/seed are the data source for development and replay.
- **numeric_guard**: Agents narrate and tools calculate (ADR-008). The numeric guard ports as is, with the same refusals.
- **heavy_tests**: Tag every test that runs longer than about 20 seconds or loads more than 20 MB as [Trait("Category", "heavy")]. A session's own gate is build, format, fast tests and its replay groups; heavy suites run at wave end and at the final gate.
- **route_ownership**: Each route group lives in its own folders: src/TaxCredit.Application/Features/<Group>/ and src/TaxCredit.Api/Endpoints/<Group>/ plus tests under tests/TaxCredit.Api.Tests/<Group>/. A group registers itself through an endpoint-group class discovered by the host; no shared file is edited to add or retire a route.
- **schema_messages**: Pack and draft validation (domain slice, finding on JsonSchema.Net): verdicts, keywords and paths must be correct; the English wording of messages is free. Record any case where a verdict differs from Python's jsonschema in dotnet/docs/pack-validation-deviations.md, with the reason.
- **ingestion_override**: Captured ingestion overrides a year-resolved pack's wage_basis, measuring_date and pay codes (domain finding M-01). This changes calculated figures, so keep it as ported and list it under needs_human as a fix candidate for the owner. Read the finding and the ADRs first: if the design clearly says otherwise, say so in the report, but still do not change it without the owner's decision.
- **multi_program_credit_math**: In credit_math a state with several programs prices its first program, as Python does; the typed refusals live in the run-resolution code (_client_run, program_defaults), which is ported. Do not add a refusal to credit_math. List this under needs_human as a fix candidate for the owner, since it affects figures.
- **improvements_register**: Each deliberate difference from the recorded Python behaviour is an entry in dotnet/docs/improvements/<your session>.json: {"improvements": [{"id": "IMP-<session>-1", "kind": one of defect_fix, error_text, wire_incidental, framework_default, "route": "METHOD /path/template", "case": optional text matching a recorded case id, "categories": optional list of replay categories, "path_prefix": optional JSON path, "finding": "F-n or empty", "reason": what was wrong and what the .NET host does instead (at least 20 characters)}]}. The replay gate treats failures covered by an entry as waived and shows them on the board and in the wave report for the owner to review; a changed number is never waived, and a group that relies on the register for more than the policy limit of its cases fails.
- **domain_slice**: The domain slice is certified (dotnet/docs/DOMAIN-SLICE-REPORT.md): build the application layer on top of it and do not re-port or re-verify its modules. Anything marked partial or pending in dotnet/docs/port-map.md and needed by your routes is yours to finish.

---

## Your role

You are building the **walking skeleton** of the .NET 10 host that will replace the Python API: an ASP.NET Core host whose every one of the API's operations is registered, answers the way the Python API is designed to answer at the contract level, and is scored by the contract replay tool in semantic mode. When you finish, running the replay against your host produces a **red/green board per route group**. Three later sessions will turn their groups green in parallel, so the conventions you set here (folders, registration, error shapes, hooks) decide whether they can work without touching each other's files. You do not implement business routes; you implement the layer every route sits on.

The reference is the Python API on CPython 3.12. The acceptance test is `contract/` (recordings, replay tool, seeds), not your own tests. The aim is equivalent, well-engineered behaviour, not a bug-for-bug copy: where Python's answer is a defect or a framework accident, build what the design intends and record it in your improvements register (Stage 4). Do not write code whose only purpose is to reproduce a quirk.

## Preflight

1. Read, in this order: `contract/README.md`, `contract/CONTRACT-REPORT.md` (sections 4, 5 and 6 are your specification), `contract/FINDINGS.md`, `contract/docs/normalisation.md`, `contract/docs/AUTH-CONTRACT.md`, `contract/harness/control.py` (the hooks), `contract/replay.py` (how it drives a server, how it selects a profile and resets state), `contract/inventory/routes.json` (every operation), `dotnet/docs/DOMAIN-SLICE-REPORT.md`, `dotnet/docs/SPIKE-REPORT.md`, the ADRs in `dotnet/docs/adr/`, and `dotnet/src/TaxCredit.Api/Program.cs` with the existing `TaxCredit.Application` messaging code.
2. Run the baseline: `dotnet build -warnaserror`, `dotnet format --verify-no-changes`, the fast tests. Note the durations of the existing test projects (`dotnet test --logger "trx"`) because you will tag the slow ones `heavy` in Stage 5.
3. Confirm the project shells the conductor prepared exist: `TaxCredit.Infrastructure.Persistence`, `.Sources`, `.Auth`, `.Ai` and `TaxCredit.Api.Tests`, and that `Directory.Packages.props` has a marked section for your session.

## Stage 1: the route registry and the groups

1. From `contract/inventory/routes.json` generate (and check in, with a test that fails when the inventory changes) a route table in the Api project: method, path template, name, the Python endpoint (`api.<module>.<function>`), whether it is typed, the declared parameters and request schema.
2. Write `dotnet/docs/route-groups.json` as `{"groups": {"<group>": ["METHOD /path/template", ...]}}`, partitioning **every** operation exactly once, with a test that proves it. Groups and the rule for assigning them, by the Python router module in the `endpoint` field:
   - `framework`: the app-level operations (`/api/health`, `/api/ready`, `/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`).
   - `reads_calc`: `api.scope`, `api.trend` (reads), `api.eligibility`, `api.onezero`, `api.proximity`, `api.forecast`, `api.simulate`, `api.retroactive`, `api.ingestion`, and `/api/me`.
   - `claims_artifacts_rules`: `api.claims` (and the v2 claims routes), `api.findings`, `api.artifacts`, `api.rules`, `api.rules_ingestion`, `api.audit`.
   - `drafts_runs`: `api.program_drafts`, `api.programs`, `api.run_batches`, and the run and base-year routes of `api.trend` (`POST /api/v2/clients/{id}/runs`, the `base-year` and `rebase` routes).
   - `ai`: `api.chat`, `api.summary`, `api.capabilities`.
   - `workspace_sealed`: every `/api/workspace*` route (answer exactly what the recordings show; there is no success path).
   - `gateway`: `/channel/*` and `/mcp` (not implemented in this wave).
   Check the assignment against `contract/COVERAGE.md` and the recorded scenarios and fix any route that does not fit.
3. **Registration convention.** An `IEndpointGroup` interface (`Map(IEndpointRouteBuilder)`), discovered by reflection from the Api assembly. Folder convention: `TaxCredit.Application/Features/<Group>/` and `TaxCredit.Api/Endpoints/<Group>/`. Every operation that no real endpoint has claimed is answered by a stub (HTTP 501 with a clear body) generated from the table; **a real endpoint wins automatically and no shared file is edited to retire a stub**. Prove with tests that registering a real endpoint for a stubbed operation replaces the stub with no ambiguity error.

## Stage 2: the wire format

What matters is the contract a client depends on, not Python's incidental output. Implement and test, using the recorded exchanges as fixtures read from `contract/recordings` (never copy them):

1. **JSON.** Use the standard System.Text.Json pipeline with sensible options; UTF-8, `Content-Type: application/json`. Do not build a custom writer to preserve key order or number text (`5.0` versus `5` is not a contract). Do keep the designed value types: money as a decimal string with its scale, dates and identifiers as the recordings show them, `null` fields present where the recordings carry them. Reuse the domain's `PyJson` and `PyDict` only where the evidence hash needs them and say where in `HOST-ARCHITECTURE.md`.
2. **Error shapes by family** (CONTRACT-REPORT section 4). Keep the structure clients read: the validation error `{"detail": [{"type","loc","msg",...}]}`; `{"detail": "<string>"}`; `{"detail": {"code","reason","remedy"?}}`; the nested `{"detail": {"detail": ..., "code": ...}}` of run batches; the dependency-unavailable body. Message text is free. Build a **request validator** that checks declared parameters and the body schema from the inventory (types, bounds, enums, required fields) and reports `loc`, `msg` and a sensible `type`; you need not copy Pydantic's English wording, `ctx`, or JSON-syntax offsets. Unhandled exceptions return a JSON 500 in the `{"detail": ...}` family with no stack trace (this fixes F-2 to F-6; do not return plain text).
3. **Routing behaviour:** unknown path and wrong method answer in the JSON error family (404 and 405 with `Allow`). For HEAD, trailing slashes, repeated or unknown query parameters, use the framework's sensible defaults and do not write code to imitate Python's quirks.
4. **CORS:** use the standard ASP.NET Core CORS middleware, configured from what the deployed web app needs (read the frontend and infrastructure configuration for the origins); do not reproduce Python's reflective behaviour (F-11 to F-13) or its 400 text body.
5. **Event streams** (`text/event-stream`, `event: <name>\ndata: <json>\n\n`, no buffering): keep the framing the clients parse, since streaming is functionality.
6. `ProblemDetails`, `[ApiController]` automatic 400s, status-code pages and the developer exception page must not leak a response of a different shape than the families above.

## Stage 3: the contract hooks, the clock and the identity of things

1. Implement `POST /__contract__/drain`, `/env`, `/mint` and `/reset` exactly as `harness/control.py` and `replay.py` define them (including how a profile is chosen). Calls the real work through ports in `Application/Ports/Contract/` with no-op defaults: persistence provides the real reset later. `mint` signs tokens with a test key generated at start-up; validation of those tokens is the auth session's job, so define the port (`ITokenMinter`) and a default that signs and records.
2. Deterministic clock, id and secret sources behind ports, switched by the hooks, as `contract/docs/normalisation.md` describes (a frozen clock, sequential UUID-shaped ids, a fixed secret). They are test seams, off in production.
3. These hooks exist only when `TCC_CONTRACT_HOOKS=1`; in any other configuration they answer 404.

## Stage 4: the replay board

1. Start the host and run `python -m contract.replay --mode semantic` against it as the conductor does (working directory `backend`, `PYTHONPATH` the worktree root, `CONTRACT_PYTHON` the 3.12 oracle; see `contract/README.md`). Use `--scenario` to iterate on one scenario at a time.
2. Create `dotnet/docs/improvements/W1-skeleton.json` (the register described in the policy) with one entry per deliberate difference you make, each with a precise route, a kind and a reason, and add a test that validates the file's structure. Then make the `framework` group pass at least 50% (the generic wire behaviour, the app-level routes and the stubs' 405/404/307/CORS handling should already lift it). The rest stays red by design. Write what remains red in the board summary of `HOST-ARCHITECTURE.md`.
3. `dotnet/docs/HOST-ARCHITECTURE.md` documents: the conventions above, how to add an endpoint group, how to run the replay for one group locally, how errors and numbers are produced, the folder ownership rules, and a list of every ASP.NET Core default you had to override and why (use CONTRACT-REPORT section 5 as the checklist).

## Stage 5: tests and the heavy tag

1. Fast tests for the wire layer in `TaxCredit.Api.Tests` (in-process host, no network), reading recordings from `contract/recordings`.
2. Tag every existing test that runs longer than about 20 seconds or loads more than 20 MB (the parity and golden suites in `TaxCredit.Parity.Tests` and `TaxCredit.Domain.Tests`) with `[Trait("Category", "heavy")]`; do not change what they assert. Show before and after the duration of `dotnet test --filter "Category!=heavy"` in your log; the fast set should finish in a few minutes.
3. Architecture tests: the Api project may reference Application and the infrastructure projects only for composition; Domain stays pure.

## Traps to expect

| Trap | What to do |
|---|---|
| Copying Python quirks because a recording shows them | Build the designed behaviour; record the difference in the improvements register with a reason |
| A custom JSON writer to keep key order or `5.0` | Do not; the replay runs in semantic mode and tolerates both |
| Hiding a real regression in the register | A changed number is never waived, and a group may rely on the register for only 10% of its cases; use it for defects and framework defaults, not to make red go green |
| Model binding coerces and defaults | Validate against the inventory specs yourself; never bind leniently |
| ASP.NET `ProblemDetails` and automatic 400s | Replace them with the error families above |
| The in-process test server hides socket behaviour | Always also run the real host through the replay tool |

## Evidence this plan is based on

`contract/CONTRACT-REPORT.md` sections 4 to 6; `contract/FINDINGS.md` F-11 to F-13; `contract/harness/control.py`; `contract/inventory/routes.json`; `contract/COVERAGE.md`; `dotnet/docs/DOMAIN-SLICE-REPORT.md`; `dotnet/docs/SPIKE-REPORT.md`.

---

## Gates (checked by the conductor after you finish, mechanically)

- `no_halt`: no HALT.md in the worktree
- `commits_present`: at least one commit on your branch
- `clean_tree`: everything committed
- `not_pushed`: the branch is not on any remote
- `owned_paths`: every changed file is inside your owned paths
- `status_json`: the STATUS.json finish file exists and parses
- `report_present`: the report files named below exist
- `dotnet_build`: `dotnet build -warnaserror` passes on the whole solution
- `dotnet_format`: `dotnet format --verify-no-changes` passes
- `tests_fast`: all tests not tagged `heavy` pass
- `replay`: the contract replay (semantic mode) meets the thresholds for your route groups; failures covered by your improvements register entries are shown separately and are capped
- report required: `dotnet/docs/HOST-ARCHITECTURE.md`
- report required: `dotnet/docs/route-groups.json`
- replay thresholds: framework >= 50%

If a gate fails you will be resumed with its output and asked to fix it. Run the same checks yourself before you finish.

---

## Rules (fixed by the conductor; they cannot be changed by the task)

- **Work only in `C:\Projects\GitHub\tcc-dotnet-w1-skeleton`** (branch `dotnet/w1-skeleton`). Do not edit the main checkout or any other worktree.
- **Never push, never open a pull request, never change a remote.** Pushing is also blocked mechanically; do not try to work around it. Commit locally in small, sensible commits with the trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- **You may create or modify only:** `dotnet/src/TaxCredit.Api/**`, `dotnet/src/TaxCredit.ServiceDefaults/**`, `dotnet/src/TaxCredit.AppHost/**`, `dotnet/src/TaxCredit.Application/**`, `dotnet/tests/TaxCredit.Api.Tests/**`, `dotnet/tests/TaxCredit.Architecture.Tests/**`, `dotnet/tests/TaxCredit.Parity.Tests/**`, `dotnet/tests/TaxCredit.Domain.Tests/**`, `dotnet/Directory.Packages.props`, `dotnet/Directory.Build.props`. Any other change fails a gate. Never edit existing product files (`backend/`, `frontend/`, `infra/`, `scripts/`, `channel_orchestrator/`, `docs/`, `.github/`) unless they are inside your owned paths.
- **The reference is the Python product on CPython 3.12** (`C:\Projects\py312-oracle\.venv\Scripts\python.exe`): it shows what the system is meant to do, but it is not a specification to copy defect for defect. Build the designed functionality and the contract clients depend on; do not reproduce defects or framework accidents. Never change the Python code. Record each deliberate difference in `dotnet/docs/improvements/skeleton.json` as the policy describes, and record Python oddities in `STATUS.json` under `findings`. A changed calculated figure is never an improvement. Never loosen a comparison, delete a test or weaken a threshold to make something pass.
- **Nobody can answer questions.** Use the policy decisions above. When a decision is missing, take the reading closest to the documented design and the Python behaviour, record it under `needs_human` in `STATUS.json`, and keep going.
- **Customer-neutral:** no customer names, tenant or server names, identifiers, tokens or secrets in any file, log or report. Synthetic data only.
- **Tests:** tag long-running tests `[Trait("Category", "heavy")]`; the fast gate excludes them. Keep the fast gate quick.
- **Shared files:** put package versions only inside your marked section of `Directory.Packages.props` if your session has one; never add a package another section already declares. Register your services and endpoints from your own project (an `AddXxx` extension or endpoint-group class); do not edit another session's files.
- **Keep a running log** of decisions, findings and gate results in `dotnet/docs/skeleton-log.md`.
- **Budget:** you have a limited time and credit budget. Finish each stage with its checks green before polishing, and finish the whole task rather than perfecting one part.

---

## Hard stops (fixed by the conductor)

Write `dotnet/docs/HALT-skeleton.md` (what happened, what you tried, what a human must decide), commit it, and end the run if any of these happens:

1. A push, a remote change, a change outside your owned paths, or a destructive command outside your worktree would be needed.
2. A secret, token, tenant or server name, customer identifier or private data would be written to a file.
3. Equivalent behaviour for the designed functionality cannot be reached after three honest attempts on the same item (this is a valid, important result: report it, do not hide it).
4. The Python oracle environment is not CPython 3.12, or imports the wrong checkout, and configuration cannot fix it.

---

## Finish (fixed by the conductor)

When the task is done, or you are stopping at a hard stop, write `dotnet/docs/status/skeleton.json` in your worktree and commit it. It is machine-read; it must be valid JSON with this shape:

```json
{
  "session": "skeleton",
  "branch": "dotnet/w1-skeleton",
  "head": "<short commit>",
  "summary": "<at most ten lines: what was built, what the gates say, what surprised you>",
  "stages": {"<stage id>": "done | partial | skipped"},
  "gates_claimed": {"<gate>": true},
  "deviations": [{"id": "DEV-1", "what": "...", "why": "...", "decision_needed": false}],
  "findings": ["Python behaviour that looks wrong, or traps found"],
  "open_questions": ["..."],
  "needs_human": [{"item": "...", "why": "..."}],
  "reports": ["relative path of each report you wrote"]
}
```

Then print a short summary. The conductor reads your reports and `STATUS.json` to plan the next wave, so write them for a reader who has not seen your session: numbers, evidence, exact error messages, and what the next session can now rely on.
