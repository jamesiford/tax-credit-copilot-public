using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Domain.Trend;

/// <summary>
/// The pure helpers of Python <c>application/queries/get_unit_trend.py</c> that <c>run_client_calculation.py</c> imports
/// (<c>_MIN_REACHABLE_MONTHS</c>, <c>_candidate_years</c>, <c>_year_benefit</c>; <c>_designation_at</c> is
/// <see cref="Designations.DesignationRegistry.DesignationAt"/>).
/// </summary>
public static class UnitTrendQueryHelpers
{
    /// <summary>
    /// Python <c>_MIN_REACHABLE_MONTHS</c>: a twelve-month average needs enough measuring dates to be an average. Half is a judgement, not a statute; it sits
    /// far from both observed cases (1 of 12 and 11 of 12).
    /// </summary>
    public const int MinReachableMonths = 6;

    /// <summary>Python <c>_candidate_years</c>: the tax years a programme (or a state's default programme) has an authored rule pack for.</summary>
    /// <param name="library">The rule library (Python reads the rules directory).</param>
    /// <param name="stateOrProgram">A programme code or a state code.</param>
    /// <returns>The authored years, ascending; empty when there is no pack.</returns>
    public static IReadOnlyList<long> CandidateYears(RuleLibrary library, string stateOrProgram)
    {
        ArgumentNullException.ThrowIfNull(library);
        var packFile = library.PackFileFor(stateOrProgram);
        return string.IsNullOrEmpty(packFile) ? [] : library.AuthoredYears(packFile);
    }

    /// <summary>Python <c>_year_benefit</c>: the statutory threshold and per-job amount for one year (ADR-005).</summary>
    /// <param name="library">The rule library.</param>
    /// <param name="programCode">The programme code.</param>
    /// <param name="taxYear">The year; <c>null</c> resolves the latest authored year with <c>year_resolved</c> false.</param>
    /// <returns><c>{threshold, per_job_usd, benefit_period_years, year_resolved}</c> in that order.</returns>
    /// <exception cref="PyKeyError">For an unknown programme code.</exception>
    /// <exception cref="PyFileNotFoundError">For a year with no authored pack.</exception>
    public static PyDict YearBenefit(RuleLibrary library, string programCode, long? taxYear)
    {
        ArgumentNullException.ThrowIfNull(library);
        var packFile = library.CodeToPack[programCode];
        var (pack, yearResolved) = library.LoadYearPack(packFile, taxYear);
        var benefit = Dict(pack, "benefit");
        var threshold = Dict(pack, "thresholds");
        return new PyDict()
            .Add("threshold", FloatOr(Get(threshold, "minimum_new_jobs"), 0.0))
            .Add("per_job_usd", FloatOr(Get(benefit, "amount_per_qualifying_job_usd"), 0.0))
            .Add("benefit_period_years", Years(Get(benefit, "benefit_period_years")))
            .Add("year_resolved", yearResolved);
    }

    private static object? Get(PyDict d, string key) => d.TryGetValue(key, out var v) ? v : null;

    /// <summary>Python <c>pack.get(key) or {}</c>.</summary>
    private static PyDict Dict(PyDict pack, string key) => ProximityCoerce.Truthy(Get(pack, key)) ? (PyDict)Get(pack, key)! : new PyDict();

    /// <summary>Python <c>float(v or fallback)</c>.</summary>
    private static double FloatOr(object? v, double fallback) => ProximityCoerce.Truthy(v) ? ProximityCoerce.ToFloat(v) : fallback;

    /// <summary>Python <c>int(v or 5)</c>.</summary>
    private static object Years(object? v) => ProximityCoerce.Truthy(v) ? ProximityCoerce.ToInt(v) : 5L;
}
