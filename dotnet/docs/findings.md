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
