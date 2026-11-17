# Integrate wave W3

Session `integrate-W3` of wave `W3`. You run unattended: nobody will answer questions, so do not ask any.
Worktree: `C:\Projects\GitHub\tcc-dotnet-integration` (branch `dotnet/integration`, created from `ffc48b3b4004ac6c41e2f228a9c5c8c3a1f73603`).

---

## Pre-approved decisions (policy)

The owner decided these in advance. Follow them without asking. If something needs a decision that is not covered here, choose the reading closest to the documented design and the Python behaviour, record it in STATUS.json under `needs_human`, and continue.

- **parity**: Equivalent behaviour, not bug-for-bug. The target is the designed functionality and the contract a client depends on: the same routes and methods, authentication and authorisation, request and response fields and their types, the meaning of each status code, money as a decimal string with its scale, and the same calculated figures for the same valid input. Do not reproduce defects, accidents of Python, FastAPI or Pydantic, or artefacts of the recording harness (plain-text error bodies, key order, number lexemes such as 5.0 versus 5, byte-level headers and wording, HEAD and trailing-slash quirks, reflected CORS headers). Never write code whose only purpose is to reproduce a defect or a framework artefact. Where the Python behaviour is a bug or an accident, implement what the design, the ADRs, the docs or sound engineering intend, and record it in dotnet/docs/improvements/<session>.json (see improvements_register). If the same issue turns up naturally in the .NET code, that is acceptable; note it as a finding.
- **parity_tiers**: The replay runs in semantic mode (values equal; key order and number lexeme free). Tier A (certified-figure routes and every gateway tool result): the values must be equal, and a changed figure is never an improvement. Tier B (everything else with a JSON body): values equal. Tier C (error responses): keep the error shape family (a JSON body with `detail`, as the clients read it) and the right status; the message text is free. Tier D (zip and xlsx container bytes, timing, model output): out of scope. Anything else that differs from a recording for a good reason goes in the improvements register, not into reproduction code.
- **python_oddities**: Fix defects instead of reproducing them. F-2 to F-6 (plain-text 500s): return the JSON error family with the correct status, a 4xx where the cause is a client error, and never a stack trace. F-8 (duplicate claims): handle duplicates as the claims design intends (idempotent or a 409), and record which. F-14 to F-16 (inconsistent writer checks): apply the writer check consistently to every route that writes. F-1 (a GET that never returns because magnitude is unbounded): bound it and refuse out-of-range values with a 422. F-17 and every other entry in contract/FINDINGS.md: apply the same principle; read the finding first. Exception: if fixing something would change a calculated figure, a stored value or an authorisation outcome for a valid request, keep the Python result, and list it under needs_human as a fix candidate for the owner.
- **list_totals**: Response metadata that counts things (totals, counts, populations) keeps the recorded Python semantics, so a list endpoint returns what the recordings show. Do not introduce page-independent totals or other metadata redesigns during the port; record any real concern as a finding for after cutover.
- **replay_scoring**: The replay runs in semantic mode and the policy tolerates free-text paths globally (validation message wording, echoed input and context, the Vary header, validation finding messages), so these never need a register entry. A status difference, a changed number or a missing or extra field elsewhere is a real difference: fix it, or register it only if it is a defect fix. During route-group sessions the replay is informational; the thresholds apply to the merged branch.
- **durable_manifest_counts**: Dry-run preview counters in run-batch responses (never_run, skip_coverage and similar, under `preview` or `dry_run_summary`) follow the real durable run manifest, as deployed, not the recording harness's disconnected in-memory store (finding F-18). Where they differ from a recording for that reason, register an improvement entry for that exact route and path; the policy permits numeric differences on those paths only. This does not extend to any calculated figure.
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

You are the convergence engineer for wave 3 of the .NET port. Two sessions worked in isolation on separate branches, and the conductor has merged both into this branch: the **channel gateway** (`TaxCredit.Gateway`: REST routes, the MCP server with its 36 tools, downloads, narration audit, the numeric-integrity guard) and the **hosted orchestrator** (`TaxCredit.Orchestrator`). Each could edit only its own folders, so neither could fix anything shared. The merged branch fails the wave checks below. Your job is to bring it to the thresholds by fixing shared problems and the remaining real differences, across every folder of the .NET solution. You own `dotnet/**`, `contract/**` and `parity/**` for this task; the ownership blockers the two sessions reported do not apply to you.

You have a long budget. Settle the shared problems first (many failing cases are downstream of them), then measure, then fix by cluster.

## Preflight

1. Read the policy decisions above again, in particular `parity`, `parity_tiers`, `python_oddities`, `replay_scoring` and `list_totals`. Free-text paths and error wording are tolerated by the replay already. The gateway's tool schemas, descriptions and tool results are tier A: their values must equal the recordings (key order and number text are free).
2. Read what the two sessions found: their reports (`dotnet/docs/GATEWAY-REPORT.md`, `dotnet/docs/ORCHESTRATOR-REPORT.md`), their status files and `needs_human` lists (treat them as your work list), their improvements registers under `dotnet/docs/improvements/`, and the wave 2 convergence report `dotnet/docs/ROUTES-CONVERGENCE-REPORT.md` for how the replay is run and what was settled.
3. Run the baselines yourself: `dotnet build -warnaserror`, `dotnet format --verify-no-changes`, the fast tests, and **two** contract replays as the conductor does (working directory `backend`, `PYTHONPATH` the worktree root, `CONTRACT_PYTHON` the 3.12 oracle, `--mode semantic`; see `contract/README.md`): one against the API host (`dotnet/src/TaxCredit.Api`) for the route groups, and one against the gateway host (`dotnet/src/TaxCredit.Gateway`) for the gateway group. Note both boards. The recordings whose scenario name starts with `g1_` belong to the gateway group.

## Failures the conductor reported

### replay_gateway
below threshold: gateway 32.5% < 90%
replay (semantic): 1769 exchanges, 7997 failing field(s), 657 covered by the improvements register, 653 on tolerated free-text paths
_unassigned               4.7%  (15/317), waived 0 (0.0%)
ai                        0.0%  (0/27), waived 0 (0.0%)
claims_artifacts_rules    5.1%  (16/316), waived 5 (1.6%)
drafts_runs               9.9%  (32/323), waived 2 (0.6%)
framework                41.2%  (7/17), waived 1 (5.9%)
gateway                  32.5%  (83/255), waived 8 (3.1%)
reads_calc               27.1%  (112/414), waived 60 (14.5%)
workspace_sealed          3.1%  (3/96), waived 3 (3.1%)

## Stage 1: shared problems

1. **Gateway host replay.** The gateway tools call the API. Make the gateway host runnable on its own for the replay (for example by composing the API's application services in-process through project references, or by starting against the API host when a documented environment variable is set), and document how in `HOST-ARCHITECTURE.md`. The two replays must be repeatable with no manual step.
2. **Shared tests and composition.** Fix stale or ambiguous shared tests, double registrations, package version conflicts and project reference problems the merge exposed, in the smallest way, without weakening any test. Add a regression test for each cause.
3. **Everything else the `needs_human` lists name that lives in shared code.**
4. Commit after each fix with the build, format and fast tests passing.

## Stage 2: harness and determinism

Reproduce one failing gateway scenario at a time with `--scenario`, find the first divergence, fix the cause, and re-run; later failures in a scenario often disappear. Check the MCP protocol envelope (initialize, ping, tools/list, tools/call, error codes), authentication and the minted-token flows, single-use download tickets, and the deterministic clock, id and secret sources from `contract/docs/normalisation.md`. Do not consume dummy identifiers or invent values to match a recording.

## Stage 3: measure and fix by cluster

Re-run both replays and tabulate failures per group by category and path (free-text paths are already removed). For each remaining cluster decide: a real defect (fix it; a changed figure or tool result value is never an improvement), a deliberate improvement the policy asks for (register it in `dotnet/docs/improvements/converge-w3.json` with a precise route, kind and reason), or a recording artefact (explain it in your report). Work the largest clusters first. The thresholds are in the failure summary above.

## Stage 4: finish

Run the whole gate set yourself: build with warnings as errors, format, the fast tests, and both replays. If a threshold cannot honestly be met, stop, write `dotnet/docs/HALT-integrate-W3.md` with both boards, the remaining clusters with counts and what a human must decide, and do not weaken a threshold, a comparison or a test to get past it. Whatever the outcome, write `dotnet/docs/GATEWAY-CONVERGENCE-REPORT.md` with the boards before and after, each fix and its evidence, the register entries added and the open decisions, and commit it.

## Traps to expect

| Trap | What to do |
|---|---|
| Fixing a symptom in a tool that is really a shared or harness problem | Reproduce one scenario, find the first divergence, fix the cause |
| Matching a recording by returning canned values or special-casing the replay caller | Never; fix the real behaviour |
| The gateway host cannot reach the API during replay | Make it composable for the replay as in Stage 1; do not skip the gateway group |
| Rewriting a stale test so it proves less | Keep what it proves; make it independent of which routes are implemented |
| Spending the whole budget on the long tail | Take the large clusters first and report honestly what remains |

---

## Gates (checked by the conductor after you finish, mechanically)

- replay thresholds: framework >= 90%, reads_calc >= 95%, claims_artifacts_rules >= 90%, drafts_runs >= 90%, ai >= 90%

If a gate fails you will be resumed with its output and asked to fix it. Run the same checks yourself before you finish.

---

## Rules (fixed by the conductor; they cannot be changed by the task)

- **Work only in `C:\Projects\GitHub\tcc-dotnet-integration`** (branch `dotnet/integration`). Do not edit the main checkout or any other worktree.
- **Never push, never open a pull request, never change a remote.** Pushing is also blocked mechanically; do not try to work around it. Commit locally in small, sensible commits with the trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- **You may create or modify only:** `dotnet/**`, `contract/**`, `parity/**`, `dotnet/docs/**`. The last entry, `dotnet/docs/**`, is always yours for reports, logs, status files and the improvements register; it never needs an exception. Any other change fails a gate. Never edit existing product files (`backend/`, `frontend/`, `infra/`, `scripts/`, `channel_orchestrator/`, `docs/`, `.github/`) unless they are inside your owned paths.
- **The reference is the Python product on CPython 3.12** (`C:\Projects\py312-oracle\.venv\Scripts\python.exe`): it shows what the system is meant to do, but it is not a specification to copy defect for defect. Build the designed functionality and the contract clients depend on; do not reproduce defects or framework accidents. Never change the Python code. Record each deliberate difference in `dotnet/docs/improvements/integrate-W3.json` as the policy describes, and record Python oddities in `STATUS.json` under `findings`. A changed calculated figure is never an improvement. Never loosen a comparison, delete a test or weaken a threshold to make something pass.
- **Nobody can answer questions.** Use the policy decisions above. When a decision is missing, take the reading closest to the documented design and the Python behaviour, record it under `needs_human` in `STATUS.json`, and keep going.
- **Customer-neutral:** no customer names, tenant or server names, identifiers, tokens or secrets in any file, log or report. Synthetic data only.
- **Tests:** tag long-running tests `[Trait("Category", "heavy")]`; the fast gate excludes them. Keep the fast gate quick.
- **Shared files:** put package versions only inside your marked section of `Directory.Packages.props` if your session has one; never add a package another section already declares. Register your services and endpoints from your own project (an `AddXxx` extension or endpoint-group class); do not edit another session's files.
- **Keep a running log** of decisions, findings and gate results in `dotnet/docs/integrate-W3-log.md`.
- **Budget:** you have a limited time and credit budget. Finish each stage with its checks green before polishing, and finish the whole task rather than perfecting one part.

---

## Hard stops (fixed by the conductor)

Write `dotnet/docs/HALT-integrate-W3.md` (what happened, what you tried, what a human must decide), commit it, and end the run if any of these happens:

1. A push, a remote change, a change outside your owned paths, or a destructive command outside your worktree would be needed.
2. A secret, token, tenant or server name, customer identifier or private data would be written to a file.
3. Equivalent behaviour for the designed functionality cannot be reached after three honest attempts on the same item (this is a valid, important result: report it, do not hide it).
4. The Python oracle environment is not CPython 3.12, or imports the wrong checkout, and configuration cannot fix it.

---

## Finish (fixed by the conductor)

When the task is done, or you are stopping at a hard stop, write `dotnet/docs/status/integrate-W3.json` in your worktree and commit it. It is machine-read; it must be valid JSON with this shape:

```json
{
  "session": "integrate-W3",
  "branch": "dotnet/integration",
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
