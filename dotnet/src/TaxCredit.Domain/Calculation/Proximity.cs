using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>
/// Which employees are near the statutory line, and what would close the gap (Python <c>domain/calculation/proximity.py</c>).
/// Reads an eligibility result; it never alters one. Rows and results are <see cref="PyDict"/> trees because the Python
/// contract is dictionaries whose key order, int-versus-float values and missing keys are observable.
/// </summary>
public static partial class Proximity
{
    /// <summary>A working week beyond which extra hours stop being a scheduling decision (<c>PLAUSIBLE_WEEKLY_HOURS</c>).</summary>
    public const double PlausibleWeeklyHours = 40.0;

    /// <summary>The notches the band curve reports (<c>BAND_CURVE_HOURS</c>).</summary>
    public static IReadOnlyList<double> BandCurveHours { get; } = [1.0, 2.0, 5.0, 10.0];

    /// <summary>Implied hourly rate, or <c>null</c> when none can be known (<c>_rate</c>): zero or negative hours have no rate.</summary>
    /// <param name="totalHours">Hours.</param>
    /// <param name="totalWages">Wages.</param>
    /// <returns>Wages per hour, or <c>null</c>.</returns>
    public static double? Rate(double totalHours, double totalWages) => totalHours <= 0 ? null : totalWages / totalHours;

    /// <summary>One employee's distance from the two floors and the lever that closes it (<c>assess_employee</c>).</summary>
    /// <param name="average">A row of <c>all_averages</c>.</param>
    /// <param name="floors">The year's floors.</param>
    /// <param name="decimals">Places to round to.</param>
    /// <returns>The assessment tree, keys in Python order.</returns>
    public static PyDict AssessEmployee(PyDict average, StatutoryFloors floors, int decimals = 2)
    {
        ArgumentNullException.ThrowIfNull(average);
        ArgumentNullException.ThrowIfNull(floors);
        var weeks = ProximityCoerce.FloatOrZero(average, "weeks_worked");
        var totalHours = ProximityCoerce.FloatOrZero(average, "total_hours");
        var totalWages = ProximityCoerce.FloatOrZero(average, "total_wages");
        var avgHours = ProximityCoerce.FloatOrZero(average, "avg_weekly_hours");
        var avgWages = ProximityCoerce.FloatOrZero(average, "avg_weekly_wages");
        var minHours = ProximityCoerce.ToFloat(floors.MinWeeklyHours);
        var minWages = ProximityCoerce.ToFloat(floors.MinWeeklyWages);

        var passedHours = avgHours >= minHours;
        var passedWages = avgWages >= minWages;
        var failed = new List<object?>();
        if (!passedHours)
        {
            failed.Add("hours");
        }

        if (!passedWages)
        {
            failed.Add("wages");
        }

        // proximity.py assess_employee: a recorded verdict beats the floors (a part-time band is eligible while failing hours).
        average.TryGetValue("eligible", out var recorded);
        var derived = failed.Count == 0;
        var eligible = recorded is not null ? ProximityCoerce.Truthy(recorded) : derived;

        var hoursGap = passedHours ? 0.0 : ProximityCoerce.RoundHalfUp(minHours - avgHours, decimals);
        var wagesGap = passedWages ? 0.0 : ProximityCoerce.RoundHalfUp(minWages - avgWages, decimals);
        var rate = Rate(totalHours, totalWages);
        double? thresholdRate = ProximityCoerce.Truthy(minHours) ? minWages / minHours : null;
        var rateLimited = rate is not null && thresholdRate is not null && rate < thresholdRate;

        var additional = AdditionalHours(failed.Count, weeks, passedHours, passedWages, hoursGap, wagesGap, rate, decimals);
        double? rateToQualify = null;
        if (passedHours && !passedWages && totalHours > 0)
        {
            rateToQualify = ProximityCoerce.RoundHalfUp(minWages * weeks / totalHours, decimals);
        }

        double? projected = additional is null ? null : ProximityCoerce.RoundHalfUp(avgHours + additional.Value, decimals);
        average.TryGetValue("Employee_ID", out var employeeId);
        average.TryGetValue("record_token", out var token);
        return new PyDict()
            .Add("employee_id", employeeId)
            .Add("weeks_worked", ProximityCoerce.RoundHalfUp(weeks, decimals))
            .Add("total_hours", totalHours)
            .Add("total_wages", totalWages)
            .Add("avg_weekly_hours", avgHours)
            .Add("avg_weekly_wages", avgWages)
            .Add("eligible", eligible)
            .Add("verdict_source", recorded is not null ? "recorded" : "derived")
            .Add("verdict_disagrees", recorded is not null && ProximityCoerce.Truthy(recorded) != derived)
            .Add("failed", failed)
            .Add("failure_mode", failed.Count == 0 ? "none" : failed.Count == 2 ? "both" : $"{failed[0]}_only")
            .Add("hours_gap_per_week", hoursGap)
            .Add("wages_gap_per_week", wagesGap)
            .Add("implied_hourly_rate", rate is null ? null : ProximityCoerce.RoundHalfUp(rate.Value, decimals))
            .Add("threshold_hourly_rate", thresholdRate is null ? null : ProximityCoerce.RoundHalfUp(thresholdRate.Value, decimals))
            .Add("rate_limited", rateLimited)
            .Add("additional_weekly_hours", additional)
            .Add("projected_weekly_hours", projected)
            .Add("exceeds_plausible_week", projected is not null && projected > PlausibleWeeklyHours)
            .Add("hourly_rate_to_qualify", rateToQualify)
            .Add("record_token", token);
    }

    /// <summary>How much cushion a QUALIFYING employee has before they stop qualifying (<c>fragility</c>); the SMALLER cushion binds.</summary>
    /// <param name="average">A row of <c>all_averages</c>.</param>
    /// <param name="floors">The year's floors.</param>
    /// <param name="decimals">Places to round to.</param>
    /// <returns>The cushion tree, keys in Python order.</returns>
    public static PyDict Fragility(PyDict average, StatutoryFloors floors, int decimals = 2)
    {
        ArgumentNullException.ThrowIfNull(average);
        ArgumentNullException.ThrowIfNull(floors);
        var weeks = ProximityCoerce.FloatOrZero(average, "weeks_worked");
        var totalHours = ProximityCoerce.FloatOrZero(average, "total_hours");
        var totalWages = ProximityCoerce.FloatOrZero(average, "total_wages");
        var avgHours = ProximityCoerce.FloatOrZero(average, "avg_weekly_hours");
        var avgWages = ProximityCoerce.FloatOrZero(average, "avg_weekly_wages");
        var minHours = ProximityCoerce.ToFloat(floors.MinWeeklyHours);
        var minWages = ProximityCoerce.ToFloat(floors.MinWeeklyWages);

        var hoursHeadroom = ProximityCoerce.RoundHalfUp(avgHours - minHours, decimals);
        var wagesHeadroom = ProximityCoerce.RoundHalfUp(avgWages - minWages, decimals);
        var rate = Rate(totalHours, totalWages);
        // Python `if rate and rate > 0`: a zero or None rate cannot convert the wage cushion into hours.
        double? wagesHeadroomHours = rate is not null && rate.Value != 0 && rate.Value > 0
            ? ProximityCoerce.RoundHalfUp(wagesHeadroom / rate.Value, decimals)
            : null;
        // min([hours] + [wages_hours]): the first minimal element wins, as PyArith.Min does.
        var toLose = wagesHeadroomHours is null ? hoursHeadroom : PyArith.Min(hoursHeadroom, wagesHeadroomHours.Value);
        var binding = wagesHeadroomHours is not null && wagesHeadroomHours < hoursHeadroom ? "wages" : "hours";
        average.TryGetValue("Employee_ID", out var employeeId);
        average.TryGetValue("record_token", out var token);
        return new PyDict()
            .Add("employee_id", employeeId)
            .Add("record_token", token)
            .Add("weeks_worked", ProximityCoerce.RoundHalfUp(weeks, decimals))
            .Add("avg_weekly_hours", avgHours)
            .Add("avg_weekly_wages", avgWages)
            .Add("hours_headroom", hoursHeadroom)
            .Add("wages_headroom_usd", wagesHeadroom)
            .Add("weekly_hours_to_lose", toLose)
            .Add("binding_floor", binding)
            .Add("implied_hourly_rate", rate is null ? null : ProximityCoerce.RoundHalfUp(rate.Value, decimals))
            // proximity.py fragility: `float(weight or 1.0)` reads a weight of 0 as 1.0 (finding P-01).
            .Add("weight", ProximityCoerce.Truthy(average.TryGetValue("weight", out var w) ? w : null) ? ProximityCoerce.ToFloat(w) : 1.0);
    }

    /// <summary>Additional weekly hours that clear every failing test at the employee's own rate; the LARGER need binds.</summary>
    private static double? AdditionalHours(int failedCount, double weeks, bool passedHours, bool passedWages, double hoursGap, double wagesGap, double? rate, int decimals)
    {
        if (failedCount == 0)
        {
            return 0.0;
        }

        if (weeks <= 0)
        {
            return null;
        }

        var needs = new List<double>();
        if (!passedHours)
        {
            needs.Add(hoursGap);
        }

        if (!passedWages)
        {
            if (rate is null || rate <= 0)
            {
                return null;
            }

            needs.Add(wagesGap / rate.Value);
        }

        return ProximityCoerce.RoundHalfUp(PyArith.Max(needs), decimals);
    }
}
