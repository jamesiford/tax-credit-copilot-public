# TaxCredit .NET port (spike and domain slice)

A time-boxed spike that proves, with bit-level evidence, whether the Python calculation engine of this repository can be
reproduced exactly in C#/.NET, and lays the multi-project solution a full port would use. The **Python engine is the oracle**;
nothing here changes Python behaviour. Results: [`docs/SPIKE-REPORT.md`](docs/SPIKE-REPORT.md).

## Layout

```
dotnet/
  TaxCredit.slnx  global.json  Directory.Build.props  Directory.Packages.props  .editorconfig
  src/
    TaxCredit.Domain/           pure BCL: Numerics (the Python compatibility layer) and Calculation (the engine)
    TaxCredit.Application/      mediator, pipeline (Audit > Authorization > Validation > Handler), ports, use cases
    TaxCredit.Infrastructure/   adapters for the ports
    TaxCredit.Api/              minimal HTTP host and composition root
    TaxCredit.ServiceDefaults/  telemetry, health, resilience (Aspire pattern)
    TaxCredit.AppHost/          Aspire app host: describes local resources only
  tests/
    TaxCredit.Domain.Tests/        readable spot checks
    TaxCredit.Parity.Tests/        golden replay (G1, G2), differential fuzz (G3), mutation self-test, benchmark
    TaxCredit.Architecture.Tests/  layering rules and pipeline contract
  docs/  adr/ (decisions), findings.md, parity-report.md, spike-log.md, SPIKE-REPORT.md
parity/                          new Python files only: exporters, engine CLI and the committed goldens
```

## Run the API locally against live Fabric data

The .NET API can read the same lakehouse the Python product reads, with operational state kept local.

```pwsh
az login                       # an identity that can read the lakehouse SQL endpoint; the Fabric capacity must be Active
.\dotnet\run-local.ps1         # http://127.0.0.1:8000, the port the Vite dev proxy expects
.\dotnet\run-local.ps1 -Offline   # synthetic seed data only, no Azure calls
cd frontend; npm run dev       # http://localhost:5173 (stop the Python API first: both use port 8000)
```

**From Visual Studio instead:** `.\dotnet\configure-local.ps1` writes launch profiles (`TaxCredit.Api - live lakehouse` and
`TaxCredit.Api - offline`) to `src\TaxCredit.Api\Properties\launchSettings.json` (gitignored, it holds your lakehouse host name). Set
`TaxCredit.Api` as the startup project, pick the profile beside the Run button and press Run. `-Session` also exports the variables into
the current PowerShell session. The frontend is not part of the solution; run `npm run dev` in a terminal. The Aspire `TaxCredit.AppHost`
starts a local SQL Server container, not the live lakehouse.

`run-local.ps1` reads `backend\.env` (`LAKEHOUSE_SQL_SERVER`, `LAKEHOUSE_SQL_DATABASE`, `SOURCE_SCHEMA`, `AUTH_MODE`) and maps it to the
.NET names (`SOURCE_SQL_SERVER`, `SOURCE_SQL_DATABASE`, ...). Claims, findings and runs stay in a local SQLite file and artifacts on local
disk; nothing is written to Fabric unless you pass `-Persistence warehouse`. It sets `AZURE_TOKEN_CREDENTIALS=AzureCliCredential` so the
signed-in `az` account is the one used (the default credential chain tries Visual Studio and VS Code sign-ins first). `GET /api/ready`
reports `ready: true` and the account count when the source is reachable. The hosts run with ICU globalization because
`Microsoft.Data.SqlClient` does not support invariant mode; the test projects keep invariant mode.

Not wired yet: the Foundry AI providers (`FOUNDRY_PROJECT_ENDPOINT` without an invocation factory reports the provider unavailable), the
sealed `/api/workspace` routes, and Warehouse persistence (the `tcc_ops.finding_audit` table must be provisioned first). See
[`docs/FINAL-REPORT.md`](docs/FINAL-REPORT.md).

## Run it

Prerequisites: .NET SDK 10 (`global.json`) and the **CPython 3.12 oracle environment** (the product runs on 3.12; other interpreters are refused):

```pwsh
uv python install 3.12
uv venv --python 3.12 C:\Projects\py312-oracle\.venv
$env:TCC_PYTHON = 'C:\Projects\py312-oracle\.venv\Scripts\python.exe'   # required, no default
```

```pwsh
cd dotnet
dotnet build TaxCredit.slnx -warnaserror
dotnet format TaxCredit.slnx --verify-no-changes
dotnet test TaxCredit.slnx                       # goldens, 20,000-scenario fuzz, architecture rules, unit tests
```

`TCC_PYTHON` has no default. The tests run `python --version` once and fail unless it is 3.12; the goldens' meta lines
are asserted to say 3.12 as well. Details and every gate command: [`../parity/README.md`](../parity/README.md).

### Parity harness

| Command | What it does |
|---|---|
| `python parity/export_primitives.py [--check]` | numeric, text and date primitive vectors (about 399k) |
| `python parity/export_goldens.py [--check]` | runs the production engine over the scenario matrix (3,939 scenarios); `--check` fails if the goldens are stale |
| `python parity/gen_unicode_tables.py` | regenerates `PyUnicodeTables.g.cs` from the oracle (Unicode 15.0) |
| `python parity/export_version_sensitive.py --py314 PATH` | the 410 vectors where 3.12 and 3.14 differ, with both answers |
| `python parity/engine_cli.py` | JSON Lines engine, used by the fuzzer |
| `python parity/bench_python.py` | Python side of the micro-benchmark |

Environment knobs for the .NET tests: `TCC_FUZZ_N` (default 20000), `TCC_FUZZ_SEED`, `TCC_FUZZ_PARALLEL` (4),
`TCC_PYTHON`, `TCC_RUN_MUTATION_TESTS=1` (builds four mutated copies and requires the harness to fail on each),
`TCC_RUN_BENCH=1` (use `-c Release`).

A fuzz mismatch is minimised (rows are shrunk while it still fails), saved under `parity/goldens/regressions/`, and
replayed by `Saved_regression_goldens_still_agree_with_the_python_engine`.

## Rules

Dependencies point inward; Domain is the BCL only; warnings are errors; XML docs on every public member of production
code; no `Math.Round`, `(decimal)someDouble`, culture-sensitive string operations or unstable sorts where Python semantics
differ. See [ADR 0001](docs/adr/0001-solution-layout-and-dependency-rules.md) and [ADR 0002](docs/adr/0002-coding-standards.md).

### Domain slice harness

Every ported family has a Python exporter (`parity/export_<family>.py [--check]`) that runs the production functions and writes
`parity/goldens/<family>.jsonl.gz`, a C# replay test comparing bit for bit, and mutation self-tests in
`MutationSelfTests`. Extra gates: per-family differential fuzz (`FamilyFuzzTests`, N = 20,000 per family, `TCC_FUZZ_N` /
`TCC_FUZZ_SEED`), and the capstone (`export_gold_payload.py` against `ClientCalculationParityTests`: every row of the seven
`tcc_gold` tables). Regenerate the port map with `python parity/port_map.py`. Mutation subsets:
`TCC_RUN_MUTATION_TESTS=1 TCC_MUTATION_FILTER=<text> TCC_MUTATION_TEST_FILTER=<xunit filter>` (a full pass is slow).
Rule files are read from `backend/rules` through `RulePackOptions` and are never copied.