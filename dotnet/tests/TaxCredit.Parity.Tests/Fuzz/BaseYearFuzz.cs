using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Differential fuzz of <c>tools/baseyear.compute_base_year_tranches</c> (and <c>tranche_columns</c> over its result): yearly headcounts that straddle the
/// threshold, ties at half a job, gaps and shuffled years, per-year <c>benefit_by_year</c> overrides, base-average and high-water-mark overrides, and
/// non-finite or mistyped numbers. Arguments use the exporter's pair-list encoding of the two mappings.
/// </summary>
internal sealed class BaseYearFuzz : FuzzFamily
{
    private static readonly object[] Thresholds = [2L, 2.0, 5.0, 10L, 0.5, 0L, 15.5, -1.0, 1e-9, double.NaN, double.PositiveInfinity, 2.5, 3L];
    private static readonly object[] PerJob = [3500L, 3500.0, 4000.0, 1500.5, 0.0, 2999.99, -3500L, 1e16, 1e300, 0.001, double.NaN, double.PositiveInfinity, 3501L, 7L, 1L, 4100L];
    private static readonly object?[] TrancheYearsPool = [null, null, null, 5L, 3L, 1L, 4L, 6L, 0L, 2L, 7L, 10L, -1L];
    private static readonly object?[] Overrides = [null, null, null, null, 12.5, 40L, 80.0, 0L, 99.999, -5L, 1e9, double.NaN, double.PositiveInfinity, 105L, 30.0, 45L, 60.5, 100.0];
    private static readonly string[] States = ["GA", "GA", "ga", "NC", "sc", string.Empty, "Stra\u00dfe", "\u01c6a", "\U00010428x"];

    public override string Name => "baseyear";

    public override IReadOnlyList<string> Functions { get; } = ["compute_base_year_tranches", "tranche_columns"];

    public override Func<PyDict, string?> CreateChecker() => call => Replay(call, BaseYearInvoke.Invoke);

    public override FamilyCase Generate(Rng r, string id)
    {
        var baseYear = r.Chance(0.04) ? r.Pick(new[] { 0L, -3L, 1L << 40 }) : r.Int(2015, 2024);
        var args = Compute(r, baseYear);
        if (!r.Chance(0.3))
        {
            return new FamilyCase(id, "compute_base_year_tranches", args);
        }

        var span = args["tranche_years"] is long t ? t : 5L;
        var years = Enumerable.Range(0, (int)Math.Clamp(Math.Max(span, 0) + 4, 0, 14)).Select(i => (object?)(baseYear - 1 + i)).ToList();
        if (r.Chance(0.3) && years.Count > 3)
        {
            years = [years[2], years[0], years[2], years[^1], years[1]];
        }

        return new FamilyCase(id, "tranche_columns", args.Add("years", years));
    }

    private static PyDict Compute(Rng r, long baseYear)
    {
        var threshold = r.Pick(Thresholds);
        var gridStep = r.Pick(new[] { 0.5, 0.25, 1.0, 0.125, 0.01 });
        var baseAvg = r.Pick(new[] { 40.0, 100.0, 0.0, 12.5, r.Uniform(0, 90) });
        var years = Enumerable.Range((int)baseYear - r.Int(0, 2), r.Int(1, 9)).Where(y => y == baseYear || r.Chance(0.88)).Select(y => (long)y).Append(baseYear).Distinct().OrderBy(_ => r.Int(0, 1 << 20)).ToList();
        var yearly = years.Select(y => (object?)new List<object?> { y, Headcount(r, baseAvg, y - baseYear, gridStep, threshold) }).ToList();
        object? benefit = null;
        if (r.Chance(0.5))
        {
            benefit = Enumerable.Range((int)baseYear - 1, r.Int(1, 10)).Where(_ => r.Chance(0.8)).Select(y => (object?)new List<object?> { (long)y, BenefitEntry(r) }).ToList();
        }

        return new PyDict().Add("state", r.Pick(States)).Add("yearly", yearly).Add("base_year", baseYear).Add("threshold", threshold).Add("per_job_usd", r.Pick(PerJob))
            .Add("tranche_years", r.Pick(TrancheYearsPool)).Add("base_average_override", r.Pick(Overrides)).Add("high_water_mark_override", r.Pick(Overrides)).Add("benefit", benefit)
            .Add("trail", r.Chance(0.3) ? new PyDict().Add("title", "Base-year trail").Add("citation", "GA JTC base-year mechanics") : null);
    }

    private static object? Headcount(Rng r, double baseAvg, long offset, double step, object threshold)
    {
        if (r.Chance(0.05))
        {
            return Pools.SpecialNumber(r);
        }

        var thr = threshold is long l ? l : threshold is double d && double.IsFinite(d) ? d : 2.0;
        return r.Int(0, 5) switch
        {
            0 => Pools.Around(r, baseAvg + thr),
            1 => Pools.Around(r, baseAvg + (thr * Math.Max(1, offset))),
            2 => Math.Round(baseAvg + (step * r.Int(-12, 24)), 3),
            3 => Math.Round(r.Uniform(0, 90), 2),
            4 => r.Pick(new object[] { 40L, 40.0, 40.005, 41.995, (long)r.Int(0, 99), 100L }),
            _ => Pools.Around(r, baseAvg),
        };
    }

    private static PyDict BenefitEntry(Rng r)
    {
        var d = new PyDict();
        if (r.Chance(0.9))
        {
            d.Add("threshold", r.Pick(Thresholds));
        }

        if (r.Chance(0.9))
        {
            d.Add("per_job_usd", r.Pick(PerJob));
        }

        return d;
    }
}
