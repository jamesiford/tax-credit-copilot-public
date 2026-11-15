# Spike log

Running log of decisions, findings and gate results for the .NET parity spike (branch `dotnet/spike`).

## Preflight (2026-11-14)

- Worktree `C:\Projects\GitHub\tcc-dotnet-spike` created from `main` (`f9da416`) on branch `dotnet/spike`. The main checkout was not touched.
- Oracle interpreter: `C:\Projects\GitHub\tax-credit-copilot-public\.venv\Scripts\python.exe` = **CPython 3.14.2** (Unicode 16.0.0), run with cwd `<worktree>\backend` and `PYTHONUTF8=1`.
- Import check: `python -c "import domain, sys; print(domain.__file__)"` printed `C:\Projects\GitHub\tcc-dotnet-spike\backend\domain\__init__.py` (inside the worktree, so no editable install is shadowing it).
- Python baseline (`test_onezero`, `test_engine_parity_synthetic`, `test_average_headcount_window`, `test_fiscal_window`, `test_credit_math`, `test_certified_figures_contract`): **82 passed in 5.46 s**.
- Toolchain: SDKs 8.0.428, 10.0.404, 11.0.100 installed; `global.json` pins 10.0.404 (rollForward latestFeature); projects target `net10.0`.
- NuGet: nuget.org source is disabled on this machine; the `azure-default` feed proxy serves restores (xunit 2.9.3 restored fine).

## Stage S1: numeric primitives lab

- `parity/export_primitives.py` writes `parity/goldens/primitives.jsonl.gz`: 398,938 vectors, 20.8 MB, seeded (`20261114`), byte-identical on re-run (gzip mtime fixed). Doubles are stored as repr, `float.hex` and IEEE bits.
- C# compatibility layer: `TaxCredit.Domain.Numerics` (`PyRound`, `PyDecimal`, `PyFloat`, `PyArith`, `PySum`, `PySort`, `PyStr`, `PyDate`, generated `PyUnicodeTables`).
- **Gate G1: PASSED. 36/36 tests, every vector bit-identical** (second run after two fixes, see findings.md traps T-04 and T-07).
- Mutation self-test (`Built_in_dotnet_calls_diverge_from_python_so_the_harness_can_fail`): `Math.Round`, `Math.Floor(a/b)` and `(decimal)x` each diverge on a measurable number of vectors, so the comparison can fail.

## Stage S2: skeleton and standards

- Solution \dotnet/TaxCredit.slnx\ with six src projects and three test projects, central package management, \
et10.0\, \TreatWarningsAsErrors\, analyzers at \latest-recommended\, XML docs required on production public members.
- \dotnet build -warnaserror\: 0 warnings, 0 errors. \dotnet format --verify-no-changes\: clean. Tests: 13 architecture + 18 domain + 36 parity, all green.
- Eight ADRs in \dotnet/docs/adr\. Licences were re-read from the upstream repositories (MediatR = RPL 1.5 / commercial, FluentAssertions = Xceed community licence, xunit = Apache-2.0, Mediator by martinothamar = MIT, NetArchTest = MIT but stale, ArchUnitNET = Apache-2.0).
- Environment notes: OpenTelemetry 1.12.0 was rejected by NuGet audit (NU1902, moderate vulnerability) and bumped to 1.20.x; Aspire 13.6.5 needs \ASPIRE010\ suppressed (no CLI bundle).


## Stages S3 and S4: goldens and engine port

- parity/export_goldens.py + matrix.py + scenarios.py + engine_io.py: 3,939 scenarios, goldens 9.5 MB (engine) + 0.9 MB (datasets). --check passes under PYTHONHASHSEED 5, 11, 12.
- Domain/Calculation: ~3,500 lines incl. Numerics. **Gate G2: PASSED, 0 mismatches** (50 parity tests, 18 domain, 13 architecture all green).
- See parity-report.md and findings.md (T-14..T-18, F-01..F-04).


## Stage S5: differential fuzzing

- parity/engine_cli.py, FuzzGenerator/PythonSession/DifferentialFuzzTests, ddmin shrinker, regression goldens folder, mutation self-test (3/3 caught).
- **Gate G3: PASSED.** N=20,000 (seed 20261114): 0 mismatches, 36 s. N=500,000 (seed 7): 0 mismatches, 13 min.
- Benchmarks recorded in SPIKE-REPORT.md (C# 2-4x faster than Python, unoptimised).

## Stage S6

- Not run: RUN_STRETCH_S6 was not set (stretch only). G4 is therefore untested.

## Stage S7

- SPIKE-REPORT.md and dotnet/README.md written. Recommendation: go with conditions.

