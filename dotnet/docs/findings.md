# Findings

Anything that cannot be matched, anything in the Python engine that looks wrong (ported as is), and every
Python-to-C# trap found. The Python engine is the oracle: nothing here has been "fixed" in C#.

## Python-to-C# traps

| Id | Python | Trap in C# | Handling |
|----|--------|-----------|----------|
| T-01 | `round(x, n)` | `Math.Round(double, int)` scales in floating point and mis-rounds some inputs (e.g. values whose scaled product lands on a tie); Python rounds the exact binary value half-even. | `PyRound` decomposes the double to `m*2^e`, scales and rounds with `BigInteger`, re-parses the decimal with the correctly rounded `double.Parse`. 100% vector match. Mutation test shows `Math.Round` diverges. |
| T-02 | `Decimal(str(x)).quantize(...)` | `(decimal)x` keeps ~15 significant digits; `System.Decimal` cannot hold `Decimal('1E+22')`, trailing-zero exponents, or raise `InvalidOperation` for > 28 digits (e.g. `1e300`). | `PyDecimal` (sign, `BigInteger` coefficient, exponent) with the 28-digit context check. Mutation test shows `(decimal)x` diverges. |
| T-03 | `str(float)` / `repr` | `double.ToString("R")` gives the same shortest digits but a different layout (`1E-05`, `1E+16`, no `.0`). | `PyFloat.Repr` takes the digits and re-lays them out with CPython's rule (exponent form when the decimal point is outside (-4, 16]). |
| T-04 | `sum(list)` | CPython 3.12 `sum()` of floats uses Neumaier compensation, but an **int that follows the first float is added without compensation** (`f += (double)value`). CPython 3.14 compensates those ints too, so the two interpreters differ in the last bit on 382 of the exported vectors. A `+=` loop, or LINQ `Sum`, differs on a measurable share of vectors. | `PySum` implements **3.12 exactly** and has no switch for 3.14. The first implementation was written against 3.14 vectors (compensated ints) and is replaced; the 3.12 behaviour was confirmed by the 3.12 vectors (the earlier uncompensated version failed 382 of 12,010 vectors against 3.14, which is the same set). The 382 vectors are kept with both answers in `parity/goldens/version-sensitive.jsonl.gz`, and `VersionSensitiveTests` states the 3.14 value in its failure message. |
| T-05 | `a // b`, `a % b` | Integers: C# truncates, Python floors. Floats: `Math.Floor(a / b)` is not CPython's `//`, which derives the quotient from `fmod`. | `PyArith.FloorDiv/Mod/DivMod` port `float_divmod`. Mutation test shows `Math.Floor(a / b)` diverges. |
| T-06 | `a / 0.0` | C# returns infinity/NaN, Python raises `ZeroDivisionError`. | `PyArith.TrueDiv` raises `PyZeroDivisionError`. |
| T-07 | `date` arithmetic | `DateOnly.AddDays` throws `ArgumentOutOfRangeException`; Python raises `OverflowError` / `ValueError`. ISO week date parsing needed floor division (a truncating `/` put early-January dates in the wrong ISO year). | `PyDate` maps to `PyValueError` / `PyOverflowError`; `IsoCalendar` fixed after a vector failure. |
| T-08 | `min` / `max` | `Math.Min(-0.0, 0.0)` returns `-0.0`; Python returns the first of equal elements. NaN handling follows `<` comparisons. | `PyArith.Min/Max` use Python's "first unless strictly better" rule. |
| T-09 | String ordering | `string.CompareOrdinal` orders UTF-16 code units, so U+10000 sorts before U+FFFF; Python orders by code point. | `PyStr.Compare`. Trap demonstrated by a test. |
| T-10 | `str.upper()` / `strip()` | `ToUpperInvariant` is 1:1 (`"ß".upper()` is `"SS"` in Python); `Trim()` misses U+001C..U+001F. | Generated mapping tables from the oracle (`PyUnicodeTables`, 1,552 upper mappings, 29 whitespace code points), verified for all 1.1M code points. |
| T-11 | `float(str)` | Python accepts underscores, Unicode digits/whitespace and `infinity`; `double.Parse` differs. | `PyFloat.TryParse` validates with Python's grammar first, then uses the correctly rounded `double.Parse`. |
| T-12 | NaN | .NET `double.NaN` has the sign bit set, Python's does not. | `PyFloat.SameBits` treats all NaNs as equal. This is the only relaxation of bit equality in the harness; Python cannot observe NaN sign through `repr` or arithmetic. **Flagged for review (NEEDS-HUMAN-REVIEW) although low risk.** |
| T-13 | Oracle version | **The oracle is CPython 3.12**, the interpreter the product runs on (App Service for the API, worker and gateway; CI). The first spike run used 3.14.2 by accident (the main checkout's venv), and the oracle turned out not to be interpreter-neutral (T-04, T-19). | Enforced in code: every `parity/*.py` script refuses another interpreter (`parity/oracle.py`; `--allow-other-python` stamps the output and the tests reject it); the .NET `PythonSession` reads `TCC_PYTHON`, has **no default**, runs `python --version` once and fails the run unless it is 3.12; each golden's meta line records the version and is asserted on load. Engine goldens and datasets are byte-identical on 3.12 and 3.14 apart from that meta field. |
| T-19 | Unicode database version | `str.upper()` goes through the Unicode database: CPython 3.12 ships **Unicode 15.0**, 3.14 ships **16.0**. Unicode 16 added case pairs, so 27 code points that upper-case to themselves on 3.12 map elsewhere on 3.14: U+019B, U+0264, U+1C8A, U+A7CD, U+A7DB and the Garay letters U+10D70..U+10D85. `PyUnicodeTables` is generated from 3.12 (Unicode 15.0, 1,525 case keys, 29 whitespace code points) and verified for all 1.1M code points. | The 28 version-sensitive string vectors: 1 `case_table` (the table above), 1 `unicode_version` (`15.0.0` vs `16.0.0`) and 26 `str` vectors. All 26 differ only in the `upper` field and each contains U+019B (to U+A7DC on 3.14) or U+0264 (to U+A7CB); the vectors are listed with both answers in the version-sensitive golden. The engine uses `upper()` only on state codes, so no engine golden or fuzz result changes. |

## Scope decisions

- Only `str.upper()`, `strip()`, `isspace()` and code point comparison are ported from `str`. `lower()`/`casefold()`/`title()` (context sensitive, final sigma) are not used by the engine and are deliberately not ported.
- `datetime.fromisoformat` and `strptime` are not ported: the engine only calls `date.fromisoformat(str(s)[:10])`.
- `Decimal` NaN/Infinity are not ported (the engine feeds `str(float)` of finite averages only).
- `sum()` of ints beyond `long` is not ported.

## Additional traps found while porting the engine (S4)

| Id | Python | Trap in C# | Handling |
|----|--------|-----------|----------|
| T-14 | `x if cond else y` with an int and a float | C# `cond ? longValue : doubleValue` silently converts the long to double, so the JSON tree said `1.0` where Python had `1`. The first golden run failed 1,160 helper scenarios on this alone. | Casts to `object` in both branches (`TrailValues.Of`, `JsonTree.Read`); the int/float distinction is carried by `PyNumber`/`RowCell` and checked by the harness. |
| T-15 | exception from a `sorted()` key comparison | `List<T>.Sort` wraps a comparer's exception in `InvalidOperationException`. Python raises the original `TypeError`. | `PySort.Sorted` unwraps and rethrows the Python-style exception. |
| T-16 | `sorted()` / `dict` with `None` keys | C# dictionaries reject null keys; Python orders `None` against `str` with a `TypeError` (even `None < None`). | `NullableKey` wrapper for dictionaries, `KeyOrder` comparer that raises `PyTypeError`; tuple keys skip equal components first, as Python does. |
| T-17 | `json.dumps(sort_keys=True)` for the evidence hash | `System.Text.Json` escapes and formats differently, so the SHA-256 would differ. | `PyJson.Dumps` reproduces `ensure_ascii` escaping (including DEL as `\u007f`) and `repr` floats; all 3,939 hashes match. |
| T-18 | `str(row.get("Pay_Code", "Regular"))` | A present-but-`None` pay code becomes the string `"None"`; an absent key becomes `"Regular"`. | `RowCell` keeps Absent / Null / Text / Int / Float apart. |

## Engine observations (ported as is, not fixed)

- **F-01 `pt_weight` truthiness.** `pack.pt_weight and ...` means a part-time weight of `0` or `0.0` disables the band silently. Mirrored.
- **F-02 set iteration order.** `weeks = sum(... for pps, ppe in periods)` iterates a Python `set` of string tuples, so the summation order depends on the per-process hash seed. The exporter was run under three different `PYTHONHASHSEED` values (5, 11, 12) and produced byte-identical goldens, `probe_hash_seed.py` gave one digest for six seeds (0, 1, 2, 3, 42, 999), and the fuzz runs used a fresh random seed per batch (2,080 Python processes in the 520,000-scenario runs). Neumaier compensation makes the sum order-insensitive in practice (the terms are `k/7.0` with small `k`). **Latent, benign non-determinism; C# sums in first-seen order.** The 20,000-scenario fuzz (S5) runs Python with a fresh random seed per process and is the stronger test of this claim.
- **F-03 `measuring_date` parsing.** `int(measuring_date)` accepts Unicode digits, underscores and surrounding whitespace (`"١٥"`, `"1_5"`, `" 20 "`), so a malformed pack value can be silently honoured. Mirrored via `PyInt`.
- **F-04 `unreachable_months` / `first_measurable_month` re-parse every row** on each call; harmless, but quadratic with many months.

## Scope decisions (S4)

- Rows carry only the ten columns the outputs use (`Employee_ID`, `Worksite_ID`, `Entity_FEIN`, `Pay_Period_Start/End`, `Pay_Date`, `Hours_Worked`, `Gross_Wages`, `Pay_Code`, `Work_State`). Extra columns are not carried; both sides of the harness project to them.
- Identifier and date cells are modelled as string, `None` or absent (the lakehouse adapter emits ISO strings: `data/source/to_bcs.py`). A numeric identifier or date cell raises `PyUnsupportedException` rather than diverging.
- `hours`/`wages` cells may be `None`, `""`, numeric text, int or float; NaN and infinities in inputs are not modelled (Python `Decimal('NaN')` quantizes quietly, which the port does not reproduce; infinities raise `InvalidOperation` in both).
- Not ported (not needed by the two run methods): `employee_derivation`, `proximity`, `performance`, `reconciliation`, `rollups`, `OneZeroMethodology.from_pack_json` (S6).
- Goldens store floats as JSON numbers written with `repr` (lossless) instead of repr+hex per value, to keep the files to about 30 MB. Bit equality does not depend on the text: every response also carries a SHA-256 over the IEEE-754 bytes of every float in traversal order, and the C# side recomputes it from its own results.

## Proximity family (DS3: `domain/calculation/proximity.py`)

| Id | Python | Trap / behaviour | Handling |
|----|--------|------------------|----------|
| P-01 | `float(average.get("weight") or 1.0)` in `fragility` | A part-time weight of `0` or `0.0` is falsy, so it reads as a FULL job (1.0). `jobs_at_risk` then counts a zero-weight employee as one job. Same `or` shape as F-01. | Mirrored (`Fragility`), covered by the weight scenarios. |
| P-02 | `modes[row["failure_mode"]] = modes.get(...) + 1` in `near_miss_cohort` | A recorded-ineligible row that clears both floors has `failure_mode == "none"`, which appends a fourth key to `failure_modes` (after `both`). Consumers expecting three keys see four. | Mirrored with `PyDict.Set`. |
| P-03 | `date.fromisoformat` on `str(value)[:10]` | A well-formed calendar date with an impossible month or day raises the date constructor's message (`month must be in 1..12`, `day is out of range for month`, `year 0 is out of range`), not `Invalid isoformat string`. The spike's `PyDate.FromIsoFormat` used the latter for everything. Week dates keep `Invalid isoformat string`. | Fixed in `PyDate.FromIsoFormat` (8 golden calls found it). |
| P-04 | `while last_end + step_days * (n + 1) + lag <= end` in `rest_of_year` | A period whose end is before its start gives a zero or negative step. Zero never terminates; negative runs about 740,000 iterations until `OverflowError: date value out of range`. Not reachable from payroll, reachable from bad input. | Negative step mirrored (one golden call); zero step is deliberately not exported. |
| P-05 | `step = 10 ** decimals` in `rest_of_year` | A negative `decimals` makes `step` a float (`0.01`), so the ceil-and-divide switches from int/int to float/float. | Not ported: `PyUnsupportedException` for `decimals` outside 0..18. `assess_employee` and the cohorts do accept negative `decimals`. |
| P-06 | `math.ceil(x) / step` (int / int) | Python's int true division is correctly rounded for any size; `(double)n / step` double-rounds above 2^53. | `ProximityCoerce.ExactTrueDiv` (BigInteger quotient, one half-even rounding). Also used for `float(huge_int)`, because `(double)BigInteger` is not trusted to round. |
| P-07 | `_round_half_up(nan)` | `Decimal('nan').quantize(...)` returns NaN quietly; `inf` raises `InvalidOperation` with message `[<class 'decimal.InvalidOperation'>]`. | `ProximityCoerce.RoundHalfUp` wraps the shared helper: NaN passes through, the message is Python's. |
| P-08 | `str(KeyError('x'))` | The message is the key's repr (`'evaluated'`), not the key. `PyKeyError` stores its argument as the message. | `ProximityCoerce.Missing` passes the repr. |
| P-10 | `near_miss_cohort(..., limit=-3)` | `reachable[:limit] if limit else reachable` slices from the end for a negative limit (drops the last 3 rather than returning 3). | Mirrored (`Take`). |