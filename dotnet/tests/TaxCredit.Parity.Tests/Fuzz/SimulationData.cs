using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>Payroll rows and rule packs for the simulation fuzz.</summary>
internal static class SimulationData
{
    private static readonly string[] Sites = ["GA_ATL", "GA_SAV", "TN_NASH", "GA_GA-016", "SC_COL", "TN_NASH_HQ"];
    private static readonly string[] StringHours = ["80", "2000.5", "abc", " 12 ", "1_0", string.Empty];

    /// <summary>The pack argument: a real pack (every state; Georgia in every authored year and some missing ones) or a hand-built spec.</summary>
    public static PyDict Pack(Rng r)
    {
        if (r.Chance(0.5))
        {
            var key = r.Pick(new[] { "GA", "GA", "GA", "TN", "SC", "NC", "CO", "FL", "OH", "VA", "NY" });
            var year = key == "GA" ? r.Pick(new object[] { 2019L, 2020L, 2021L, 2022L, 2023L, 2024L, 2025L, 2026L, 2018L, 2027L }) : 2025L;
            return new PyDict().Add("$pack", new PyDict().Add("key", key).Add("tax_year", year));
        }

        var spec = new PyDict().Add("min_weekly_hours", r.Chance(0.6) ? Pools.Around(r, r.Pick(new[] { 35.0, 32.5, 20.0, 37.5, 32.0 })) : r.Pick(new object[] { 0L, 0.0, 1e6, 0.00001, 123456.7, 1234567.0 }))
            .Add("min_weekly_wages", r.Chance(0.6) ? Pools.Around(r, r.Pick(new[] { 636.0, 700.25, 636.5, 680.0, 0.0 })) : r.Pick(new object[] { 0L, 1234567.891, 0.5, 1500.5, 1e15 }));
        if (r.Chance(0.25))
        {
            var lo = r.Pick(new object[] { 20.0, 20L, 24.5 });
            spec.Add("pt_band_hours", new List<object?> { lo, spec["min_weekly_hours"] }).Add("pt_weight", r.Pick(new object[] { 0.5, 0.25, 1.0 }));
        }

        if (r.Chance(0.15))
        {
            spec.Add("included_pay_codes", new List<object?> { "Regular" }).Add("citation", "demo");
        }

        return new PyDict().Add("$pack_spec", spec);
    }

    /// <summary>A small payroll: employees across a few sites with biweekly periods around the floors, a few damaged cells.</summary>
    public static List<object?> Rows(Rng r, int maxEmployees)
    {
        var rows = new List<object?>();
        var employees = r.Int(0, maxEmployees);
        var monthly = r.Chance(0.15);
        for (var e = 0; e < employees; e++)
        {
            var id = r.Chance(0.03) ? null : $"R{r.Int(0, Math.Max(1, employees - 1))}";
            var site = r.Pick(Sites);
            var periods = r.Int(1, monthly ? 12 : 6);
            for (var p = 0; p < periods; p++)
            {
                rows.Add(Row(r, id, site, p, monthly));
            }
        }

        return rows;
    }

    private static PyDict Row(Rng r, string? id, string site, int p, bool monthly)
    {
        DateOnly start;
        DateOnly end;
        if (monthly)
        {
            start = new DateOnly(2025, (p % 12) + 1, 1);
            end = start.AddMonths(1).AddDays(-1);
        }
        else
        {
            start = new DateOnly(2025, 1, 1).AddDays((14 * p) + r.Int(0, 3));
            end = start.AddDays(r.Pick(new[] { 6, 13, 13, 14, 27, 0, -1 }));
        }

        var hours = r.Pick(new object[] { 0.0, 10.0, 34.99, 35.0, 80.0, r.Uniform(0, 120), 72.82, 1e-9, 172.0, 68.0 });
        var wages = r.Pick(new object[] { 0.0, 100.0, 636.0, 2000.0, r.Uniform(0, 5000), 2061.19, 4300.0 });
        if (r.Chance(0.03))
        {
            hours = r.Pick(StringHours);
        }

        var row = new PyDict().Add("Employee_ID", id).Add("Worksite_ID", site).Add("Entity_FEIN", "58-1111111");
        row.Add("Pay_Period_Start", Pools.Iso(start)).Add("Pay_Period_End", Pools.Iso(end)).Add("Pay_Date", Pools.Iso(end))
            .Add("Hours_Worked", hours).Add("Gross_Wages", wages).Add("Pay_Code", "Regular");
        if (r.Chance(0.3))
        {
            row.Add("Job_Title", "HQ Staff");
        }

        return r.Chance(0.03) ? Drop(r, row) : row;
    }

    private static PyDict Drop(Rng r, PyDict row)
    {
        var key = r.Pick(new[] { "Employee_ID", "Pay_Period_Start", "Pay_Period_End", "Hours_Worked", "Gross_Wages", "Worksite_ID" });
        return row.Where(kv => kv.Key != key).Aggregate(new PyDict(), (d, kv) => d.Add(kv.Key, kv.Value));
    }
}
