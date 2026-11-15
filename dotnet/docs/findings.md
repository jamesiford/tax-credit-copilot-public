# Findings

Anything that cannot be matched, anything in the Python engine that looks wrong (ported as is), and every
Python-to-C# trap found. The Python engine is the oracle: nothing here has been "fixed" in C#.

## Python-to-C# traps

| Id | Python | Trap in C# | Handling |
|----|--------|-----------|----------|
| T-01 | `round(x, n)` | `Math.Round(double, int)` scales in floating point and mis-rounds some inputs (e.g. values whose scaled product lands on a tie); Python rounds the exact binary value half-even. | `PyRound` decomposes the double to `m*2^e`, scales and rounds with `BigInteger`, re-parses the decimal with the correctly rounded `double.Parse`. 100% vector match. Mutation test shows `Math.Round` diverges. |
| T-02 | `Decimal(str(x)).quantize(...)` | `(decimal)x` keeps ~15 significant digits; `System.Decimal` cannot hold `Decimal('1E+22')`, trailing-zero exponents, or raise `InvalidOperation` for > 28 digits (e.g. `1e300`). | `PyDecimal` (sign, `BigInteger` coefficient, exponent) with the 28-digit context check. Mutation test shows `(decimal)x` diverges. |
| T-03 | `str(float)` / `repr` | `double.ToString("R")` gives the same shortest digits but a different layout (`1E-05`, `1E+16`, no `.0`). | `PyFloat.Repr` takes the digits and re-lays them out with CPython's rule (exponent form when the decimal point is outside (-4, 16]). |
| T-04 | `sum(list)` | Since 3.12, `sum()` of floats uses Neumaier compensation; **in 3.14 the compensation also covers ints that follow the first float**. A `+=` loop, or LINQ `Sum`, differs on a measurable share of vectors. | `PySum` mirrors the algorithm. First implementation added trailing ints without compensation and failed 382 of 12,010 vectors; fixed after checking in Python. |
| T-05 | `a // b`, `a % b` | Integers: C# truncates, Python floors. Floats: `Math.Floor(a / b)` is not CPython's `//`, which derives the quotient from `fmod`. | `PyArith.FloorDiv/Mod/DivMod` port `float_divmod`. Mutation test shows `Math.Floor(a / b)` diverges. |
| T-06 | `a / 0.0` | C# returns infinity/NaN, Python raises `ZeroDivisionError`. | `PyArith.TrueDiv` raises `PyZeroDivisionError`. |
| T-07 | `date` arithmetic | `DateOnly.AddDays` throws `ArgumentOutOfRangeException`; Python raises `OverflowError` / `ValueError`. ISO week date parsing needed floor division (a truncating `/` put early-January dates in the wrong ISO year). | `PyDate` maps to `PyValueError` / `PyOverflowError`; `IsoCalendar` fixed after a vector failure. |
| T-08 | `min` / `max` | `Math.Min(-0.0, 0.0)` returns `-0.0`; Python returns the first of equal elements. NaN handling follows `<` comparisons. | `PyArith.Min/Max` use Python's "first unless strictly better" rule. |
| T-09 | String ordering | `string.CompareOrdinal` orders UTF-16 code units, so U+10000 sorts before U+FFFF; Python orders by code point. | `PyStr.Compare`. Trap demonstrated by a test. |
| T-10 | `str.upper()` / `strip()` | `ToUpperInvariant` is 1:1 (`"ß".upper()` is `"SS"` in Python); `Trim()` misses U+001C..U+001F. | Generated mapping tables from the oracle (`PyUnicodeTables`, 1,552 upper mappings, 29 whitespace code points), verified for all 1.1M code points. |
| T-11 | `float(str)` | Python accepts underscores, Unicode digits/whitespace and `infinity`; `double.Parse` differs. | `PyFloat.TryParse` validates with Python's grammar first, then uses the correctly rounded `double.Parse`. |
| T-12 | NaN | .NET `double.NaN` has the sign bit set, Python's does not. | `PyFloat.SameBits` treats all NaNs as equal. This is the only relaxation of bit equality in the harness; Python cannot observe NaN sign through `repr` or arithmetic. **Flagged for review (NEEDS-HUMAN-REVIEW) although low risk.** |
| T-13 | Oracle version | The brief assumed a 3.12-era interpreter; the venv is **CPython 3.14.2** (Unicode 16.0.0). Behaviour such as `sum()` int compensation (T-04) is version dependent. | Every golden records the Python version; the .NET port targets 3.14 behaviour. Production must pin the same interpreter to keep the oracle meaningful. |

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
