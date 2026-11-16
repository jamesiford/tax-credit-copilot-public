# Integrate wave W2

Session `integrate-W2` of wave `W2`. You run unattended: nobody will answer questions, so do not ask any.
Worktree: `C:\Projects\GitHub\tcc-dotnet-integration` (branch `dotnet/integration`, created from `b766691e75716c0060dbffe140ba174e0fde6c8b`).

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

You are the convergence engineer for wave 2 of the .NET port. Four route-group sessions (reads and calculation, claims/artifacts/rules, drafts and runs, AI) each implemented their routes on separate branches, and the conductor has merged all four into this branch. Each session worked in isolation: it could edit only its own folders, so it could not fix anything shared, and it could not see its siblings' work. The merged branch builds and formats, but it fails the wave checks below. Your job is to bring the merged branch to the replay thresholds by fixing the shared problems and the remaining real differences, across every folder of the .NET solution. You own `dotnet/**`, `contract/**` and `parity/**` for this task; the ownership blockers the route sessions reported do not apply to you.

You have a long budget. Use it in order: settle the shared problems first, because many failing replay cases are downstream of them; then measure; then fix by group.

## Preflight

1. Read the policy decisions above again, in particular `parity`, `parity_tiers`, `python_oddities`, `list_totals` and `replay_scoring`. Free-text paths (validation message wording, echoed input and context, the `Vary` header, validation finding messages) are tolerated by the replay already. Response metadata keeps the recorded Python semantics (`list_totals`).
2. Read what the four sessions found: their halt notes under `dotnet/docs/waves/W2-attempt1/` (named `<session>-halt.md`), their reports (`ROUTES-READS-REPORT.md`, `ROUTES-CLAIMS-REPORT.md`, `ROUTES-DRAFTS-REPORT.md`, `ROUTES-AI-REPORT.md` where present), their improvements registers under `dotnet/docs/improvements/`, `dotnet/docs/COMPOSITION-REPORT.md` and `dotnet/docs/HOST-ARCHITECTURE.md`. Treat their `needs_human` lists as your work list; each item names the shared file or decision it was blocked on.
3. Run the baseline yourself: `dotnet build -warnaserror`, `dotnet format --verify-no-changes`, the fast tests, and the contract replay exactly as the conductor does (working directory `backend`, `PYTHONPATH` the worktree root, `CONTRACT_PYTHON` the 3.12 oracle, `--mode semantic`; see `contract/README.md`). Note the board per route group.

## Failures the conductor reported

### replay
below threshold: drafts_runs 88.5% < 90%
replay (semantic): 1769 exchanges, 2113 failing field(s), 509 covered by the improvements register, 1248 on tolerated free-text paths
_unassigned              75.1%  (238/317), waived 0 (0.0%)
ai                       96.3%  (26/27), waived 3 (11.1%)
claims_artifacts_rules   92.1%  (291/316), waived 70 (22.2%)
drafts_runs              88.5%  (286/323), waived 42 (13.0%)
framework               100.0%  (17/17), waived 9 (52.9%)
gateway                   0.8%  (2/255), waived 0 (0.0%)
reads_calc               98.1%  (406/414), waived 26 (6.3%)
workspace_sealed         82.3%  (79/96), waived 3 (3.1%)

## Stage 1: shared tests and shared composition

1. **Stale placeholder tests.** Some shared tests in `dotnet/tests/TaxCredit.Api.Tests/Framework` assert that a specific route still returns 501, which is false once a feature implements it. Rewrite them so they pick a still-stubbed operation from the route table at run time (and skip with a clear reason if none remains), so they cannot go stale again. Do not weaken what they prove: a real endpoint still replaces exactly one stub with no ambiguity, and discovery still registers services before the container is built.
2. **Direct runtime construction.** A provider-selection test builds the runtime graph without feature modules and fails to resolve feature collaborators. Make the test compose the feature modules the same way production does; do not add service location or a second startup graph.
3. **Everything else the four `needs_human` lists name that lives in shared code:** the validation check counts the runtime reports versus what the recordings show, the metadata shape of new-reader footprints, mediator and scoped-lease lifetimes, the BigInteger draft-offset limit, and the AI session's sibling collaborators (it consumes services that now exist because the reads and claims features are merged; wire them). For each, fix the cause, not the symptom, and add a regression test.
4. Commit after each fix with the build, format and fast tests passing.

## Stage 2: harness and determinism

Many replay cases fail because of how a scenario is set up, not because of a handler. Check, with the replay tool's own diagnostics: the profile selection (P1 versus P2) and the reset hook, token minting and the acting-user and agent flows from `contract/docs/AUTH-CONTRACT.md`, the deterministic clock, id and secret sources from `contract/docs/normalisation.md` (identifier counters and the order they are consumed in must match the recordings), and post-run manifest state. Reproduce one failing scenario at a time with `--scenario`, find the first divergence, fix it, and re-run; later failures in the same scenario often disappear. Do not consume dummy identifiers or invent counts to match a recording; make the real behaviour deterministic.

## Stage 3: measure and fix by group

Re-run the full replay and tabulate, per route group, the failures by category and path. Free-text paths are already removed. For each remaining cluster decide which it is:

- **A real defect in a feature** (wrong value, missing or extra field, wrong status): fix it in the feature. Calculated figures on the certified-figure routes must equal the recording exactly; a changed figure is never an improvement.
- **A deliberate improvement** that the policy asks for (a plain-text 500 turned into a JSON error, an unbounded input now bounded, a race fixed): keep it and record it in `dotnet/docs/improvements/converge.json` with a precise route, a kind and a reason. A group may rely on the register for at most the share set in the policy.
- **A recording artefact** that depends on something outside the port (for example the recording harness's own state): explain it in your report and register it only if it is a defect fix.

Work the largest clusters first. After each fix re-run only the affected scenario, then the whole replay before you commit.

## Stage 4: finish

Run the whole gate set yourself: build with warnings as errors, format, the fast tests, and the replay. The thresholds are in the conductor's failure summary above. If a threshold cannot honestly be met for a group, stop, write `dotnet/docs/HALT-integrate-W2.md` with the board per group, the remaining clusters with counts, and what a human must decide, and do not weaken a threshold, a comparison or a test to get past it. Whatever the outcome, write `dotnet/docs/ROUTES-CONVERGENCE-REPORT.md` with the board before and after, each fix and its evidence, the register entries added, and the open decisions for the owner, and commit it.

## Traps to expect

| Trap | What to do |
|---|---|
| Fixing a symptom in a feature that is really a shared or harness problem | Reproduce one scenario, find the first divergence, fix the cause |
| Matching a recording by returning canned values or by special-casing the replay caller | Never; fix the real behaviour |
| Hiding a real regression in the register | A changed number or status is never waived; the register is for defect fixes |
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
- **The reference is the Python product on CPython 3.12** (`C:\Projects\py312-oracle\.venv\Scripts\python.exe`): it shows what the system is meant to do, but it is not a specification to copy defect for defect. Build the designed functionality and the contract clients depend on; do not reproduce defects or framework accidents. Never change the Python code. Record each deliberate difference in `dotnet/docs/improvements/integrate-W2.json` as the policy describes, and record Python oddities in `STATUS.json` under `findings`. A changed calculated figure is never an improvement. Never loosen a comparison, delete a test or weaken a threshold to make something pass.
- **Nobody can answer questions.** Use the policy decisions above. When a decision is missing, take the reading closest to the documented design and the Python behaviour, record it under `needs_human` in `STATUS.json`, and keep going.
- **Customer-neutral:** no customer names, tenant or server names, identifiers, tokens or secrets in any file, log or report. Synthetic data only.
- **Tests:** tag long-running tests `[Trait("Category", "heavy")]`; the fast gate excludes them. Keep the fast gate quick.
- **Shared files:** put package versions only inside your marked section of `Directory.Packages.props` if your session has one; never add a package another section already declares. Register your services and endpoints from your own project (an `AddXxx` extension or endpoint-group class); do not edit another session's files.
- **Keep a running log** of decisions, findings and gate results in `dotnet/docs/integrate-W2-log.md`.
- **Budget:** you have a limited time and credit budget. Finish each stage with its checks green before polishing, and finish the whole task rather than perfecting one part.

---

## Hard stops (fixed by the conductor)

Write `dotnet/docs/HALT-integrate-W2.md` (what happened, what you tried, what a human must decide), commit it, and end the run if any of these happens:

1. A push, a remote change, a change outside your owned paths, or a destructive command outside your worktree would be needed.
2. A secret, token, tenant or server name, customer identifier or private data would be written to a file.
3. Equivalent behaviour for the designed functionality cannot be reached after three honest attempts on the same item (this is a valid, important result: report it, do not hide it).
4. The Python oracle environment is not CPython 3.12, or imports the wrong checkout, and configuration cannot fix it.

---

## Finish (fixed by the conductor)

When the task is done, or you are stopping at a hard stop, write `dotnet/docs/status/integrate-W2.json` in your worktree and commit it. It is machine-read; it must be valid JSON with this shape:

```json
{
  "session": "integrate-W2",
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
