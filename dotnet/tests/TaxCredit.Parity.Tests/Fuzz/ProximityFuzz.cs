using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>One statutory floor pair as a scenario carries it: ints and floats are both used so the output type of each function is exercised.</summary>
internal readonly record struct FloorSpec(string Code, long Year, object Hours, object Wages)
{
    /// <summary>The recorded-argument encoding of the floors (the four fields <c>fuzz_ops</c> rebuilds a <c>StatutoryFloors</c> from).</summary>
    public PyDict ToArgs() => new PyDict().Add("program_code", Code).Add("tax_year", Year).Add("min_hours", Hours).Add("min_wages", Wages);

    /// <summary>The weekly hours floor as a double.</summary>
    public double HoursValue => ProximityData.Num(Hours);

    /// <summary>The weekly wages floor as a double.</summary>
    public double WagesValue => ProximityData.Num(Wages);
}

/// <summary>
/// Differential fuzz of <c>domain/calculation/proximity.py</c>: employee rows with levers either side of each floor, tie-heavy cohorts, recorded
/// verdicts, part-time weights, <c>population</c> overrides, and pay-period series for the rest-of-year projection (leap days, month ends, lags).
/// </summary>
internal sealed class ProximityFuzz : FuzzFamily
{
    private static readonly FloorSpec[] FloorPool =
    [
        new("GA_JTC", 2023, 35L, 636L), new("GA_JTC", 2024, 35.0, 636.0), new("GA_JTC", 2021, 35L, 600.5), new("GA_JTC", 2025, 35.0, 636.5), new("XX_DEMO", 2030, 32.5, 700.25),
        new("SC_JOBS", 2024, 35.0, 0.0), new("ZERO_H", 2024, 0L, 636.0), new("ZERO_H", 2024, 0.0, 0L), new("NEG", 2024, -5.0, -100.0), new("BIG", 2024, 1e300, 1e300),
        new("TINY", 2024, 5e-324, 5e-324), new("Ga_Mixed", 2024, 20.0, 360.0), new("GA_JTC", 2023, 35L, 636L), new("GA_JTC", 2023, 35.0, 636.0),
    ];

    private static readonly object?[] Bands = [5.0, 0.0, 1.0, 2.5, 5L, 10.0, 20.0, 40.0, 100.0, -1.0, 0.5, double.PositiveInfinity, double.NaN, 1e-9];
    private static readonly object?[] Limits = [null, 0L, 1L, 2L, 3L, 10L, -1L, -3L, 1000L];
    private static readonly object?[] DecimalsPool = [2L, 2L, 2L, 0L, 1L, 3L, 4L, -1L, -2L, 6L, 10L];

    public override string Name => "proximity";

    public override IReadOnlyList<string> Functions { get; } = ["_rate", "assess_employee", "fragility", "near_miss_cohort", "fragile_cohort", "band_curve", "rest_of_year"];

    public override Func<PyDict, string?> CreateChecker() => call => Replay(call, ProximityParityTests.Invoke);

    public override FamilyCase Generate(Rng r, string id)
    {
        var floors = r.Pick(FloorPool);
        var roll = r.Int(0, 99);
        var fn = roll switch
        {
            < 5 => "_rate",
            < 25 => "assess_employee",
            < 45 => "fragility",
            < 62 => "near_miss_cohort",
            < 79 => "fragile_cohort",
            < 85 => "band_curve",
            _ => "rest_of_year",
        };
        var args = new PyDict();
        switch (fn)
        {
            case "_rate":
                args.Add("total_hours", Rate(r)).Add("total_wages", Rate(r));
                break;
            case "assess_employee":
            case "fragility":
                args.Add("average", ProximityData.Row(r, floors, 0)).Add("floors", floors.ToArgs());
                Optional(r, args, "decimals", 0.25, DecimalsPool);
                break;
            case "band_curve":
                args.Add("averages", ProximityData.Rows(r, floors)).Add("floors", floors.ToArgs());
                if (r.Chance(0.5))
                {
                    args.Add("bands", Enumerable.Range(0, r.Int(0, 5)).Select(_ => r.Pick(Bands)).ToList());
                }

                Optional(r, args, "decimals", 0.3, DecimalsPool);
                break;
            case "rest_of_year":
                args = ProximityData.RestOfYear(r, floors, DecimalsPool);
                break;
            default:
                args.Add("averages", ProximityData.Rows(r, floors)).Add("floors", floors.ToArgs());
                Optional(r, args, "within_weekly_hours", 0.75, Bands);
                Optional(r, args, "limit", 0.4, Limits);
                Optional(r, args, "decimals", 0.4, DecimalsPool);
                if (r.Chance(0.3))
                {
                    args.Add("population", Population(r));
                }

                break;
        }

        return new FamilyCase(id, fn, args);
    }

    private static void Optional(Rng r, PyDict args, string key, double chance, IReadOnlyList<object?> pool)
    {
        if (r.Chance(chance))
        {
            args.Add(key, r.Pick(pool));
        }
    }

    private static object Rate(Rng r) => r.Chance(0.1)
        ? Pools.SpecialFloat(r)
        : r.Pick(new object[] { 0L, 0.0, 10.0, 181.7, -1.0, 1.0, 35.0, 636.0, 7.25, 100.5, 1e-9, 1e12, 3L, 7L, r.Uniform(0, 3000) });

    private static PyDict Population(Rng r) => r.Int(0, 7) switch
    {
        0 => new PyDict().Add("evaluated", 10080L).Add("eligible", 539L).Add("ineligible", 9541L).Add("failure_modes", new PyDict().Add("hours_only", 7000L).Add("wages_only", 41L).Add("both", 2500L)),
        1 => new PyDict().Add("evaluated", 5L).Add("eligible", 2L).Add("ineligible", 3L).Add("failure_modes", new PyDict()),
        2 => new PyDict().Add("evaluated", 5.9).Add("eligible", 2.2).Add("ineligible", 3.7).Add("failure_modes", new PyDict().Add("both", 1L).Add("none", 2L)),
        3 => new PyDict().Add("eligible", 2L),
        4 => new PyDict().Add("evaluated", "7").Add("eligible", "2").Add("ineligible", "3").Add("failure_modes", new PyDict().Add("b", 1L).Add("a", 2L)),
        5 => new PyDict().Add("evaluated", true).Add("eligible", false).Add("ineligible", 0L).Add("failure_modes", new PyDict().Add("z", 1L).Add("a", 2L).Add("m", 3L)),
        6 => new PyDict().Add("evaluated", 3L).Add("eligible", 1L).Add("ineligible", 2L).Add("failure_modes", null),
        _ => new PyDict(),
    };
}
