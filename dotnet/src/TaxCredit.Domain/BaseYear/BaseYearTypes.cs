using System.Numerics;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.BaseYear;

/// <summary>
/// One year in the stair-step net-new-vs-frozen-base evaluation (Python <c>tools/baseyear.py</c> <c>TrancheYear</c>). Field order is the dataclass's.
/// </summary>
/// <param name="Year">The tax year.</param>
/// <param name="AverageHeadcount">The One/Zero Average Headcount.</param>
/// <param name="BaseAverageHeadcount">The frozen base; an int when a caller overrode it with one (Python keeps the type).</param>
/// <param name="NetNew"><c>max(0, avg - base)</c>.</param>
/// <param name="Threshold">The minimum new jobs that applied to this year.</param>
/// <param name="Qualified">Whether net new met the threshold (and is positive).</param>
/// <param name="EligibleJobs">Net new if qualified else 0.</param>
/// <param name="HighWaterMark">The running maximum average through this year; an int when the seed was one.</param>
/// <param name="NewJobsCreated">The increment over the prior high-water mark.</param>
/// <param name="Backfilled">Re-qualified after a non-qualifying year.</param>
/// <param name="AnnualCreditUsd">The stair-step claim: Python <c>round(eligible_jobs * rate)</c>, an int.</param>
/// <param name="PerJobUsd">The rate THIS year was priced at (statute is versioned by tax year, ADR-005).</param>
public sealed record TrancheYear(
    long Year,
    double AverageHeadcount,
    PyNumber BaseAverageHeadcount,
    double NetNew,
    double Threshold,
    bool Qualified,
    double EligibleJobs,
    PyNumber HighWaterMark,
    double NewJobsCreated,
    bool Backfilled,
    BigInteger AnnualCreditUsd,
    double PerJobUsd)
{
    /// <summary>Every field unrounded, in the dataclass's field order (what <c>dataclasses.fields</c> shows).</summary>
    /// <returns>The tree.</returns>
    public PyDict ToFields() => new PyDict()
        .Add("year", Year).Add("average_headcount", AverageHeadcount).Add("base_average_headcount", PyNum.Tree(BaseAverageHeadcount))
        .Add("net_new", NetNew).Add("threshold", Threshold).Add("qualified", Qualified).Add("eligible_jobs", EligibleJobs)
        .Add("high_water_mark", PyNum.Tree(HighWaterMark)).Add("new_jobs_created", NewJobsCreated).Add("backfilled", Backfilled)
        .Add("annual_credit_usd", PyNum.IntTree(AnnualCreditUsd)).Add("per_job_usd", PerJobUsd);

    /// <summary>Python <c>TrancheYear.to_dict()</c>: the headcount fields rounded to two places, the rest as stored.</summary>
    /// <returns>The tree.</returns>
    public PyDict ToDict() => new PyDict()
        .Add("year", Year)
        .Add("average_headcount", PyRound.Round(AverageHeadcount, 2))
        .Add("base_average_headcount", PyNum.Tree(PyNum.Round2(BaseAverageHeadcount)))
        .Add("net_new", PyRound.Round(NetNew, 2))
        .Add("threshold", Threshold)
        .Add("qualified", Qualified)
        .Add("eligible_jobs", PyRound.Round(EligibleJobs, 2))
        .Add("high_water_mark", PyNum.Tree(PyNum.Round2(HighWaterMark)))
        .Add("new_jobs_created", PyRound.Round(NewJobsCreated, 2))
        .Add("backfilled", Backfilled)
        .Add("annual_credit_usd", PyNum.IntTree(AnnualCreditUsd))
        .Add("per_job_usd", PerJobUsd);
}

/// <summary>One installment of a tranche: the dict <c>{year, jobs_maintained, credit_usd}</c> Python builds.</summary>
/// <param name="Year">The installment year.</param>
/// <param name="JobsMaintained">Jobs still maintained, rounded to two places.</param>
/// <param name="CreditUsd">Python <c>round(jobs_maintained * per_job_usd)</c>, an int.</param>
public sealed record Installment(long Year, double JobsMaintained, BigInteger CreditUsd)
{
    /// <summary>The installment as Python's dict.</summary>
    /// <returns>The tree.</returns>
    public PyDict ToDict() => new PyDict().Add("year", Year).Add("jobs_maintained", JobsMaintained).Add("credit_usd", PyNum.IntTree(CreditUsd));
}

/// <summary>
/// A job-creation event in <paramref name="CreationYear"/>, claimable over a window (Python <c>TrancheEvent</c>). It holds the rate of the year it OPENED.
/// </summary>
/// <param name="CreationYear">The year that opened the window.</param>
/// <param name="Jobs">New jobs created that year (the tranche size).</param>
/// <param name="PerJobUsd">The rate attached to the jobs when they were created; a later year never reprices it.</param>
/// <param name="TrancheYears">The window length in years (passed through unchanged).</param>
/// <param name="Installments">One entry per year of the window.</param>
public sealed record TrancheEvent(long CreationYear, double Jobs, double PerJobUsd, long TrancheYears, IReadOnlyList<Installment> Installments)
{
    /// <summary>Python <c>lifetime_usd</c>: the exact integer sum of the installments' credits.</summary>
    public BigInteger LifetimeUsd => Installments.Aggregate(BigInteger.Zero, (sum, i) => sum + i.CreditUsd);

    /// <summary>Every field in the dataclass's order.</summary>
    /// <returns>The tree.</returns>
    public PyDict ToFields() => new PyDict()
        .Add("creation_year", CreationYear).Add("jobs", Jobs).Add("per_job_usd", PerJobUsd).Add("tranche_years", TrancheYears)
        .Add("installments", Installments.Select(i => (object?)i.ToDict()).ToList());

    /// <summary>Python <c>TrancheEvent.to_dict()</c>.</summary>
    /// <returns>The tree.</returns>
    public PyDict ToDict() => new PyDict()
        .Add("creation_year", CreationYear)
        .Add("jobs", PyRound.Round(Jobs, 2))
        .Add("per_job_usd", PerJobUsd)
        .Add("tranche_years", TrancheYears)
        .Add("window", new List<object?> { CreationYear, CreationYear + TrancheYears - 1 })
        .Add("installments", Installments.Select(i => (object?)i.ToDict()).ToList())
        .Add("lifetime_usd", PyNum.IntTree(LifetimeUsd));
}

/// <summary>The result of the frozen-base-year evaluation (Python <c>BaseYearResult</c>).</summary>
/// <param name="State">The upper-cased state code.</param>
/// <param name="BaseYear">The frozen base year.</param>
/// <param name="BaseAverageHeadcount">The base average (an int when overridden with one).</param>
/// <param name="Threshold">The caller's threshold, unchanged (an int stays an int).</param>
/// <param name="PerJobUsd">The caller's rate, unchanged.</param>
/// <param name="TrancheYears">The window length, unchanged.</param>
/// <param name="BaseYearOverridden">Whether a base average override was supplied.</param>
/// <param name="HighWaterMarkOverridden">Whether a high-water-mark seed was supplied.</param>
/// <param name="Years">The evaluated years, ascending.</param>
/// <param name="TrancheEvents">The tranches opened.</param>
/// <param name="FinalHighWaterMark">The running maximum after the last year.</param>
public sealed record BaseYearResult(
    string State,
    long BaseYear,
    PyNumber BaseAverageHeadcount,
    PyNumber Threshold,
    PyNumber PerJobUsd,
    long TrancheYears,
    bool BaseYearOverridden,
    bool HighWaterMarkOverridden,
    IReadOnlyList<TrancheYear> Years,
    IReadOnlyList<TrancheEvent> TrancheEvents,
    PyNumber FinalHighWaterMark)
{
    /// <summary>Python <c>total_annual_credit_usd</c>: the exact sum of the per-year claims.</summary>
    public BigInteger TotalAnnualCreditUsd => Years.Aggregate(BigInteger.Zero, (sum, y) => sum + y.AnnualCreditUsd);

    /// <summary>Python <c>total_tranche_lifetime_usd</c>: the forecast ceiling, the sum of every tranche's lifetime.</summary>
    public BigInteger TotalTrancheLifetimeUsd => TrancheEvents.Aggregate(BigInteger.Zero, (sum, e) => sum + e.LifetimeUsd);

    /// <summary>Every field unrounded in dataclass order (the golden's <c>result</c>).</summary>
    /// <returns>The tree.</returns>
    public PyDict ToFields() => new PyDict()
        .Add("state", State).Add("base_year", BaseYear).Add("base_average_headcount", PyNum.Tree(BaseAverageHeadcount))
        .Add("threshold", PyNum.Tree(Threshold)).Add("per_job_usd", PyNum.Tree(PerJobUsd)).Add("tranche_years", TrancheYears)
        .Add("base_year_overridden", BaseYearOverridden).Add("high_water_mark_overridden", HighWaterMarkOverridden)
        .Add("years", Years.Select(y => (object?)y.ToFields()).ToList())
        .Add("tranche_events", TrancheEvents.Select(e => (object?)e.ToFields()).ToList())
        .Add("final_high_water_mark", PyNum.Tree(FinalHighWaterMark));

    /// <summary>Python <c>BaseYearResult.to_dict()</c>.</summary>
    /// <returns>The tree.</returns>
    public PyDict ToDict() => new PyDict()
        .Add("_roadmap_tag", "L1").Add("_story", "CALC-07").Add("_prototype_verify", true).Add("_disc_ref", BaseYearEngine.DiscRef)
        .Add("state", State).Add("base_year", BaseYear)
        .Add("base_average_headcount", PyNum.Tree(PyNum.Round2(BaseAverageHeadcount)))
        .Add("threshold", PyNum.Tree(Threshold)).Add("per_job_usd", PyNum.Tree(PerJobUsd)).Add("tranche_years", TrancheYears)
        .Add("base_year_overridden", BaseYearOverridden).Add("high_water_mark_overridden", HighWaterMarkOverridden)
        .Add("years", Years.Select(y => (object?)y.ToDict()).ToList())
        .Add("tranche_events", TrancheEvents.Select(e => (object?)e.ToDict()).ToList())
        .Add("final_high_water_mark", PyNum.Tree(PyNum.Round2(FinalHighWaterMark)))
        .Add("total_annual_credit_usd", PyNum.IntTree(TotalAnnualCreditUsd))
        .Add("total_tranche_lifetime_usd", PyNum.IntTree(TotalTrancheLifetimeUsd));
}

/// <summary>One entry of <c>benefit_by_year</c>: <c>{threshold, per_job_usd}</c> where either key may be absent (the scalar then applies).</summary>
/// <param name="Threshold">The year's threshold, or <c>null</c> when the key is absent.</param>
/// <param name="PerJobUsd">The year's rate, or <c>null</c> when the key is absent.</param>
public sealed record YearBenefit(PyNumber? Threshold, PyNumber? PerJobUsd);

/// <summary>The scalar and optional arguments of <c>compute_base_year_tranches</c> (everything except the state, the series and the base year).</summary>
/// <param name="Threshold">The designation's <c>minimum_new_jobs</c> (the fallback for a year absent from <paramref name="BenefitByYear"/>).</param>
/// <param name="PerJobUsd">Statutory dollars per qualifying job (the fallback rate).</param>
/// <param name="TrancheYears">The benefit window per creation event (GA = 5).</param>
/// <param name="BaseAverageOverride">A negotiated base replacing the base year's headcount (DISC-8).</param>
/// <param name="HighWaterMarkOverride">A seed for the persistent high-water mark (DISC-9).</param>
/// <param name="BenefitByYear">Per-year statute; a year absent from it falls back to the scalars, never to a neighbouring year.</param>
public sealed record BaseYearSettings(
    PyNumber Threshold,
    PyNumber PerJobUsd,
    long TrancheYears = BaseYearEngine.DefaultTrancheYears,
    PyNumber? BaseAverageOverride = null,
    PyNumber? HighWaterMarkOverride = null,
    OrderedMap<long, YearBenefit>? BenefitByYear = null);
