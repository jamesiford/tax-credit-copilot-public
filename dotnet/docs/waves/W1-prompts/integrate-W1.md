# Integrate wave W1

Session `integrate-W1` of wave `W1`. You run unattended: nobody will answer questions, so do not ask any.
Worktree: `C:\Projects\GitHub\tcc-dotnet-integration` (branch `dotnet/integration`, created from `b8e17f467845301f7afd01b97b2c9dbd84b3cfdf`).

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

You are repairing an integrated branch. Several parallel sessions each passed their own gates, and the conductor merged their branches into this one. The combined result fails the wave checks below. Make it green without changing what any session ported: you fix integration problems, not behaviour.

## Preflight

Read the `dotnet/docs/STATUS.json` files and the session logs under `dotnet/docs/` that the merged sessions wrote (they explain what each owns), then read the failures below.

## Failures to fix

### dotnet_build
exit 1
...t 7.1.2.
C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Api.Tests\TaxCredit.Api.Tests.csproj : error NU1506: Warning As Error: Duplicate 'PackageVersion' items found. Remove the duplicate items or use the Update functionality to ensure a consistent restore behavior. The duplicate 'PackageVersion' items are: Microsoft.Data.SqlClient 7.1.2, Microsoft.Data.SqlClient 7.1.2.
C:\Projects\GitHub\tcc-dotnet-integration\dotnet\src\TaxCredit.Infrastructure.Auth\TaxCredit.Infrastructure.Auth.csproj : error NU1506: Warning As Error: Duplicate 'PackageVersion' items found. Remove the duplicate items or use the Update functionality to ensure a consistent restore behavior. The duplicate 'PackageVersion' items are: Microsoft.Data.SqlClient 7.1.2, Microsoft.Data.SqlClient 7.1.2.
C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Infrastructure.Persistence.Tests\TaxCredit.Infrastructure.Persistence.Tests.csproj : error NU1506: Warning As Error: Duplicate 'PackageVersion' items found. Remove the duplicate items or use the Update functionality to ensure a consistent restore behavior. The duplicate 'PackageVersion' items are: Microsoft.Data.SqlClient 7.1.2, Microsoft.Data.SqlClient 7.1.2.
C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Infrastructure.Auth.Tests\TaxCredit.Infrastructure.Auth.Tests.csproj : error NU1506: Warning As Error: Duplicate 'PackageVersion' items found. Remove the duplicate items or use the Update functionality to ensure a consistent restore behavior. The duplicate 'PackageVersion' items are: Microsoft.Data.SqlClient 7.1.2, Microsoft.Data.SqlClient 7.1.2.
C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Parity.Tests\TaxCredit.Parity.Tests.csproj : error NU1506: Warning As Error: Duplicate 'PackageVersion' items found. Remove the duplicate items or use the Update functionality to ensure a consistent restore behavior. The duplicate 'PackageVersion' items are: Microsoft.Data.SqlClient 7.1.2, Microsoft.Data.SqlClient 7.1.2.
C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Infrastructure.Sources.Tests\TaxCredit.Infrastructure.Sources.Tests.csproj : error NU1506: Warning As Error: Duplicate 'PackageVersion' items found. Remove the duplicate items or use the Update functionality to ensure a consistent restore behavior. The duplicate 'PackageVersion' items are: Microsoft.Data.SqlClient 7.1.2, Microsoft.Data.SqlClient 7.1.2.
    0 Warning(s)
    18 Error(s)

Time Elapsed 00:00:02.90


### dotnet_format
exit 2
...GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Parity.Tests\PayloadHelperInvoke.cs(43,75): error CS1503: Argument 1: cannot convert from 'TaxCredit.Infrastructure.Payroll.CsvPayrollSource' to 'TaxCredit.Domain.Pipeline.IPayrollSource' [C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Parity.Tests\TaxCredit.Parity.Tests.csproj]
C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Parity.Tests\PayloadHelperInvoke.cs(55,49): error CS0246: The type or namespace name 'IPayrollSource' could not be found (are you missing a using directive or an assembly reference?) [C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Parity.Tests\TaxCredit.Parity.Tests.csproj]
C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Parity.Tests\PayloadHelperInvoke.cs(55,39): error CS0246: The type or namespace name 'PayRow' could not be found (are you missing a using directive or an assembly reference?) [C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Parity.Tests\TaxCredit.Parity.Tests.csproj]
C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Parity.Tests\PayloadHelperInvoke.cs(55,19): error CS0246: The type or namespace name 'PayRow' could not be found (are you missing a using directive or an assembly reference?) [C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Parity.Tests\TaxCredit.Parity.Tests.csproj]
C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Parity.Tests\PackValidationParityTests.cs(100,163): error CS0246: The type or namespace name 'Json' could not be found (are you missing a using directive or an assembly reference?) [C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Parity.Tests\TaxCredit.Parity.Tests.csproj]
C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Parity.Tests\PackValidationParityTests.cs(145,43): error CS0246: The type or namespace name 'IJsonSchemaValidator' could not be found (are you missing a using directive or an assembly reference?) [C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Parity.Tests\TaxCredit.Parity.Tests.csproj]
C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Parity.Tests\PackValidationParityTests.cs(145,28): error CS0246: The type or namespace name 'SchemaFinding' could not be found (are you missing a using directive or an assembly reference?) [C:\Projects\GitHub\tcc-dotnet-integration\dotnet\tests\TaxCredit.Parity.Tests\TaxCredit.Parity.Tests.csproj]


### tests_fast
skipped: the build failed

### replay
skipped: the build failed

## Stage 1: diagnose and fix

Typical causes: two sessions registered the same service or route, a package declared twice or at two versions, a project reference cycle, formatting drift after a merge, a heavy test that is not tagged, a replay regression caused by a shared helper. Fix the cause in the smallest way, never by deleting or weakening a test, comparison or threshold. If a failure is a real parity regression in one session's code, fix it there and note it in your STATUS.json `findings`.

## Stage 2: re-run

Run the failing checks yourself until they pass, then the whole fast suite, then finish.

---

## Gates (checked by the conductor after you finish, mechanically)

- replay thresholds: board only (the replay must run and produce a report)

If a gate fails you will be resumed with its output and asked to fix it. Run the same checks yourself before you finish.

---

## Rules (fixed by the conductor; they cannot be changed by the task)

- **Work only in `C:\Projects\GitHub\tcc-dotnet-integration`** (branch `dotnet/integration`). Do not edit the main checkout or any other worktree.
- **Never push, never open a pull request, never change a remote.** Pushing is also blocked mechanically; do not try to work around it. Commit locally in small, sensible commits with the trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- **You may create or modify only:** `dotnet/**`, `contract/**`, `parity/**`. Any other change fails a gate. Never edit existing product files (`backend/`, `frontend/`, `infra/`, `scripts/`, `channel_orchestrator/`, `docs/`, `.github/`) unless they are inside your owned paths.
- **The reference is the Python product on CPython 3.12** (`C:\Projects\py312-oracle\.venv\Scripts\python.exe`): it shows what the system is meant to do, but it is not a specification to copy defect for defect. Build the designed functionality and the contract clients depend on; do not reproduce defects or framework accidents. Never change the Python code. Record each deliberate difference in `dotnet/docs/improvements/integrate-W1.json` as the policy describes, and record Python oddities in `STATUS.json` under `findings`. A changed calculated figure is never an improvement. Never loosen a comparison, delete a test or weaken a threshold to make something pass.
- **Nobody can answer questions.** Use the policy decisions above. When a decision is missing, take the reading closest to the documented design and the Python behaviour, record it under `needs_human` in `STATUS.json`, and keep going.
- **Customer-neutral:** no customer names, tenant or server names, identifiers, tokens or secrets in any file, log or report. Synthetic data only.
- **Tests:** tag long-running tests `[Trait("Category", "heavy")]`; the fast gate excludes them. Keep the fast gate quick.
- **Shared files:** put package versions only inside your marked section of `Directory.Packages.props` if your session has one; never add a package another section already declares. Register your services and endpoints from your own project (an `AddXxx` extension or endpoint-group class); do not edit another session's files.
- **Keep a running log** of decisions, findings and gate results in `dotnet/docs/integrate-W1-log.md`.
- **Budget:** you have a limited time and credit budget. Finish each stage with its checks green before polishing, and finish the whole task rather than perfecting one part.

---

## Hard stops (fixed by the conductor)

Write `dotnet/docs/HALT-integrate-W1.md` (what happened, what you tried, what a human must decide), commit it, and end the run if any of these happens:

1. A push, a remote change, a change outside your owned paths, or a destructive command outside your worktree would be needed.
2. A secret, token, tenant or server name, customer identifier or private data would be written to a file.
3. Equivalent behaviour for the designed functionality cannot be reached after three honest attempts on the same item (this is a valid, important result: report it, do not hide it).
4. The Python oracle environment is not CPython 3.12, or imports the wrong checkout, and configuration cannot fix it.

---

## Finish (fixed by the conductor)

When the task is done, or you are stopping at a hard stop, write `dotnet/docs/status/integrate-W1.json` in your worktree and commit it. It is machine-read; it must be valid JSON with this shape:

```json
{
  "session": "integrate-W1",
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
