using System.Numerics;
using System.Text.Json;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate G1: replays every Python-exported primitive vector (<c>parity/goldens/primitives.jsonl.gz</c>) against the
/// C# compatibility layer. Doubles are compared by IEEE-754 bit pattern (all NaNs equal); everything else exactly.
/// </summary>
public sealed class PrimitiveParityTests
{
    private const string File = "primitives.jsonl.gz";

    private static double Dbl(JsonElement d) => PyFloat.FromBits(d.GetProperty("b").GetInt64());

    private static bool IsDbl(JsonElement e) => e.ValueKind == JsonValueKind.Object && e.TryGetProperty("b", out _);

    private static string? Same(string what, double actual, JsonElement expected) =>
        PyFloat.SameBits(actual, Dbl(expected)) ? null : $"{what}: got {PyFloat.Repr(actual)} ({PyFloat.ToBits(actual):x}) expected {expected.GetProperty("r").GetString()}";

    private static string? Eq<T>(string what, T actual, T expected) =>
        EqualityComparer<T>.Default.Equals(actual, expected) ? null : $"{what}: got '{actual}' expected '{expected}'";

    /// <summary>Runs <paramref name="check"/> over every vector of <paramref name="kind"/> and fails with the first mismatches.</summary>
    internal static int Run(string kind, Func<JsonElement, string?> check)
    {
        var count = 0;
        var failures = new List<string>();
        var failed = 0;
        foreach (var v in GoldenFiles.Read(File, kind))
        {
            count++;
            string? error;
            try
            {
                error = check(v);
            }
            catch (PyException e)
            {
                error = $"unexpected Python-style exception {e.PythonType}: {e.Message}";
            }

            if (error is not null)
            {
                failed++;
                if (failures.Count < 8)
                {
                    failures.Add($"{error}  <= {v.GetRawText()[..Math.Min(220, v.GetRawText().Length)]}");
                }
            }
        }

        Assert.True(count > 0, $"no vectors of kind {kind}");
        Assert.True(failed == 0, $"{failed}/{count} {kind} vectors diverged:\n" + string.Join("\n", failures));
        return count;
    }

    private static string ErrName(Func<BigInteger> f)
    {
        try
        {
            return f().ToString(System.Globalization.CultureInfo.InvariantCulture);
        }
        catch (PyException e)
        {
            return e.PythonType;
        }
    }

    [Fact]
    public void Round_float_ndigits_matches_python_bit_for_bit() =>
        Run("round", v => Same("round", PyRound.Round(Dbl(v.GetProperty("x")), v.GetProperty("n").GetInt32()), v.GetProperty("o")));

    [Fact]
    public void Round_float_to_int_matches_python() =>
        Run("round_int", v => Eq("round(x)", PyRound.RoundToInteger(Dbl(v.GetProperty("x"))).ToString(System.Globalization.CultureInfo.InvariantCulture), v.GetProperty("o").GetString()));

    [Fact]
    public void Round_int_with_negative_ndigits_matches_python() =>
        Run("round_intn", v => Eq("round(int,n)", PyRound.RoundInteger(BigInteger.Parse(v.GetProperty("v").GetRawText(), System.Globalization.CultureInfo.InvariantCulture), v.GetProperty("n").GetInt32()).ToString(System.Globalization.CultureInfo.InvariantCulture), v.GetProperty("o").GetString()));

    [Fact]
    public void Round_float_with_negative_ndigits_matches_python() =>
        Run("round_negn", v => Same("round(x,-n)", PyRound.Round(Dbl(v.GetProperty("x")), v.GetProperty("n").GetInt32()), v.GetProperty("o")));

    [Fact]
    public void Decimal_quantize_matches_python_including_invalid_operation() =>
        Run("quantize", v =>
        {
            var mode = v.GetProperty("mode").GetString() == "half_up" ? PyRoundingMode.HalfUp : PyRoundingMode.HalfEven;
            var expectedText = v.GetProperty("s").GetString()!;
            try
            {
                var q = PyDecimal.FromFloatViaStr(Dbl(v.GetProperty("x"))).Quantize(v.GetProperty("n").GetInt32(), mode);
                return Eq("str", q.ToString(), expectedText) ?? (v.GetProperty("f").ValueKind == JsonValueKind.Null
                    ? "expected InvalidOperation"
                    : Same("float(q)", q.ToDouble(), v.GetProperty("f")));
            }
            catch (PyInvalidOperation)
            {
                return expectedText == "InvalidOperation" ? null : "raised InvalidOperation unexpectedly";
            }
        });

    [Fact]
    public void Decimal_of_str_float_matches_python() =>
        Run("decimal_str", v => Eq("str(Decimal(str(x)))", PyDecimal.FromFloatViaStr(Dbl(v.GetProperty("x"))).ToString(), v.GetProperty("s").GetString()));

    [Fact]
    public void Float_repr_matches_python() =>
        Run("repr", v => Eq("repr", PyFloat.Repr(Dbl(v.GetProperty("x"))), v.GetProperty("s").GetString()) ??
                         Eq("str", PyFloat.Repr(Dbl(v.GetProperty("x"))), v.GetProperty("str").GetString()));

    [Fact]
    public void Float_parse_matches_python() =>
        Run("parse", v =>
        {
            var ok = PyFloat.TryParse(v.GetProperty("t").GetString()!, out var value);
            var expected = v.GetProperty("o");
            if (expected.ValueKind == JsonValueKind.Null)
            {
                return ok ? $"parsed to {PyFloat.Repr(value)} but Python raises ValueError" : null;
            }

            return ok ? Same("float(str)", value, expected) : "rejected but Python accepts";
        });

    [Fact]
    public void Integer_floor_division_and_modulo_match_python() =>
        Run("idivmod", v =>
        {
            var a = BigInteger.Parse(v.GetProperty("a").GetRawText(), System.Globalization.CultureInfo.InvariantCulture);
            var b = BigInteger.Parse(v.GetProperty("b").GetRawText(), System.Globalization.CultureInfo.InvariantCulture);
            return Eq("a//b", ErrName(() => PyArith.FloorDiv(a, b)), v.GetProperty("q").GetString()) ??
                   Eq("a%b", ErrName(() => PyArith.Mod(a, b)), v.GetProperty("r").GetString());
        });

    [Fact]
    public void Float_floor_division_and_modulo_match_python() =>
        Run("fdivmod", v =>
        {
            var a = Dbl(v.GetProperty("a"));
            var b = Dbl(v.GetProperty("b"));
            if (!IsDbl(v.GetProperty("q")))
            {
                return b == 0 ? null : "expected ZeroDivisionError for nonzero divisor?";
            }

            if (b == 0)
            {
                return "Python did not raise for zero divisor";
            }

            var (dq, dr) = PyArith.DivMod(a, b);
            return Same("a//b", PyArith.FloorDiv(a, b), v.GetProperty("q")) ?? Same("a%b", PyArith.Mod(a, b), v.GetProperty("r")) ??
                   Same("divmod q", dq, v.GetProperty("dq")) ?? Same("divmod r", dr, v.GetProperty("dr"));
        });

    [Fact]
    public void Int_with_float_floor_division_matches_python() =>
        Run("mixdiv", v =>
        {
            double a = v.GetProperty("a").GetInt64();
            var b = Dbl(v.GetProperty("b"));
            if (!IsDbl(v.GetProperty("q")))
            {
                return b == 0 ? null : "unexpected error vector";
            }

            return Same("a//b", PyArith.FloorDiv(a, b), v.GetProperty("q")) ?? Same("a%b", PyArith.Mod(a, b), v.GetProperty("r"));
        });

    [Fact]
    public void True_division_raises_on_zero_like_python() =>
        Run("truediv", v =>
        {
            var a = Dbl(v.GetProperty("a"));
            var b = Dbl(v.GetProperty("b"));
            var o = v.GetProperty("o");
            if (!IsDbl(o))
            {
                try
                {
                    PyArith.TrueDiv(a, b);
                    return "expected ZeroDivisionError";
                }
                catch (PyZeroDivisionError)
                {
                    return null;
                }
            }

            return Same("a/b", PyArith.TrueDiv(a, b), o);
        });

    [Theory]
    [InlineData("int")]
    [InlineData("trunc")]
    [InlineData("floor")]
    [InlineData("ceil")]
    public void Float_to_integer_conversions_match_python(string kind) =>
        Run(kind, v =>
        {
            var x = Dbl(v.GetProperty("x"));
            Func<double, BigInteger> f = kind switch
            {
                "floor" => PyArith.Floor,
                "ceil" => PyArith.Ceil,
                _ => PyArith.Truncate,
            };
            return Eq(kind, ErrName(() => f(x)), v.GetProperty("o").GetString());
        });

    [Fact]
    public void Sum_matches_python_compensated_summation() =>
        Run("sum", v =>
        {
            var items = v.GetProperty("xs").EnumerateArray()
                .Select(e => IsDbl(e) ? PyNumber.OfFloat(Dbl(e)) : PyNumber.OfInt(e.GetInt64())).ToList();
            var actual = PySum.Sum(items);
            var o = v.GetProperty("o");
            if (!IsDbl(o))
            {
                return actual.IsInt ? Eq("int sum", actual.IntValue.ToString(System.Globalization.CultureInfo.InvariantCulture), o.GetProperty("i").GetString()) : "expected an int sum";
            }

            return actual.IsInt ? "expected a float sum" : Same("sum", actual.FloatValue, o);
        });

    [Fact]
    public void A_naive_loop_does_not_match_python_sum_so_the_trap_is_real()
    {
        // Demonstrates the trap: a plain += loop diverges from Python on a measurable share of vectors.
        var diverged = 0;
        var total = 0;
        foreach (var v in GoldenFiles.Read(File, "sum"))
        {
            var naiveElem = v.GetProperty("naive");
            if (naiveElem.ValueKind == JsonValueKind.Null || !IsDbl(naiveElem) || !IsDbl(v.GetProperty("o")))
            {
                continue;
            }

            total++;
            if (!PyFloat.SameBits(Dbl(naiveElem), Dbl(v.GetProperty("o"))))
            {
                diverged++;
            }
        }

        Assert.True(total > 1000);
        Assert.True(diverged > 0, "expected Python's compensated sum to differ from a naive loop on some vectors");
    }

    [Fact]
    public void Built_in_dotnet_calls_diverge_from_python_so_the_harness_can_fail()
    {
        // Mutation self-test for G1: swap in the obvious BCL equivalents and prove the vectors catch each one.
        var roundDiverged = 0;
        foreach (var v in GoldenFiles.Read(File, "round"))
        {
            var x = Dbl(v.GetProperty("x"));
            var n = v.GetProperty("n").GetInt32();
            if (!PyFloat.SameBits(Math.Round(x, n, MidpointRounding.ToEven), Dbl(v.GetProperty("o"))))
            {
                roundDiverged++;
            }
        }

        var floorDivDiverged = 0;
        foreach (var v in GoldenFiles.Read(File, "fdivmod"))
        {
            if (!IsDbl(v.GetProperty("q")))
            {
                continue;
            }

            var a = Dbl(v.GetProperty("a"));
            var b = Dbl(v.GetProperty("b"));
            if (!PyFloat.SameBits(Math.Floor(a / b), Dbl(v.GetProperty("q"))))
            {
                floorDivDiverged++;
            }
        }

        var decimalCastDiverged = 0;
        foreach (var v in GoldenFiles.Read(File, "quantize"))
        {
            var x = Dbl(v.GetProperty("x"));
            if (v.GetProperty("mode").GetString() != "half_up" || v.GetProperty("f").ValueKind == JsonValueKind.Null || Math.Abs(x) > 1e20 || Math.Abs(x) < 1e-20)
            {
                continue;
            }

            var places = v.GetProperty("n").GetInt32();
            var viaCast = (double)Math.Round((decimal)x, places, MidpointRounding.AwayFromZero);
            if (!PyFloat.SameBits(viaCast, Dbl(v.GetProperty("f"))))
            {
                decimalCastDiverged++;
            }
        }

        Assert.True(roundDiverged > 0, "Math.Round should diverge from Python round() on some vectors");
        Assert.True(floorDivDiverged > 0, "Math.Floor(a / b) should diverge from Python // on some vectors");
        Assert.True(decimalCastDiverged > 0, "(decimal)x should diverge from Decimal(str(x)) on some vectors");
    }

    [Fact]
    public void Sum_of_booleans_and_rounded_headcount_match_python() =>
        Run("sum_bool", v =>
        {
            var count = v.GetProperty("xs").EnumerateArray().Count(e => e.GetBoolean());
            return Eq("sum(bools)", count.ToString(System.Globalization.CultureInfo.InvariantCulture), v.GetProperty("o").GetString()) ??
                   Same("round(sum/12.0, 4)", PyRound.Round(count / 12.0, 4), v.GetProperty("div12"));
        });
}
