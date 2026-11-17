using System.Numerics;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>Argument builders for the credit-layer Gold rows: the unit-year master (stair, trend, unit year), the credit installments, and the run summary.</summary>
internal static class GoldCredit
{
    private static readonly object?[] MonthsWith = [null, 11L, 12L, 13L, 0L, -1L, 11.999, 12.0, 12.0000001, true, false, "12", 11.5, double.NaN, double.PositiveInfinity, 12L];

    private static PyDict Stair(Rng r)
    {
        var d = new PyDict();
        // Every attribute of a TrancheYear exists in production, so only the open-year reading's missing per_job_usd (a getattr default) is modelled as absent.
        void Num(string k, object ordinary) => _ = k == "per_job_usd" && r.Chance(0.05) ? d : d.Add(k, r.Chance(0.12) ? GoldPools.Dec(r) : ordinary);
        void Flag(string k, bool v) => _ = d.Add(k, r.Chance(0.1) ? GoldPools.Flag(r) : v);
        Num("year", 2024L);
        Num("average_headcount", Math.Round(r.Uniform(0, 80), 2));
        Num("base_average_headcount", Math.Round(r.Uniform(0, 60), 2));
        Num("net_new", Math.Round(r.Uniform(-5, 30), 3));
        Num("threshold", r.Pick(new object[] { 2.0, 5.0, 10.0, 2L }));
        Flag("qualified", r.Chance(0.6));
        Num("eligible_jobs", Math.Round(r.Uniform(0, 30), 3));
        Num("high_water_mark", Math.Round(r.Uniform(0, 80), 2));
        Num("new_jobs_created", Math.Round(r.Uniform(0, 30), 3));
        Flag("backfilled", r.Chance(0.2));
        Num("annual_credit_usd", r.Pick(new object[] { 43750L, 0L, 17500.5, 66500L }));
        Num("per_job_usd", r.Pick(new object[] { 3500.0, 3500L, 4000.0, 1500.5, 0.0 }));
        return d;
    }

    private static PyDict Event(Rng r)
    {
        var installments = Enumerable.Range(0, r.Pick(new[] { 0, 1, 2, 3, 5 })).Select(i =>
        {
            var inst = new PyDict();
            if (!r.Chance(0.03))
            {
                inst.Add("year", r.Chance(0.05) ? r.Pick(new object?[] { "2024", null }) : 2024L + i);
            }

            if (!r.Chance(0.03))
            {
                inst.Add("jobs_maintained", r.Chance(0.12) ? GoldPools.Dec(r) : Math.Round(r.Uniform(0, 30), 3));
            }

            if (!r.Chance(0.03))
            {
                inst.Add("credit_usd", r.Chance(0.12) ? GoldPools.Dec(r) : r.Pick(new object[] { 43750L, 17500.5, 0L }));
            }

            return (object?)inst;
        }).ToList();
        return new PyDict().Add("creation_year", 2024L).Add("jobs", r.Chance(0.12) ? GoldPools.Dec(r) : Math.Round(r.Uniform(0, 30), 3))
            .Add("per_job_usd", r.Chance(0.12) ? GoldPools.Dec(r) : r.Pick(new object[] { 3500.0, 4000.0, 1500.5 })).Add("tranche_years", 5L).Add("installments", installments);
    }

    private static PyDict Trend(Rng r) => new PyDict()
        .Add("base_average_headcount", r.Chance(0.12) ? GoldPools.Dec(r) : Math.Round(r.Uniform(0, 60), 2))
        .Add("per_job_usd", r.Chance(0.1) ? r.Pick(new object?[] { null, 0.0, 3500.5 }) : 3500.0)
        .Add("tranche_years", r.Pick(new object?[] { 5L, 5L, 3L, 1L, 0L, null, "5", BigInteger.Pow(10, 20) }))
        .Add("base_year_overridden", r.Chance(0.2) ? GoldPools.Flag(r) : r.Chance(0.5)).Add("high_water_mark_overridden", r.Chance(0.2) ? GoldPools.Flag(r) : r.Chance(0.5))
        .Add("tranche_events", Enumerable.Range(0, r.Pick(new[] { 0, 1, 2, 3 })).Select(_ => (object?)Event(r)).ToList());

    private static object? Stamp(Rng r) => r.Chance(0.8) ? Pools.DateTimeTag(r) : r.Pick(new object?[] { Pools.Dt("2026-03-01T09:30:15"), Pools.Dt("2026-03-01T09:30:15.250000"), Pools.Dt("2026-03-01T09:30:15+00:00") });

    private static PyDict Key(Rng r)
    {
        var ty = r.Pick(new object[] { 2024L, 2023L, 2022L, 2025L });
        return new PyDict().Add("client_id", r.Pick(new object[] { 1001L, 1001L, 2000L, BigInteger.Pow(10, 20) }))
            .Add("worksite_id", r.Pick(new[] { "GA_1", "GA_\u00e9\u4e2d", string.Empty, "TN_2" })).Add("entity_fein", r.Pick(new[] { "58-1234567", null, string.Empty }))
            .Add("program_code", r.Pick(new[] { "GA_JTC", string.Empty, "NC_JTEC" })).Add("method", r.Pick(new[] { "min_max", "pay_period" })).Add("tax_year", ty)
            .Add("base_year", r.Pick(new object[] { 2023L, 2022L, 2024L, 2021L })).Add("base_year_source", r.Pick(new[] { "inferred", "override", string.Empty, "Override" }))
            .Add("months_reachable", r.Pick(new object[] { 12L, 12L, 11L, 0L, 1L, 13L, -1L })).Add("declined", r.Chance(0.15)).Add("decline_reason", r.Chance(0.15) ? "under half" : null)
            .Add("threshold_source", r.Pick(new[] { "rule_pack", "designation" })).Add("status", r.Pick(new[] { "qualified", "in_progress", "no_credit" }))
            .Add("tier", r.Pick(new[] { "T1", null })).Add("designation", r.Pick(new[] { "T1B40", null })).Add("tier_source", r.Pick(new[] { "prototype", "unassigned" })).Add("run_id", r.Pick(new[] { "R1", "R9" }));
    }

    /// <summary>One <c>unit_year_master_row</c> call.</summary>
    public static PyDict MasterRow(Rng r)
    {
        var args = Key(r);
        args.Add("stair", r.Chance(0.06) ? null : Stair(r)).Add("trend", Trend(r));
        var unitYear = new PyDict();
        if (!r.Chance(0.05))
        {
            unitYear.Add("average_headcount", r.Chance(0.2) ? GoldPools.Dec(r) : Math.Round(r.Uniform(0, 80), 2));
        }

        if (!r.Chance(0.05))
        {
            unitYear.Add("months_with_headcount", r.Chance(0.5) ? r.Pick(MonthsWith) : (long)r.Int(1, 12));
        }

        return args.Add("unit_year", unitYear).Add("appended_at", Stamp(r));
    }

    /// <summary>One <c>unit_credit_installment_rows</c> call.</summary>
    public static PyDict Installments(Rng r) => new PyDict().Add("trend", Trend(r))
        .Add("years_with_data", Enumerable.Range(0, r.Pick(new[] { 0, 1, 3, 4 })).Select(i => (object?)(2023L + i)).ToList()).Add("appended_at", Stamp(r))
        .Add("client_id", 1001L).Add("worksite_id", r.Pick(new[] { "GA_1", "GA_\u00e9" })).Add("program_code", "GA_JTC").Add("method", r.Pick(new[] { "min_max", "pay_period" })).Add("run_id", "R1");

    /// <summary>One <c>run_method_summary_row</c> call on top of the shared identity fields.</summary>
    public static PyDict RunSummary(Rng r, PyDict common)
    {
        var flag = new PyDict().Add("type", "multi_unit_double_count").Add("employee_id", "E1").Add("month_index", 3L).Add("count", 2L);
        var flags = r.Pick(new object?[] { new List<object?>(), new List<object?> { flag }, new List<object?> { flag, flag, new PyDict().Add("type", "over_53_weeks").Add("employee_id", "E2").Add("weeks", 54.5) },
            null, new List<object?> { new PyDict().Add("employee_id", "E1") }, new List<object?> { new PyDict().Add("type", null) }, new List<object?> { new PyDict().Add("type", "multi_unit_double_count ") } });
        var months = r.Pick(new object?[]
        {
            new List<object?> { Pools.Date(new DateOnly(2023, 8, 28)), Pools.Date(new DateOnly(2023, 9, 30)) }, new List<object?>(), new List<object?> { Pools.Dt("2023-08-28T01:02:03"), Pools.Date(new DateOnly(2023, 9, 30)) },
            new List<object?> { Pools.Dt("2023-08-28T01:02:03.000500+00:00") }, new List<object?> { "2023-08-28" }, new List<object?> { null }, new List<object?> { 20230828L }, Enumerable.Range(0, 12).Select(i => (object?)Pools.Date(new DateOnly(2023, 1, 1).AddMonths(i))).ToList(),
        });
        var result = new PyDict().Add("annual_average", r.Chance(0.3) ? GoldPools.Dec(r) : Math.Round(r.Uniform(0, 900), r.Int(0, 5))).Add("n_eligible", (long)r.Int(0, 900)).Add("n_totals", (long)r.Int(0, 3000))
            .Add("n_matrix", (long)r.Int(0, 4000)).Add("flags", flags).Add("months", months);
        var args = new PyDict().Add("result", result);
        foreach (var (k, v) in common)
        {
            args.Add(k, v);
        }

        return args.Add("unit_fein_rows", r.Pick(new object[] { 0L, 101L, BigInteger.Pow(10, 20) })).Add("appended_at", Stamp(r));
    }
}
