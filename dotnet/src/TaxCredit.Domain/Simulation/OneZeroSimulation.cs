using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Domain.Simulation;

/// <summary>
/// Python <c>tools/simulation.py</c> [J2] UX-02 entity-level simulator: the headline snapshot of a row set, and the levers (hours, wages,
/// add or remove heads) applied to a copy of it.
/// </summary>
/// <param name="library">The rule library behind the credit math.</param>
public sealed class OneZeroSimulation(RuleLibrary library)
{
    /// <summary>
    /// Python <c>onezero_snapshot</c>: runs the pay-period method plus the benefit math for a row set and returns the headline figures the
    /// simulator compares. <paramref name="priorAverageHeadcount"/> is the frozen base; omitting it treats the whole workforce as net-new.
    /// </summary>
    /// <param name="rows">The pay-period rows.</param>
    /// <param name="taxYear">The tax year (the window is the calendar year).</param>
    /// <param name="state">A state, or a program code to price that program.</param>
    /// <param name="pack">The eligibility parameters.</param>
    /// <param name="priorAverageHeadcount">The base the credit is measured against; <c>null</c> is the Python default <c>0.0</c>.</param>
    /// <returns>The snapshot tree.</returns>
    public PyDict OneZeroSnapshot(IReadOnlyList<PayrollRow> rows, long taxYear, string state, OneZeroPack pack, PyNumber? priorAverageHeadcount = null)
    {
        var prior = priorAverageHeadcount ?? PyNumber.OfFloat(0.0);
        var res = PayPeriodMethod.Run(rows, taxYear, PyDate.Make((int)taxYear, 1, 1), pack);
        object priorValue = prior.IsInt ? (object)prior.IntValue : prior.FloatValue;
        var credit = library.ApplyOneZeroStateCredit(state, res.AnnualAverage, priorValue, null);
        // `e.get("weight", 1.0) < 1.0`: the port keeps an absent weight as null, which Python reads as the default 1.0.
        var partTime = res.EligibleEmployees.Count(e => (e.Weight ?? 1.0) < 1.0);
        return new PyDict()
            .Add("average_headcount", res.AnnualAverage)
            .Add("eligible_employee_count", (long)res.EligibleEmployees.Count)
            .Add("part_time_eligible_count", (long)partTime)
            .Add("qualifying_jobs", Get(credit, "qualifying_jobs", 0L))
            .Add("annual_credit_usd", Get(credit, "annual_credit_usd", 0L))
            .Add("lifetime_credit_usd", Get(credit, "lifetime_credit_usd", 0L))
            .Add("base_average_headcount", prior.IsInt ? priorValue : PyRound.Round(prior.FloatValue, 2));
    }

    /// <summary>
    /// Python <c>describe_role</c>: whether a role of these hours and pay clears the two floors, in words. Reported, not enforced: the
    /// engine decides who counts; this only says in advance why a hire might move nothing.
    /// </summary>
    /// <param name="weeklyHours">Hours a week, or <c>null</c> for "the pack's floor".</param>
    /// <param name="hourlyRate">Pay an hour, or <c>null</c> for "unspecified".</param>
    /// <param name="pack">The eligibility parameters.</param>
    /// <returns>The sentence.</returns>
    public static string DescribeRole(double? weeklyHours, double? hourlyRate, OneZeroPack pack)
    {
        ArgumentNullException.ThrowIfNull(pack);
        var minHours = ProximityCoerce.ToFloat(pack.MinWeeklyHours);
        var minWages = ProximityCoerce.ToFloat(pack.MinWeeklyWages);
        if (weeklyHours is { } wh && wh < minHours)
        {
            return $"below the {PyFormat.General(minHours)}-hour floor, so these roles will not count";
        }

        var hours = weeklyHours ?? minHours;
        if (hourlyRate is { } rate && hours * rate < minWages)
        {
            return $"below the ${PyFormat.Fixed(minWages, 0, grouping: true)}/week wage floor, so these roles will not count";
        }

        return "clear of both floors, so each counts as a job";
    }

    private static object? Get(PyDict d, string key, object? fallback) => d.TryGetValue(key, out var v) ? v : fallback;
}
