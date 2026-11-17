using System.Numerics;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>Argument builders for the employee-grain and summary-grain Gold tables and the calculation id.</summary>
internal static class GoldTables
{
    private static readonly object?[] DaysPool = [null, 0L, 1L, 180L, -3L, 12.9, -12.9, 1e19, 3.0, double.NaN, double.PositiveInfinity, true, false, "12", " 12 ", "1_2", "12.5", string.Empty, "abc", 10L, BigInteger.Pow(10, 30), "\u0661\u0662"];

    /// <summary>Puts a cell: ordinary most of the time, a pool edge value some of the time, absent a couple of percent of the time.</summary>
    public static PyDict Put(this PyDict d, Rng r, string key, object? ordinary, Func<Rng, object?> pool, double edge = 0.12)
    {
        if (r.Chance(0.02))
        {
            return d;
        }

        return d.Add(key, r.Chance(edge) ? pool(r) : ordinary);
    }

    private static string Iso(Rng r) => Pools.Iso(Pools.Day(r, 2019, 2026));

    private static PyDict PayrollRow(Rng r, int i)
    {
        var start = Pools.Day(r, 2019, 2026);
        return new PyDict()
            .Put(r, "Employee_ID", i == 0 ? "E1" : $"E{i}", g => g.Chance(0.5) ? GoldPools.EmployeeId(g) : GoldPools.Text(g), 0.1)
            .Put(r, "Worksite_ID", "GA_1", GoldPools.Text)
            .Put(r, "Entity_FEIN", "12-3456789", GoldPools.Text)
            .Put(r, "Job_Title", "Cook", GoldPools.Text)
            .Put(r, "Pay_Period_Start", Pools.Iso(start), GoldPools.Day)
            .Put(r, "Pay_Period_End", Pools.Iso(start.AddDays(r.Int(0, 40))), GoldPools.Day)
            .Put(r, "Pay_Date", r.Chance(0.2) ? null : Pools.Iso(start.AddDays(r.Int(0, 60))), GoldPools.Day)
            .Put(r, "Pay_Frequency", "3", GoldPools.Text)
            .Put(r, "Pay_Code", r.Pick(new[] { "Regular", "Overtime", string.Empty }), GoldPools.Text)
            .Put(r, "Hours_Worked", GoldPools.Money(r), GoldPools.Dec)
            .Put(r, "Gross_Wages", GoldPools.Money(r), GoldPools.Dec);
    }

    private static List<object?> Many(Rng r, int max, Func<int, object?> make) => Enumerable.Range(0, r.Pick(new[] { 0, 1, 1, 2, 3, max })).Select(make).ToList();

    private static PyDict Total(Rng r, string id) => new PyDict().Put(r, "Employee_ID", id, GoldPools.Text, 0.05)
        .Put(r, "total_hours", Math.Round(r.Uniform(0, 3000), r.Int(0, 4)), GoldPools.Dec).Put(r, "total_wages", Math.Round(r.Uniform(0, 90000), 2), GoldPools.Dec);

    private static PyDict Average(Rng r, string id) => Total(r, id)
        .Put(r, "first_start", "2023-01-01", GoldPools.Day).Put(r, "last_end", "2023-06-30", GoldPools.Day)
        .Put(r, "days", (long)r.Int(1, 365), _ => r.Pick(DaysPool))
        .Put(r, "weeks_worked", Math.Round(r.Uniform(1, 53), 2), GoldPools.Dec).Put(r, "avg_weekly_hours", Math.Round(r.Uniform(5, 50), 2), GoldPools.Dec)
        .Put(r, "avg_weekly_wages", Math.Round(r.Uniform(100, 1500), 2), GoldPools.Dec).Put(r, "passed_hours", r.Chance(0.5), GoldPools.Flag).Put(r, "passed_wages", r.Chance(0.5), GoldPools.Flag)
        .Put(r, "weight", r.Pick(new object[] { 1.0, 0.5, 0.0 }), GoldPools.Dec).Put(r, "eligible", r.Chance(0.5), GoldPools.Flag);

    private static PyDict Months(Rng r, PyDict row) => row.Put(r, "months", Enumerable.Range(0, r.Pick(new[] { 12, 12, 12, 12, 6, 13, 0, 11 })).Select(_ => r.Pick(new object?[] { 0L, 0.0, 1.0, 0.5, 1L, 0.25, 0.333, 0.005, 0.015 })).ToList(), g => g.Chance(0.5) ? null : new List<object?> { GoldPools.Dec(g), 1.0 });

    private static PyDict MatrixRow(Rng r, int i)
    {
        var row = new PyDict().Put(r, "Employee_ID", $"E{i % 3}", GoldPools.Text, 0.05).Put(r, "Worksite_ID", "GA_1", GoldPools.Text).Put(r, "Entity_FEIN", "58-1", GoldPools.Text)
            .Put(r, "weight", r.Pick(new object[] { 1.0, 0.5, 0.0 }), GoldPools.Dec);
        row = Months(r, row);
        if (r.Chance(0.5))
        {
            return row.Put(r, "first_pps", Iso(r), GoldPools.Day).Put(r, "last_ppe", Iso(r), GoldPools.Day);
        }

        return row.Put(r, "Pay_Period_Start", Iso(r), GoldPools.Day).Put(r, "Pay_Period_End", Iso(r), GoldPools.Day).Put(r, "Pay_Date", Iso(r), GoldPools.Day);
    }

    private static PyDict SummaryRow(Rng r, int i) => new PyDict().Put(r, "Worksite_ID", r.Pick(new[] { "GA_1", "GA_\u00e9", "TN_2", "\u4e2d", $"GA_{i}" }), GoldPools.Text)
        .Put(r, "month_totals", Enumerable.Range(0, r.Pick(new[] { 12, 12, 12, 6, 13, 0 })).Select(_ => r.Pick(new object?[] { 0.0, 0L, Math.Round(r.Uniform(0, 60), 2), Math.Round(r.Uniform(0, 60), 4), 10.0 })).ToList(),
            g => g.Chance(0.5) ? null : new List<object?> { GoldPools.Dec(g), 1.0 })
        .Put(r, "total", Math.Round(r.Uniform(0, 400), 2), GoldPools.Dec).Put(r, "average_headcount", Math.Round(r.Uniform(0, 40), 2), GoldPools.Dec);

    /// <summary>The arguments of one table-building call.</summary>
    public static PyDict Table(Rng r, string fn, PyDict common)
    {
        var args = new PyDict();
        switch (fn)
        {
            case "employee_period_fact_rows":
                args.Add("payroll", Many(r, 5, i => PayrollRow(r, i)));
                return Merge(args, common, "client_id", "program_code", "tax_year", "run_id");
            case "employee_eligibility_rows":
                var ids = Enumerable.Range(0, r.Pick(new[] { 0, 1, 2, 4, 8 })).Select(i => r.Chance(0.2) ? GoldPools.EmployeeId(r) : $"E{i}").ToList();
                args.Add("totals", ids.Select(i => (object?)Total(r, i)).ToList()).Add("averages", ids.Where(_ => r.Chance(0.8)).Select(i => (object?)Average(r, i)).ToList());
                return Merge(args, common, "client_id", "program_code", "tax_year", "method", "run_id");
            case "onezero_matrix_rows":
                args.Add("matrix", Many(r, 6, i => MatrixRow(r, i)));
                return Merge(args, common, "client_id", "program_code", "tax_year", "method", "run_id");
            default:
                args.Add("summary", Many(r, 5, i => SummaryRow(r, i)))
                    .Add("unreachable", Enumerable.Range(0, 12).Where(_ => r.Chance(0.15)).Select(i => (object?)(long)i).Concat(r.Chance(0.1) ? [(object?)12L, -1L] : []).ToList());
                return Merge(args, common, "client_id", "tax_year", "method", "run_id");
        }
    }

    private static PyDict Merge(PyDict args, PyDict common, params string[] keys)
    {
        foreach (var k in keys)
        {
            args.Add(k, common[k]);
        }

        return args;
    }

    /// <summary>The arguments of one <c>calculation_id</c> call: a base request with a few inputs swapped for edge values.</summary>
    public static PyDict CalculationId(Rng r)
    {
        var floors = new PyDict().Add("minimum_average_weekly_hours", 35.0).Add("minimum_average_weekly_wages_usd", 636.0).Add("source", "rules/ga_jtc/2023.json");
        var variants = new (string Key, Func<object?> Make)[]
        {
            ("client_id", () => r.Pick(new object?[] { 1002L, null, BigInteger.Pow(10, 25), 1001L })),
            ("program_code", () => r.Pick(new object?[] { "NC_JTEC", string.Empty, "GA_JTC" })),
            ("tax_year", () => r.Pick(new object?[] { 2024L, "2023", 2023L, 0L })),
            ("window_begin", () => r.Pick(new object?[] { Pools.Date(new DateOnly(2023, 1, 2)), Pools.Dt("2023-01-01T05:06:07"), "2023-01-01", null, GoldPools.Day(r) })),
            ("window_end", () => r.Pick(new object?[] { Pools.Date(new DateOnly(2024, 2, 29)), Pools.Dt("2023-12-31T01:02:03.000004+00:00"), 20231231L, GoldPools.Day(r) })),
            ("floors", () => r.Pick(new object?[] { new PyDict(), new PyDict().Add("source", null), floors.Aggregate(new PyDict(), (d, kv) => d.Add(kv.Key, kv.Key == "minimum_average_weekly_hours" ? GoldPools.Dec(r) : kv.Value)) })),
            ("assumption_ids", () => r.Pick(new object?[] { new List<object?>(), new List<object?> { "a", "b" }, new List<object?> { "b", "a" }, new List<object?> { 7L }, new List<object?> { "a", null }, new List<object?> { "\ud800" }, new List<object?> { "a\0b" } })),
            ("rows", () => Many(r, 4, i => PayrollRow(r, i))),
        };
        var chosen = new Dictionary<string, object?>();
        for (var n = r.Int(0, 3); n > 0; n--)
        {
            var v = r.Pick(variants);
            chosen[v.Key] = v.Make();
        }
        var baseArgs = new Dictionary<string, object?>
        {
            ["client_id"] = 1001L,
            ["program_code"] = "GA_JTC",
            ["tax_year"] = 2023L,
            ["window_begin"] = Pools.Date(new DateOnly(2023, 1, 1)),
            ["window_end"] = Pools.Date(new DateOnly(2023, 12, 31)),
            ["floors"] = floors,
            ["assumption_ids"] = new List<object?> { "GDS-STEP1-2026-08-25-v8" },
            ["rows"] = new List<object?> { PayrollRow(r, 0) },
        };
        return baseArgs.Aggregate(new PyDict(), (d, kv) => d.Add(kv.Key, chosen.TryGetValue(kv.Key, out var v) ? v : kv.Value));
    }
}
