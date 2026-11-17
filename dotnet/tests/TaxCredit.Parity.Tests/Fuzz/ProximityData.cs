using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>Row and series builders for the proximity fuzz.</summary>
internal static class ProximityData
{
    public static double Num(object v) => v is long l ? l : (double)v;

    private static object IntIfWhole(Rng r, double v)
    {
        object result = v;
        if (r.Chance(0.3) && v == Math.Floor(v) && Math.Abs(v) < 1e15)
        {
            result = (long)v;
        }

        return result;
    }

    /// <summary>A cohort: tie-heavy (a few lever templates under many ids) a third of the time.</summary>
    public static List<object?> Rows(Rng r, FloorSpec f)
    {
        var n = r.Pick(new[] { 0, 1, 2, 3, 5, 8, 12, 20, 40 });
        var tie = r.Chance(0.3);
        var templates = Enumerable.Range(0, r.Int(1, 3)).Select(_ => Row(r, f, 0)).ToList();
        return Enumerable.Range(0, n).Select(i => tie ? Tied(r, templates[i % templates.Count], i) : (object?)Row(r, f, i)).ToList();
    }

    private static PyDict Tied(Rng r, PyDict template, int i) =>
        template.Aggregate(new PyDict(), (d, kv) => d.Add(kv.Key, kv.Key == "Employee_ID" ? Pools.EmployeeId(r, i) : kv.Value));

    /// <summary>One employee-average row with levers around the floors, optional verdict/weight/token, and a few percent of damaged fields.</summary>
    public static PyDict Row(Rng r, FloorSpec f, int i)
    {
        var weeks = r.Pick(new object[] { 52.0, 52L, 26.5, 10.0, 1.0, 0.0, 0L, 53.14, 4.43, r.Uniform(0.1, 60) });
        var avgHours = r.Chance(0.6) ? Pools.Around(r, f.HoursValue) : r.Pick(new object[] { 0L, 5.0, 20L, 30.0, 34.5, 35.0, 36L, 40.0, 70.0, r.Uniform(0, 70) });
        var avgWages = r.Chance(0.6) ? Pools.Around(r, f.WagesValue) : Math.Round(Num(avgHours) * r.Pick(new[] { 0.0, 7.25, 12.0, 15.0, 18.17, 25.0, 40.0, r.Uniform(5, 90) }), 2);
        var totalHours = Math.Round(Num(avgHours) * Num(weeks), r.Pick(new[] { 0, 1, 2, 3, 6 }));
        var totalWages = Math.Round(Num(avgWages) * Num(weeks), r.Pick(new[] { 0, 2, 2, 3, 6 }));
        var row = new PyDict()
            .Add("Employee_ID", Pools.EmployeeId(r, i))
            .Add("total_hours", IntIfWhole(r, totalHours))
            .Add("total_wages", IntIfWhole(r, totalWages))
            .Add("weeks_worked", weeks)
            .Add("avg_weekly_hours", avgHours)
            .Add("avg_weekly_wages", avgWages);
        if (r.Chance(0.3))
        {
            row.Set("eligible", r.Pick(new object?[] { true, false, null, 0L, 1L, string.Empty, "no", 0.0, 2L }));
        }

        if (r.Chance(0.25))
        {
            row.Set("weight", r.Pick(new object?[] { 0.5, 1.0, 0L, null, 0.25, 0.75, 1L, 0.1, 0.2, 0.3, -0.5, 2L, true, double.NaN, "0.25" }));
        }

        if (r.Chance(0.3))
        {
            row.Set("record_token", r.Chance(0.9) ? $"t{r.Int(0, 999)}" : null);
        }

        return Disturb(r, row);
    }

    private static PyDict Disturb(Rng r, PyDict row)
    {
        var result = new PyDict();
        foreach (var (key, value) in row)
        {
            if (key is "Employee_ID" or "eligible" or "weight" or "record_token" || !r.Chance(0.03))
            {
                result.Add(key, value);
                continue;
            }

            switch (r.Int(0, 3))
            {
                case 0:
                    break;
                case 1:
                    result.Add(key, null);
                    break;
                case 2:
                    result.Add(key, Pools.Special(r));
                    break;
                default:
                    result.Add(key, Pools.Weird(r));
                    break;
            }
        }

        return result;
    }

    /// <summary>The arguments of one <c>rest_of_year</c> call: a cadence of pay periods, an as-of date on a boundary, and a year end.</summary>
    public static PyDict RestOfYear(Rng r, FloorSpec f, IReadOnlyList<object?> decimalsPool)
    {
        var args = new PyDict().Add("periods", Periods(r)).Add("floors", f.ToArgs());
        var yearEnd = r.Pick(new[] { new DateOnly(2025, 12, 31), new DateOnly(2025, 12, 28), new DateOnly(2026, 3, 31), new DateOnly(2024, 12, 31) });
        var asOf = r.Chance(0.5) ? Pools.Day(r, yearEnd.Year, yearEnd.Year) : yearEnd.AddDays(r.Int(-300, 20));
        args.Add("as_of", r.Chance(0.1) ? r.Pick(new object?[] { "2025-08-31", "2025-08-31T23:59:59", "20250831", "bad", string.Empty, null, 20250831L, "2025-02-30" }) : Pools.Date(asOf));
        args.Add("year_end", r.Chance(0.05) ? r.Pick(new object?[] { "2025-12-31", "bad", null }) : Pools.Date(yearEnd));
        if (r.Chance(0.5))
        {
            args.Add("method", r.Pick(new object?[] { "min_max", "pay_period", "min_max", "pay_period", "other", string.Empty, null }));
        }

        if (r.Chance(0.2))
        {
            args.Add("decimals", r.Pick(decimalsPool));
        }

        return args;
    }

    private static List<object?> Periods(Rng r)
    {
        var days = r.Pick(new[] { 7, 7, 14, 14, 15, 28, 30, 1, 10 });
        var n = r.Pick(new[] { 0, 1, 2, 5, 12, 18, 30, 34 });
        var hours = r.Pick(new[] { 0.0, 10.0, 24.5, 34.0, 34.995, 36.0, 38.0, 40.0, 70.0, 80.0, r.Uniform(1, 100) });
        var wage = r.Pick(new[] { 0.0, 7.25, 15.0, 17.0, 18.125, 18.17, 20.0, 25.0, r.Uniform(5, 60) });
        var lag = r.Pick(new int?[] { null, null, 0, 3, 5, 7, -2, 21, 40 });
        var start = r.Chance(0.15) ? new DateOnly(2024, 2, 29).AddDays(r.Int(-20, 5)) : new DateOnly(2025, 1, 1).AddDays(r.Int(-30, 120));
        var asDate = r.Chance(0.3);
        object Pd(DateOnly d) => asDate ? Pools.Date(d) : Pools.Iso(d);
        var list = new List<object?>();
        for (var i = 0; i < n; i++)
        {
            var s = start.AddDays(days * i);
            var e = s.AddDays(days - 1);
            var period = new PyDict().Add("pay_period_start", Pd(s)).Add("pay_period_end", Pd(e)).Add("hours", hours * days / 7).Add("wages", Math.Round(hours * days / 7 * wage, 2));
            if (lag is { } l)
            {
                period.Add("pay_date", Pd(e.AddDays(l)));
            }

            list.Add(r.Chance(0.03) ? Mutate(r, period) : period);
        }

        return list;
    }

    private static PyDict Mutate(Rng r, PyDict period)
    {
        var key = r.Pick(new[] { "pay_period_start", "pay_period_end", "hours", "wages", "pay_date" });
        var result = new PyDict();
        foreach (var (k, v) in period)
        {
            if (k != key)
            {
                result.Add(k, v);
            }
            else if (r.Chance(0.5))
            {
                result.Add(k, r.Pick(new object?[] { null, "x", "garbage", -5.0, double.PositiveInfinity, double.NaN, 1e308, 7L, string.Empty, "2025-01-20" }));
            }
        }

        return result;
    }
}
