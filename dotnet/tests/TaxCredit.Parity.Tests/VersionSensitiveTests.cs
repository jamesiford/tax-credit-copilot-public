using System.Globalization;
using System.Text.Json;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// The facts that differ between CPython 3.12 (the pinned oracle) and 3.14, kept as data in
/// <c>parity/goldens/version-sensitive.jsonl.gz</c>. The port must match <c>py312</c>; every failure also states what 3.14
/// would answer, so moving the oracle to a later interpreter is a deliberate, visible step and never a silent drift.
/// </summary>
public sealed class VersionSensitiveTests
{
    private const string File = "version-sensitive.jsonl.gz";

    private static string Excerpt(JsonElement e) => e.GetRawText() is { Length: > 300 } t ? t[..300] + "..." : e.GetRawText();

    private static IEnumerable<JsonElement> Vectors(string kind) => GoldenFiles.Read(File, "vs").Where(v => v.GetProperty("kind").GetString() == kind);

    private static void Replay(string kind, int expectedCount, Func<JsonElement, string?> check)
    {
        var failures = new List<string>();
        var count = 0;
        foreach (var v in Vectors(kind))
        {
            count++;
            var error = check(v.GetProperty("py312"));
            if (error is not null && failures.Count < 5)
            {
                failures.Add($"{error}\n  CPython 3.12 (oracle): {Excerpt(v.GetProperty("py312"))}\n  CPython 3.14 would give: {Excerpt(v.GetProperty("py314"))}");
            }
        }

        Assert.Equal(expectedCount, count);
        Assert.True(failures.Count == 0, $"the port no longer matches the {kind} behaviour of CPython 3.12:\n" + string.Join("\n", failures));
    }

    [Fact]
    public void Sum_of_an_int_after_a_float_is_not_compensated_like_cpython_312() =>
        Replay("sum", 382, PrimitiveParityTests.CheckSum);

    [Fact]
    public void Upper_matches_the_unicode_15_database_of_cpython_312() =>
        Replay("str", 26, v =>
        {
            var s = v.GetProperty("s").GetString()!;
            var upper = PyStr.Upper(s);
            return upper == v.GetProperty("upper").GetString() ? null : $"upper of '{s}' gave '{upper}'";
        });

    [Fact]
    public void The_case_table_and_unicode_version_are_those_of_cpython_312()
    {
        Replay("unicode_version", 1, v => PyUnicodeTables.UnicodeVersion == v.GetProperty("v").GetString() ? null : $"table is Unicode {PyUnicodeTables.UnicodeVersion}");
        Replay("case_table", 1, v =>
        {
            var expected = v.GetProperty("table").EnumerateArray().ToDictionary(r => r[0].GetInt32(), r => string.Concat(r[1].EnumerateArray().Select(e => char.ConvertFromUtf32(e.GetInt32()))));
            var bad = new List<int>();
            for (var cp = 0; cp < 0x110000; cp++)
            {
                if (cp is >= 0xD800 and <= 0xDFFF)
                {
                    continue;
                }

                var s = char.ConvertFromUtf32(cp);
                if (PyStr.Upper(s) != (expected.TryGetValue(cp, out var e) ? e : s))
                {
                    bad.Add(cp);
                }
            }

            return bad.Count == 0 ? null : $"{bad.Count} code points differ, first: {string.Join(',', bad.Take(10).Select(c => c.ToString("x", CultureInfo.InvariantCulture)))}";
        });
    }

    [Fact]
    public void A_314_style_sum_matches_every_py314_vector_and_fails_the_py312_ones_so_the_harness_can_tell_them_apart()
    {
        var total = 0;
        var matches314 = 0;
        var failsOracle = 0;
        foreach (var v in Vectors("sum"))
        {
            total++;
            var xs = v.GetProperty("py312").GetProperty("xs").EnumerateArray().Select(e => e.ValueKind == JsonValueKind.Object ? (true, PyFloat.FromBits(e.GetProperty("b").GetInt64()), 0L) : (false, 0.0, e.GetInt64())).ToList();
            var got = Sum314(xs);
            var want314 = v.GetProperty("py314").GetProperty("o");
            var want312 = v.GetProperty("py312").GetProperty("o");
            if (PyFloat.SameBits(got, PyFloat.FromBits(want314.GetProperty("b").GetInt64())))
            {
                matches314++;
            }

            if (!PyFloat.SameBits(got, PyFloat.FromBits(want312.GetProperty("b").GetInt64())))
            {
                failsOracle++;
            }
        }

        Assert.Equal(total, matches314);
        Assert.Equal(total, failsOracle);
    }

    /// <summary>CPython 3.14's <c>sum()</c>: trailing ints are compensated like floats. Test-only; the port must not do this.</summary>
    private static double Sum314(List<(bool IsFloat, double F, long I)> xs)
    {
        var i = 0;
        long intAcc = 0;
        for (; i < xs.Count && !xs[i].IsFloat; i++)
        {
            intAcc += xs[i].I;
        }

        var acc = (double)intAcc;
        if (i < xs.Count)
        {
            acc += xs[i].IsFloat ? xs[i].F : xs[i].I;
            i++;
        }

        var c = 0.0;
        for (; i < xs.Count; i++)
        {
            var x = xs[i].IsFloat ? xs[i].F : xs[i].I;
            var t = acc + x;
            c += Math.Abs(acc) >= Math.Abs(x) ? (acc - t) + x : (x - t) + acc;
            acc = t;
        }

        return c != 0 && double.IsFinite(c) ? acc + c : acc;
    }
}

/// <summary>Fails the run, with the instructions, unless <c>TCC_PYTHON</c> is CPython 3.12.</summary>
public sealed class OracleInterpreterTests
{
    [Fact]
    public void The_oracle_interpreter_is_cpython_312() => Assert.StartsWith("3.12.", OracleInterpreter.Version, StringComparison.Ordinal);

    [Theory]
    [InlineData("primitives.jsonl.gz")]
    [InlineData("engine.jsonl.gz")]
    [InlineData("datasets.jsonl.gz")]
    [InlineData("version-sensitive.jsonl.gz")]
    public void Every_golden_records_that_cpython_312_produced_it(string file) => GoldenFiles.AssertOracleStamp(file);
}
