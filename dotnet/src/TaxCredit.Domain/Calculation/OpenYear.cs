using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>The closed-series facts an open year is read against (the attributes <c>open_year_reading</c> takes from Python's <c>trend</c> object).</summary>
/// <param name="BaseAverageHeadcount">The base year's average headcount (anything Python's <c>float()</c> accepts).</param>
/// <param name="FinalHighWaterMark">The high-water mark of the closed series.</param>
/// <param name="PerJobUsd">The per-job credit, used when the statute names none.</param>
public sealed record OpenYearTrend(object? BaseAverageHeadcount, object? FinalHighWaterMark, object? PerJobUsd);

/// <summary>Where an open year stands against the base (the <c>SimpleNamespace</c> <c>open_year_reading</c> returns). Nothing is priced until the year closes.</summary>
/// <param name="AverageHeadcount">The average over the closed months.</param>
/// <param name="BaseAverageHeadcount">The base year's average.</param>
/// <param name="NetNew">Net new to date, never negative.</param>
/// <param name="Threshold">The year's minimum net new.</param>
/// <param name="Qualified">The on-track reading: net new meets the threshold and is above zero.</param>
/// <param name="EligibleJobs">Always zero: nothing is claimable until the year closes.</param>
/// <param name="NewJobsCreated">Always zero.</param>
/// <param name="HighWaterMark">The larger of the closed series' mark and this year's average.</param>
/// <param name="Backfilled">Always false.</param>
/// <param name="AnnualCreditUsd">Always zero.</param>
/// <param name="PerJobUsd">The per-job credit.</param>
public sealed record OpenYearReading(
    double AverageHeadcount,
    double BaseAverageHeadcount,
    double NetNew,
    double Threshold,
    bool Qualified,
    double EligibleJobs,
    double NewJobsCreated,
    double HighWaterMark,
    bool Backfilled,
    double AnnualCreditUsd,
    double PerJobUsd)
{
    /// <summary>The reading as the ordered attribute dictionary Python's <c>vars()</c> shows.</summary>
    /// <returns>An ordered tree.</returns>
    public PyDict ToDict() => new PyDict()
        .Add("average_headcount", AverageHeadcount)
        .Add("base_average_headcount", BaseAverageHeadcount)
        .Add("net_new", NetNew)
        .Add("threshold", Threshold)
        .Add("qualified", Qualified)
        .Add("eligible_jobs", EligibleJobs)
        .Add("new_jobs_created", NewJobsCreated)
        .Add("high_water_mark", HighWaterMark)
        .Add("backfilled", Backfilled)
        .Add("annual_credit_usd", AnnualCreditUsd)
        .Add("per_job_usd", PerJobUsd);
}

/// <summary>
/// Is a tax year still open? One answer, used everywhere a year is priced (Python <c>application/open_year.py</c>). An open year is read
/// on its closed months, is never claimed, and is never fed into the priced credit series until it closes.
/// </summary>
public static class OpenYear
{
    /// <summary>The fewest closed months an open year is read on (Python <c>MIN_OPEN_MONTHS</c>); fewer is too early to state a pace.</summary>
    public const long MinOpenMonths = 3;

    /// <summary>Python <c>today()</c>: the one clock read in the module (local time, like <c>date.today()</c>). Callers pass their own clock to pin it.</summary>
    /// <returns>Today's local date.</returns>
    public static DateOnly Today() => DateOnly.FromDateTime(DateTime.Now);

    /// <summary>Python <c>is_open</c>: true while the fiscal window ending <paramref name="windowEnd"/> is still running (it ends after the day it is judged on).</summary>
    /// <param name="windowEnd">A <see cref="DateOnly"/>, or any value whose <c>str()</c> starts with an ISO date (text, <c>null</c> and numbers raise like Python).</param>
    /// <param name="on">The day to judge on; <paramref name="today"/> when omitted.</param>
    /// <param name="today">The clock for the default day; <see cref="Today"/> when omitted.</param>
    /// <returns>Whether the window is open.</returns>
    /// <exception cref="PyValueError">When the text is not an ISO date.</exception>
    public static bool IsOpen(object? windowEnd, DateOnly? on = null, Func<DateOnly>? today = null)
    {
        var end = windowEnd is DateOnly d ? d : PyDate.FromIsoFormat(PyStr.Prefix(ProximityCoerce.Str(windowEnd), 10));
        return end > (on ?? (today ?? Today)());
    }

    /// <summary>
    /// Python <c>open_year_reading</c>: where an open year stands against the base, read on its closed months. <c>qualified</c> is the
    /// on-track reading, net new to date against the minimum. Conversions follow Python's <c>float()</c> in Python's evaluation order,
    /// so the first bad value decides which exception is raised.
    /// </summary>
    /// <param name="averageHeadcount">The average over the closed months; a falsy value reads as 0.0.</param>
    /// <param name="trend">The closed series' base, high-water mark and per-job credit.</param>
    /// <param name="statute">The year's statute values (<c>threshold</c> and <c>per_job_usd</c> are read when present).</param>
    /// <param name="threshold">The threshold used when the statute carries none.</param>
    /// <returns>The reading.</returns>
    public static OpenYearReading Reading(object? averageHeadcount, OpenYearTrend trend, PyDict statute, object? threshold)
    {
        ArgumentNullException.ThrowIfNull(trend);
        ArgumentNullException.ThrowIfNull(statute);
        var average = ProximityCoerce.Truthy(averageHeadcount) ? ProximityCoerce.ToFloat(averageHeadcount) : 0.0;
        var netNew = PyArith.Max(0.0, average - ProximityCoerce.ToFloat(trend.BaseAverageHeadcount));
        var yearThreshold = ProximityCoerce.ToFloat(statute.TryGetValue("threshold", out var t) ? t : threshold);
        var baseAverage = ProximityCoerce.ToFloat(trend.BaseAverageHeadcount);
        var highWater = PyArith.Max(ProximityCoerce.ToFloat(trend.FinalHighWaterMark), average);
        var perJobSource = statute.TryGetValue("per_job_usd", out var p) && ProximityCoerce.Truthy(p) ? p : trend.PerJobUsd;
        var perJob = ProximityCoerce.ToFloat(perJobSource);
        return new OpenYearReading(average, baseAverage, netNew, yearThreshold, netNew >= yearThreshold && netNew > 0, 0.0, 0.0, highWater, false, 0.0, perJob);
    }
}
