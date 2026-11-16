using TaxCredit.Domain.Forecast;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Simulation;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate DS6 (forecast and what-if family): replays every call of <c>parity/goldens/forecast.jsonl.gz</c> (production
/// <c>tools/forecast.py</c>, <c>tools/simulation.py</c> and the <c>portfolio.chat_state_credit</c> they import, on CPython 3.12) against
/// <see cref="ForecastProjection"/>, <see cref="WhatIfSimulator"/>, <see cref="OneZeroSimulation"/> and <see cref="OneZeroLever"/>. Trees
/// are compared by type (int versus float), key order, double bit pattern and exception type plus message; trails by their SHA-256.
/// </summary>
public sealed class ForecastParityTests
{
    private static readonly string[] Functions =
        ["_months_elapsed", "_ytd_average_headcount", "project_state_year_end", "_resolve_location", "simulate_hiring", "chat_state_credit", "latest_tax_year", "onezero_snapshot", "describe_role", "apply_onezero_lever", "str.lower"];

    [Fact]
    [Trait("Category", "heavy")]
    public void Every_golden_call_matches_python_bit_for_bit()
    {
        var golden = new ForecastGolden();
        ClaimGolden.AssertAllMatch(ForecastGolden.File, golden.Invoke, Functions, 7000, 300);
    }

    [Fact]
    [Trait("Category", "heavy")]
    public void A_perturbed_output_is_detected_by_the_comparison()
    {
        // Mutation self-test (in process): the same comparison, fed outputs with one deliberate defect, must disagree.
        var golden = new ForecastGolden();
        var detected = new Dictionary<string, int> { ["ulp"] = 0, ["int-as-float"] = 0, ["bool-flip"] = 0, ["key-order"] = 0, ["trail-hash"] = 0 };
        foreach (var call in ForecastGolden.Calls().Skip(1).Take(3500).Where(c => !c.ContainsKey("err")))
        {
            var expected = call["out"];
            var actual = golden.Invoke(call);
            foreach (var name in detected.Keys.ToList())
            {
                var mutated = Mutate(Copy(actual), name);
                if (mutated is not null && ClaimGolden.Compare(expected, mutated, "$") is not null)
                {
                    detected[name]++;
                }
            }
        }

        foreach (var (name, n) in detected)
        {
            Assert.True(n > 5, $"the comparison cannot fail for '{name}' ({n} detections)");
        }
    }

    [Fact]
    public void The_denominator_is_counted_off_the_runs_own_months_not_from_1_january()
    {
        // test_forecast.test_months_elapsed_counts_the_runs_own_month_ends: for an August-opening year 31 December is month FIVE.
        var start = new DateOnly(2023, 8, 1);
        Assert.Equal(5, ForecastProjection.MonthsElapsed(start, new DateOnly(2023, 12, 31)));
        Assert.Equal(8, ForecastProjection.MonthsElapsed(start, new DateOnly(2024, 3, 31)));
        Assert.Equal(1, ForecastProjection.MonthsElapsed(start, new DateOnly(2023, 8, 1)));
        Assert.Equal(12, ForecastProjection.MonthsElapsed(start, new DateOnly(2030, 1, 1)));
        Assert.Equal(12, ForecastProjection.MonthsElapsed(new DateOnly(2023, 1, 1), new DateOnly(2023, 12, 31)));
    }

    [Fact]
    public void A_supplied_average_bypasses_the_payroll_replay()
    {
        var golden = new ForecastGolden();
        var projected = new ForecastProjection(golden.Library).ProjectStateYearEnd("GA", 2023, [], [], new DateOnly(2024, 3, 31), new ForecastOptions(YtdAverageHeadcount: 410.13, PriorAverageHeadcount: 375.53));
        Assert.NotNull(projected);
        Assert.Equal(410.13, projected["ytd_average_headcount"]);
        Assert.Equal(375.53, projected["prior_year_average_headcount"]);
        Assert.Equal(410.13, projected["projected_average_headcount"]);
    }

    [Fact]
    public void The_latest_year_of_an_empty_payroll_is_the_prior_calendar_year()
    {
        // Not in the golden: Python reads date.today(), which would make the golden stale every January.
        var golden = new ForecastGolden();
        var calc = new StateCreditCalculator(golden.Library, new GoldenPayroll([]), () => new DateOnly(2031, 5, 5));
        Assert.Equal(2030, calc.LatestTaxYear());
    }

    [Theory]
    [InlineData(35.0, "35")]
    [InlineData(32.5, "32.5")]
    [InlineData(1e6, "1e+06")]
    [InlineData(123456.7, "123457")]
    [InlineData(0.00001, "1e-05")]
    [InlineData(0.0001, "0.0001")]
    [InlineData(-0.0, "-0")]
    public void General_format_matches_python(double value, string expected) => Assert.Equal(expected, PyFormat.General(value));

    [Theory]
    [InlineData(636.5, 0, true, false, "636")]
    [InlineData(637.5, 0, true, false, "638")]
    [InlineData(0.125, 2, false, false, "0.12")]
    [InlineData(1234567.891, 2, true, false, "1,234,567.89")]
    [InlineData(2.0, 1, false, true, "+2.0")]
    [InlineData(-0.04, 1, false, true, "-0.0")]
    public void Fixed_format_rounds_the_exact_binary_value_half_to_even(double value, int decimals, bool grouping, bool plus, string expected) =>
        Assert.Equal(expected, PyFormat.Fixed(value, decimals, grouping, plus));

    private static object? Mutate(object? t, string how) => how switch
    {
        "ulp" => Map(t, v => v is double d && double.IsFinite(d) && d != 0 ? BitConverter.Int64BitsToDouble(BitConverter.DoubleToInt64Bits(d) + 1) : v),
        "int-as-float" => Map(t, v => v is long l ? (double)l : v),
        "bool-flip" => Map(t, v => v is bool b ? !b : v),
        "trail-hash" => Map(t, v => v is string s && s.StartsWith("sha256:", StringComparison.Ordinal) ? "sha256:0" + s[8..] : v),
        _ => Map(t, v => v is PyDict { Count: > 1 } d ? Reverse(d) : v),
    };

    private static PyDict Reverse(PyDict d)
    {
        var reversed = new PyDict();
        foreach (var kv in d.Reverse())
        {
            reversed.Add(kv.Key, kv.Value);
        }

        return reversed;
    }

    private static object? Map(object? t, Func<object?, object?> f) => t switch
    {
        PyDict d => f(d.Aggregate(new PyDict(), (acc, kv) => acc.Add(kv.Key, Map(kv.Value, f)))),
        List<object?> l => f(l.Select(x => Map(x, f)).ToList()),
        _ => f(t),
    };

    private static object? Copy(object? t) => Map(t, v => v);
}
