using System.Numerics;
using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Gold;

/// <summary>
/// The attributes of a <c>TrancheYear</c> (or an open year's <c>SimpleNamespace</c> reading) that <c>unit_year_master_row</c> reads. Each is whatever
/// the Python attribute held (floats from the engine, an int from <c>round()</c>), because <c>_dec</c> and <c>_flag</c> accept any.
/// </summary>
/// <param name="NetNew">Net new jobs over the base.</param>
/// <param name="Threshold">The year's minimum net new.</param>
/// <param name="Qualified">Whether net new met the threshold (truthy test).</param>
/// <param name="EligibleJobs">Jobs claimable this year.</param>
/// <param name="NewJobsCreated">The increment over the prior high-water mark.</param>
/// <param name="HighWaterMark">The running maximum average.</param>
/// <param name="Backfilled">Whether the year re-qualified after a lapse (truthy test).</param>
/// <param name="AnnualCreditUsd">The stair-step claim (an int: Python <c>round(x)</c>).</param>
/// <param name="PerJobUsd">The rate the year was priced at; <c>null</c> when the attribute is absent or <c>None</c> (the row then falls back to the series rate).</param>
public sealed record StairView(
    object? NetNew,
    object? Threshold,
    object? Qualified,
    object? EligibleJobs,
    object? NewJobsCreated,
    object? HighWaterMark,
    object? Backfilled,
    object? AnnualCreditUsd,
    object? PerJobUsd)
{
    /// <summary>The reading of a real <see cref="TrancheYear"/> (the ported <c>tools/baseyear.py</c> type), each attribute with the type Python holds.</summary>
    /// <param name="year">The engine's year.</param>
    /// <returns>The view.</returns>
    public static StairView From(TrancheYear year)
    {
        ArgumentNullException.ThrowIfNull(year);
        return new StairView(
            year.NetNew, year.Threshold, year.Qualified, year.EligibleJobs, year.NewJobsCreated, PyNum.Tree(year.HighWaterMark), year.Backfilled,
            PyNum.IntTree(year.AnnualCreditUsd), year.PerJobUsd);
    }
}

/// <summary>One creation event of a <c>BaseYearResult</c>: a tranche opened in <paramref name="CreationYear"/>.</summary>
/// <param name="CreationYear">The year that opened the window.</param>
/// <param name="Jobs">The tranche size.</param>
/// <param name="PerJobUsd">The rate attached to the jobs when they were created.</param>
/// <param name="Installments">The <c>{year, jobs_maintained, credit_usd}</c> dictionaries.</param>
public sealed record TrancheEventView(object? CreationYear, object? Jobs, object? PerJobUsd, IReadOnlyList<PyDict> Installments)
{
    /// <summary>The view of a real <see cref="TrancheEvent"/>.</summary>
    /// <param name="tranche">The event.</param>
    /// <returns>The view.</returns>
    public static TrancheEventView From(TrancheEvent tranche)
    {
        ArgumentNullException.ThrowIfNull(tranche);
        return new TrancheEventView(tranche.CreationYear, tranche.Jobs, tranche.PerJobUsd, tranche.Installments.Select(i => i.ToDict()).ToList());
    }
}

/// <summary>The attributes of a <c>BaseYearResult</c> the Gold projections read.</summary>
/// <param name="BaseAverageHeadcount">The frozen base average.</param>
/// <param name="PerJobUsd">The series' fallback rate.</param>
/// <param name="TrancheYears">The benefit window in years (passed through unchanged).</param>
/// <param name="BaseYearOverridden">Whether a human chose the base average (truthy test).</param>
/// <param name="HighWaterMarkOverridden">Whether a human seeded the high-water mark (truthy test).</param>
/// <param name="TrancheEvents">The creation events.</param>
public sealed record BaseYearView(
    object? BaseAverageHeadcount,
    object? PerJobUsd,
    object? TrancheYears,
    object? BaseYearOverridden,
    object? HighWaterMarkOverridden,
    IReadOnlyList<TrancheEventView> TrancheEvents)
{
    /// <summary>The view of a real <see cref="BaseYearResult"/> (the ported <c>BaseYearResult</c>), each attribute with the type Python holds.</summary>
    /// <param name="result">The engine result.</param>
    /// <returns>The view.</returns>
    public static BaseYearView From(BaseYearResult result)
    {
        ArgumentNullException.ThrowIfNull(result);
        return new BaseYearView(
            PyNum.Tree(result.BaseAverageHeadcount), PyNum.Tree(result.PerJobUsd), result.TrancheYears, result.BaseYearOverridden, result.HighWaterMarkOverridden,
            result.TrancheEvents.Select(TrancheEventView.From).ToList());
    }
}

/// <summary>The identity, label and provenance arguments of <c>unit_year_master_row</c> that the credit layer does not compute.</summary>
/// <param name="ClientId">The client.</param>
/// <param name="WorksiteId">The unit.</param>
/// <param name="EntityFein">The single FEIN the unit hosts, or <c>null</c>.</param>
/// <param name="ProgramCode">The programme.</param>
/// <param name="Method">The method name.</param>
/// <param name="TaxYear">The tax year.</param>
/// <param name="BaseYear">The frozen base year.</param>
/// <param name="BaseYearSource"><c>inferred</c> or <c>override</c>.</param>
/// <param name="MonthsReachable">The months a pay period reaches.</param>
/// <param name="Declined">Whether the year was declined.</param>
/// <param name="DeclineReason">Why, or <c>null</c>.</param>
/// <param name="ThresholdSource"><c>designation</c> or <c>rule_pack</c>.</param>
/// <param name="Status">The status label.</param>
/// <param name="Tier">The tier, or <c>null</c>: whatever the registry held (an int in production, though the Python annotation says <c>str</c>).</param>
/// <param name="Designation">The designation, or <c>null</c>; passed through unchanged like the tier.</param>
/// <param name="TierSource"><c>prototype</c> or <c>unassigned</c>.</param>
/// <param name="RunId">The run.</param>
public sealed record UnitYearKey(
    BigInteger ClientId,
    string WorksiteId,
    string? EntityFein,
    string ProgramCode,
    string Method,
    BigInteger TaxYear,
    BigInteger BaseYear,
    string BaseYearSource,
    BigInteger MonthsReachable,
    bool Declined,
    string? DeclineReason,
    string ThresholdSource,
    string Status,
    object? Tier,
    object? Designation,
    string TierSource,
    string RunId);
