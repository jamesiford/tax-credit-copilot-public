using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Differential fuzz of <c>tools/forecast.py</c> and <c>tools/simulation.py</c>: the year-end projection, the what-if hiring and One/Zero snapshot,
/// the role description and the lever, over small seeded payrolls with hours and wages either side of each floor, pack specs and real packs for every
/// state (missing years included), every month end and leap day as-of, city text with unicode case folding, and non-finite magnitudes.
/// </summary>
internal sealed class SimulationFuzz : FuzzFamily
{
    private static readonly string[] Cities =
    [
        "atlanta", "savannah", "macon", "new york", "brooklyn", "charleston", "greenville", "austin", "houston", "dallas", "charlotte", "raleigh", "nashville", "memphis", "jacksonville", "miami",
        "orlando", "columbus", "cincinnati", "cleveland", "denver", "boulder", "tysons", "tysons corner", "richmond", "arlington", "Atlanta", "ATLANTA", "  Atlanta  ", "ga", "Ga", "GA", "ny", "xx",
        "tx", "1a", "!!", "a", string.Empty, " ", "Mars", "Tampa", "new  york", "\u00a0atlanta\u00a0", "\u0130", "\u03a3", "\u0391\u03a3", "\u0391\u03a3 ", "\u00df", "\ufb01", "\u01c5", "\U0001f600", "\u212a",
        "\u1e9e", "\u0149", "\u1f88", "CO", "Nashville", "Houston",
    ];

    private static readonly string[] StateKeys = ["GA", "GA", "TN", "SC", "NC", "CO", "FL", "OH", "VA", "NY", "ga", "Ga", "GA_JTC", "TX", "ZZ", string.Empty, "tn", "sc_jobs"];
    private static readonly object?[] Averages = [0.0, 1.0, 2.0, 5.0, 10.5, 24.99, 25.0, 25.01, 30L, 100L, -4.0, double.NaN, double.PositiveInfinity, -1e300, 1e-9, 1e300, 12.345, 12.355, 0.005, 0.015, 41.5, 42.0, 40.0, 7L];
    private static readonly object?[] Magnitudes = [0L, 1L, 2L, 3L, 5L, -1L, -2L, 2.5, 0.5, -0.5, 10L, -10L, 100L, 1000.0, 7.77, -7.77, 0.05, double.NaN, double.PositiveInfinity, double.NegativeInfinity];

    public override string Name => "simulation";

    public override IReadOnlyList<string> Functions { get; } =
    [
        "_months_elapsed", "_ytd_average_headcount", "project_state_year_end", "_resolve_location", "str.lower", "simulate_hiring", "chat_state_credit", "latest_tax_year",
        "onezero_snapshot", "describe_role", "apply_onezero_lever",
    ];

    public override Func<PyDict, string?> CreateChecker()
    {
        var golden = new ForecastGolden();
        return call => Replay(call, golden.Invoke);
    }

    public override FamilyCase Generate(Rng r, string id)
    {
        var roll = r.Int(0, 99);
        var (fn, args) = roll switch
        {
            < 8 => ("_months_elapsed", MonthsElapsed(r)),
            < 16 => ("_ytd_average_headcount", Ytd(r)),
            < 34 => ("project_state_year_end", Project(r)),
            < 44 => ("_resolve_location", new PyDict().Add("city_or_state", r.Chance(0.5) ? r.Pick(Cities) : Alphabet(r))),
            < 48 => ("str.lower", new PyDict().Add("s", Alphabet(r))),
            < 56 => ("simulate_hiring", Hiring(r)),
            < 63 => ("chat_state_credit", Credit(r)),
            < 65 => ("latest_tax_year", new PyDict().Add("fy_end_month", (long)r.Int(1, 12))),
            < 77 => ("onezero_snapshot", Snapshot(r)),
            < 89 => ("describe_role", Role(r)),
            _ => ("apply_onezero_lever", Lever(r)),
        };
        return new FamilyCase(id, fn, args);
    }

    private static string Alphabet(Rng r)
    {
        const string alphabet = "aAbBzZ \t\u00dfi\u0130\u0131\u03a3\u03c3\u212a\U0001f600.'1-\u0391\u00b7";
        var text = alphabet.EnumerateRunes().ToList();
        return string.Concat(Enumerable.Range(0, r.Int(0, 5)).Select(_ => text[r.Int(0, text.Count - 1)].ToString()));
    }

    private static PyDict MonthsElapsed(Rng r)
    {
        var start = r.Chance(0.1) ? r.Pick(new[] { new DateOnly(1, 1, 1), new DateOnly(9998, 1, 1), new DateOnly(2020, 2, 29), new DateOnly(9999, 12, 1) }) : Pools.Day(r, 2018, 2026);
        var asOf = r.Chance(0.1) ? r.Pick(new[] { new DateOnly(9999, 12, 31), new DateOnly(1, 1, 1), new DateOnly(2024, 2, 29) }) : Pools.Shift(start, r.Int(-60, 500));
        return new PyDict().Add("analysis_start", Pools.Date(start)).Add("as_of", Pools.Date(asOf));
    }

    private static PyDict Ytd(Rng r)
    {
        var units = Enumerable.Range(0, r.Pick(new[] { 0, 1, 2, 5, 9 })).Select(_ => (object?)new PyDict().Add("worksite_id", "U").Add("month_totals",
            Enumerable.Range(0, r.Pick(new[] { 12, 12, 12, 6, 3, 0, 13 })).Select(_ => r.Chance(0.05) ? Pools.SpecialFloat(r) : r.Pick(new object[] { r.Uniform(0, 100), Math.Round(r.Uniform(0, 100), 2), (double)r.Int(0, 50), (long)r.Int(0, 50), 0.0, 1e-9, 0.1 })).Select(x => (object?)x).ToList())).ToList();
        return new PyDict().Add("summary", units).Add("months_elapsed", r.Pick(new object[] { -3L, -1L, 0L, 1L, 2L, 3L, 8L, 11L, 12L, 13L, 24L, 1000L, (long)r.Int(-1, 14) }));
    }

    private static PyDict Project(Rng r)
    {
        var year = r.Pick(new[] { 2019, 2022, 2023, 2024, 2025, 2025, 2026, 0 });
        var args = new PyDict().Add("state", r.Pick(StateKeys)).Add("tax_year", (long)year);
        var inline = r.Chance(0.2);
        args.Add("rows", inline ? SimulationData.Rows(r, 5) : new List<object?>()).Add("prior_rows", inline && r.Chance(0.4) ? SimulationData.Rows(r, 3) : new List<object?>());
        args.Add("as_of", Pools.Date(Pools.Shift(new DateOnly(Math.Max(year, 1), 1, 1), r.Int(-40, 420))));
        if (r.Chance(0.5))
        {
            args.Add("fiscal_year_end_month", r.Pick(new object[] { 12L, 12L, 6L, 7L, 9L, 3L, 1L, 2L }));
        }

        if (!inline || r.Chance(0.5))
        {
            args.Add("ytd_average_headcount", r.Chance(0.5) ? r.Pick(Averages) : Pools.Around(r, 42.0));
        }

        if (r.Chance(0.7))
        {
            args.Add("prior_average_headcount", r.Chance(0.4) ? r.Pick(Averages) : Pools.Around(r, 40.0));
        }

        if (r.Chance(0.5))
        {
            args.Add("months_elapsed", r.Pick(new object[] { (long)r.Int(1, 12), -2L, 0L, 13L, 99L }));
        }

        return Trail(r, args, 0.4);
    }

    private static PyDict Trail(Rng r, PyDict args, double chance) =>
        r.Chance(chance) ? args.Add("trail", new PyDict().Add("title", r.Pick(new[] { string.Empty, "Pending", "x" })).Add("citation", string.Empty)) : args;

    private static PyDict Hiring(Rng r)
    {
        var args = new PyDict().Add("location", r.Chance(0.03) ? null : r.Pick(Cities)).Add("new_hires", r.Pick(new object[] { 25L, -25L, 1L, -1L, 10L, -10L, 500L, -500L, 1000L, -1000L, 3L, 100L, 0L, (long)r.Int(-100, 100) }));
        return Trail(r, args, 0.15);
    }

    private static PyDict Credit(Rng r)
    {
        var args = new PyDict().Add("state", r.Pick(StateKeys));
        var withAverages = r.Chance(0.75);
        if (r.Chance(0.4) || !withAverages)
        {
            args.Add("tax_year", r.Pick(new object[] { 2023L, 2024L, 2025L, 2026L }));
        }

        if (r.Chance(0.2))
        {
            args.Add("fy_end_month", r.Pick(new object[] { 6L, 9L, 12L }));
        }

        if (withAverages)
        {
            args.Add("current_average", r.Chance(0.5) ? r.Pick(Averages) : Pools.Around(r, 61.0));
            if (r.Chance(0.7))
            {
                args.Add("prior_average", r.Pick(new object?[] { 40.0, null, 0.0, 12.5, 7L, 40L }));
            }
        }

        if (r.Chance(0.2))
        {
            args.Add("program_code", r.Pick(new[] { "GA_JTC", "SC_JOBS", "TN_JTC" }));
        }

        return Trail(r, args, 0.2);
    }

    private static PyDict Snapshot(Rng r)
    {
        var args = new PyDict().Add("rows", SimulationData.Rows(r, 8)).Add("tax_year", r.Pick(new object[] { 2025L, 2025L, 2024L, 0L })).Add("state", r.Pick(StateKeys)).Add("pack", SimulationData.Pack(r));
        if (r.Chance(0.7))
        {
            args.Add("prior_average_headcount", r.Pick(new object[] { 0.0, 2.5, 4L, 10.0, 12.5, 7L, 0.005, 29.995, double.NaN }));
        }

        return Trail(r, args, 0.2);
    }

    private static PyDict Role(Rng r)
    {
        var hours = r.Pick(new object?[] { null, 0L, 0.0, 10L, 20L, 31.99, 32L, 34.99, 35L, 35.0, 35.01, 37.49, 37.5, 40L, 80.5, -1.0, 1e-9, 1e6, 1234567.0, double.NaN, double.PositiveInfinity, double.NegativeInfinity });
        var rate = r.Chance(0.3) && hours is long or double ? Pools.Around(r, 636.0 / Math.Max(1e-9, hours is long l ? l : (double)hours)) : r.Pick(new object?[] { null, 0L, 0.0, 7.25, 12L, 15.0, 18.17, 18.171, 18.1714, 20L, 25.0, 100L, 1e-9, -3.0, double.NaN, double.PositiveInfinity, 1e300 });
        return new PyDict().Add("weekly_hours", hours).Add("hourly_rate", rate).Add("pack", SimulationData.Pack(r));
    }

    private static PyDict Lever(Rng r)
    {
        var args = new PyDict().Add("rows", SimulationData.Rows(r, 6)).Add("action", r.Pick(new[] { "adjust_hours", "adjust_wages", "add_headcount", "remove_headcount", "adjust_hours", "add_headcount", "bogus", string.Empty }))
            .Add("magnitude", r.Pick(Magnitudes)).Add("pack", SimulationData.Pack(r)).Add("state", r.Pick(new[] { "GA", "ga", "TX", "TN", "GA" }));
        if (r.Chance(0.3))
        {
            args.Add("fein", "58-1111111");
        }

        if (r.Chance(0.5))
        {
            args.Add("hire_weekly_hours", r.Pick(new object?[] { null, 20L, 30.5, 35.0, 40L, 34.99, 30L, 12.5, 0L, 1e6, 37.5 }));
        }

        if (r.Chance(0.5))
        {
            args.Add("hire_hourly_rate", r.Pick(new object?[] { null, 7.25, 15L, 18.17, 25.5, 20L, 0L, 0.0, 12.5, 1e6, 18.1714286 }));
        }

        return args;
    }
}
