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

## DS2 foundations (gate: met for PyJson)

- `PyDict` moved to `Numerics` with a key index and Python dict semantics (`Set` keeps first position, last value; `Add` rejects duplicates).
- `PyJson.Loads`: port of CPython's C scanner (`Modules/_json.c`): ints are `long`/`BigInteger` (one CLR type per magnitude), floats `double`, `NaN`/`Infinity`/`-Infinity` accepted, duplicate keys last-wins-first-position, 4300-digit int limit as `ValueError`, BOM message, and `JSONDecodeError` messages with line/column/char offsets counted in code points.
- `PyJson.Dumps(value, sortKeys, compact)` added beside the canonical overload; `BigInteger` supported.
- `parity/export_json.py` -> `goldens/json.jsonl.gz` (about 6,200 vectors: handcrafted edge cases, all 38 `backend/rules` files, seeded mutations). C# replays `Loads` then both `Dumps` configurations, and error type+message, bit for bit: 0 mismatches. Mutation self-test (`IntsAsFloats`) proves the int/float comparison can fail.
- Trap found while porting: `cond ? long : BigInteger` in C# silently converts the long to BigInteger (conditional type). Cast to `object`.
- Not ported: `Counter`/`defaultdict` helpers; insertion-ordered `PyDict` suffices until DS3 shows otherwise.

## DS3 proximity family (`domain/calculation/proximity.py`)

- **Ported:** every function in the module: `_rate`, `assess_employee`, `fragility`, `near_miss_cohort`, `fragile_cohort`, `band_curve`, `rest_of_year`; constants `PLAUSIBLE_WEEKLY_HOURS`, `BAND_CURVE_HOURS`. C# is `Proximity` (partial static class) in `Calculation/Proximity.cs`, `ProximityCohorts.cs`, `ProximityRestOfYear.cs`, with `ProximityCoerce.cs` for the Python conversions (`float(x or 0.0)`, `int()`, `str()`, truthiness, exact int/int division).
- **Representation:** rows, results and `population` are `PyDict` trees (key order, int-versus-float values and missing keys are the contract); `within_weekly_hours` and `bands` are `PyNumber` because the call echoes the argument with its type (`5` versus `5.0`); `limit` is `long?`.
- **Golden:** `parity/export_proximity.py` -> `goldens/proximity.jsonl.gz`, 11,623 calls (assess_employee 2,358, fragility 2,358, `_rate` 37, near_miss_cohort 1,509, fragile_cohort 1,509, band_curve 413, rest_of_year 3,439), 957 of them recording an exception type+message. Inputs: every row and period the two Python test modules build (including the 606-row hostile hours/rate probe), boundaries one ulp either side of both floors, half-cent ties, missing/None/zero/negative/NaN/inf/huge/BigInteger/string/list fields, every recorded-verdict variant, fractional weights, tie-heavy id sets (`"10"` versus `"9"`, ints, None, non-BMP), `population` overrides (missing keys, floats, strings, None `failure_modes`), `limit` -3..1000, `decimals` -2..4, weekly/biweekly/semi-monthly/monthly cadences with and without pay-date lags, date objects versus ISO strings versus malformed dates, and 60 employees of the committed synthetic payroll.
- **Test:** `ProximityParityTests` compares by type, key order, double bits and exception type+message. Result: 11,623 / 11,623 identical. In-process perturbation test (ulp bump, int-as-float, bool flip, list reversal, key reorder) proves the comparison can fail. Seven mutations added to `MutationSelfTests` (banker's rounding, `>=` to `>`, recorded verdict ignored, `max` to `min` on the way in, `min` to `max` on the way out, id tie-break reversed, `population` ignored): all caught.
- **Decisions:** `rest_of_year` rounds up with `math.ceil(x * step - 1e-9) / step`; the int/int division is exact (`ExactTrueDiv`) instead of `(double)n / step`. `rest_of_year`'s sums go through `PySum` (3.12 compensated). `jobs_at_risk` sums weights with `PySum` too. The recorded verdict is read with Python truthiness (`bool(recorded)`), so `0`, `""` and `[]` mean "not eligible" while only `None` means "no verdict".
- **Fix outside the family:** `PyDate.FromIsoFormat` now raises the date constructor's messages for impossible calendar components (finding P-03); the primitive goldens still pass.
- **Not ported / limits:** `rest_of_year` with `decimals` outside 0..18 (P-05); `datetime` arguments for dates (they would raise `TypeError` on comparison in Python; not exported); `str()` of non-scalar employee ids; `str.lower()` of non-ASCII program codes (refused with `PyUnsupportedException`); a zero-length pay period (infinite loop in Python, not exported).
- **Size:** functions `AssessEmployee`, `Fragility`, `RestOfYear` exceed 40 lines because each ends in a 20-key result literal whose order is the contract; the computations in them are split out (`AdditionalHours`, `ClosedPeriods`, `PaymentLags`, `CountRemainingPeriods`, `OpenState`).
- **Trap met again:** `cond ? (long)i : i` converts the long to `BigInteger` (see DS2); `Normalise` returns through an `if` and carries a `CA1859` pragma with the reason.
- **Observation:** one run of the whole Parity suite failed once (1 of 70) while the same suite passed on the three reruns, including with the proximity tests alone; the failing test was not captured. Not investigated further.