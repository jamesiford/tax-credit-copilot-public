# Parity report

Python (CPython 3.14.2, production engine in `backend/domain/calculation`) is the oracle. Branch `dotnet/spike`.

## Gate G1: numeric primitives. PASSED

`parity/goldens/primitives.jsonl.gz`: 398,980 seeded vectors (20.8 MB) replayed by `PrimitiveParityTests` and
`PrimitiveParityOrderingTests`: round (n = 0..6, negative n, adversarial ties), Decimal quantize half-up/half-even
(including `InvalidOperation`), repr, float and int parsing, `//` `%` `divmod`, `int` `floor` `ceil`, `sum`, dates,
sort stability, min/max ties, string comparison, and every one of the 1.1 million code points for `upper()` and `isspace()`.
Result: **100% identical** (doubles compared by IEEE-754 bits; all NaNs equal, see findings T-12).
Mutation self-tests show `Math.Round`, `Math.Floor(a / b)`, `(decimal)x`, `string.CompareOrdinal` and a naive `+=` sum diverge.

## Gate G2: engine goldens. PASSED

`parity/export_goldens.py` ran the production engine over the matrix in `parity/matrix.py`
(`--check` mode fails when the goldens are stale; byte-identical across `PYTHONHASHSEED` values).

| Item | Count |
|---|---|
| Scenarios | 3,939 (3,747 results, 192 expected Python exceptions) |
| Datasets | 29 (committed synthetic CSV of 9,477 rows, 8 derived variants, 20 edge datasets) |
| `pay_period` / `min_max` runs | 612 / 651 |
| Other ops | preprocess 67, average_headcount 248, rows_for_state_year 200, first_measurable_month 47, unreachable_months 23, apply_pay_code_policy 29, row_states 24, states_present 24, fiscal 62, floors 50, helper 1,902 |
| Mismatches (final run) | **0** |

Coverage: all nine programme packs (GA 2019-2026, others 2023-2024, plus the flat legacy resolution) on both methods;
calendar, March year-end, 53-week and stub-opening windows; pay-code include/exclude policies; part-time bands with
int and float floors; entity and granularity variants; measuring-date variants (including Unicode digits); methodology
overrides; empty, null and empty-string cells; missing keys (`KeyError`); bad dates (`ValueError`); half-cent ties;
duplicate collapse; negative adjustments; leap days and month ends; extreme values (`InvalidOperation`); `None` units
(`TypeError`); 700 seeded random runs.

Compared per scenario: the result tree (types, key order, double bits), the calculation trail including its SHA-256
evidence hash, a separate SHA-256 over the IEEE-754 bytes of every float, and, for failing scenarios, the Python
exception type name.

### Mismatches found and fixed on the way to zero

| Divergence | Cause | Fix |
|---|---|---|
| 1,160 helper results printed `2023.0` where Python had `2023` | C# `?:` promoted a `long` to `double` (T-14) | cast to `object` |
| `TypeError` scenarios surfaced as `InvalidOperationException` | `List.Sort` wraps comparer exceptions (T-15) | unwrap in `PySort` |
| 382 `sum` vectors off in the last bit | Python 3.14 compensates ints after the first float too (T-04) | `PySum` fixed (G1) |
| 9 `isocalendar` vectors in the wrong ISO year | truncating division (T-07) | floor logic (G1) |

No tolerance was introduced. The only relaxation is NaN equality (T-12).

## Gate G3: differential fuzzing. PASSED

`DifferentialFuzzTests`: C# generates N seeded scenarios (SplitMix64, independent of the Python generator), sends them in
batches of 250 to `parity/engine_cli.py` (a fresh Python process, hence a fresh string-hash seed, per batch), runs the C#
engine and compares result, trail (including the evidence hash), float-bit digest and exception type. About 4% of scenarios
carry one corrupted row (missing key, garbage date, non-numeric hours, `None` unit, overflowing hours, inverted period).
A mismatch is minimised by row-wise delta debugging, saved under `parity/goldens/regressions/`, and fails the test.

| Run | N | Seed | Python raised | Operations | Mismatches |
|---|---|---|---|---|---|
| gate | 20,000 | 20261114 | 266 | pay_period 9,113 / min_max 8,898 / average_headcount 997 / preprocess 992 | **0** (36 s) |
| overnight-style | 500,000 | 7 | 6,735 | pay_period 224,505 / min_max 225,357 / average_headcount 25,090 / preprocess 25,048 | **0** (13 min) |

### Mutation self-test (`TCC_RUN_MUTATION_TESTS=1`)

Each defect is applied to a scratch copy of the Domain sources, the copy is built, and the golden and fuzz tests must fail:

| Mutation | Outcome |
|---|---|
| `PyRoundingMode.HalfUp` becomes `HalfEven` (rounding) | caught (4 failing summaries) |
| `avgHours + 1e-9 >= minHours` becomes `>` (comparison) | caught (1) |
| `PySort` tie-break reversed (sort) | caught (3) |
