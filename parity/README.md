# parity/: the Python side of the .NET parity harness

New files only; the production Python is never modified. These scripts produce what the C# port is judged against.

## The oracle is CPython 3.12

The product runs on Python 3.12 (App Service for the API, worker and gateway; CI), so 3.12 behaviour is the
specification. Every script here refuses to run on another interpreter (`oracle.py`). Create the environment once; the
engine needs only the standard library:

```pwsh
uv python install 3.12
uv venv --python 3.12 C:\Projects\py312-oracle\.venv
C:\Projects\py312-oracle\.venv\Scripts\python.exe --version     # Python 3.12.x
```

`--allow-other-python` exists for exploration only: output is stamped `allow_other_python` in its meta line and the .NET
tests reject it. Every golden records the interpreter in its meta line, and the .NET tests assert `3.12.x` on load.

## Scripts (run with the 3.12 interpreter)

| Script | Output | Notes |
|---|---|---|
| `export_primitives.py [--check]` | `goldens/primitives.jsonl.gz` (398,980 vectors, gate G1) | seeded; `--check` fails if stale |
| `export_goldens.py [--check]` | `goldens/engine.jsonl.gz` (3,939 scenarios) and `datasets.jsonl.gz` (gate G2) | runs the production engine |
| `gen_unicode_tables.py` | `dotnet/src/TaxCredit.Domain/Numerics/PyUnicodeTables.g.cs` | Unicode 15.0 tables of CPython 3.12 |
| `export_version_sensitive.py --py314 PATH` | `goldens/version-sensitive.jsonl.gz` | the 410 vectors where 3.12 and 3.14 differ, both answers kept as data |
| `engine_cli.py` | JSON Lines on stdin/stdout | the oracle for the C# differential fuzzer (gate G3) |
| `probe_hash_seed.py` | digest | engine output across `PYTHONHASHSEED` values |
| `bench_python.py` | timings | Python side of the micro-benchmark |

## Running the gates

```pwsh
$env:ORACLE_PYTHON = 'C:\Projects\py312-oracle\.venv\Scripts\python.exe'   # required; there is no default
cd dotnet
dotnet test TaxCredit.slnx                                              # G1, G2, version-sensitive facts, G3 at N=20,000
$env:FUZZ_N=500000; $env:FUZZ_SEED=7; dotnet test tests\TaxCredit.Parity.Tests --filter Random_scenarios
$env:MUTATION_RUN=1; dotnet test tests\TaxCredit.Parity.Tests --filter MutationSelfTests
```

Regenerate everything after an engine change (3.12 only), then commit the new goldens:

```pwsh
$py = 'C:\Projects\py312-oracle\.venv\Scripts\python.exe'
& $py parity\export_primitives.py ; & $py parity\export_goldens.py ; & $py parity\gen_unicode_tables.py
& $py parity\export_version_sensitive.py --py314 C:\Projects\GitHub\tax-credit-copilot-public\.venv\Scripts\python.exe
```

Moving the oracle to a later interpreter is a deliberate step: the failing `VersionSensitiveTests` state what the new
interpreter would answer.
