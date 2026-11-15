using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>Eligibility classification and the pay-code policy (Python <c>onezero.py</c>, CALC-03, CALC-11, BA-06).</summary>
public static class OneZeroEligibility
{
    /// <summary><c>_round_half_up</c> (BA-06): round half away from zero on the shortest-repr decimal, as Access does.</summary>
    /// <param name="value">The value.</param>
    /// <param name="places">Decimal places.</param>
    /// <returns>The rounded value.</returns>
    public static double RoundHalfUp(double value, int places) =>
        PyDecimal.FromFloatViaStr(value).Quantize(places, PyRoundingMode.HalfUp).ToDouble();

    /// <summary><c>_pay_code_allowed</c> (CALC-11): excluded wins over included.</summary>
    /// <param name="payCode">The code.</param>
    /// <param name="pack">The pack.</param>
    /// <returns>Whether the code is counted.</returns>
    public static bool PayCodeAllowed(string payCode, OneZeroPack pack)
    {
        ArgumentNullException.ThrowIfNull(pack);
        if (pack.ExcludedPayCodes is { Count: > 0 } excluded && excluded.Contains(payCode))
        {
            return false;
        }

        return !(pack.IncludedPayCodes is { Count: > 0 } included && !included.Contains(payCode));
    }

    /// <summary><c>apply_pay_code_policy</c>: drops rows whose code is suppressed; unchanged when the pack has no policy.</summary>
    /// <param name="rows">The rows.</param>
    /// <param name="pack">The pack.</param>
    /// <returns>The rows to use.</returns>
    public static IReadOnlyList<PayrollRow> ApplyPayCodePolicy(IReadOnlyList<PayrollRow> rows, OneZeroPack pack)
    {
        ArgumentNullException.ThrowIfNull(rows);
        ArgumentNullException.ThrowIfNull(pack);
        if (pack.IncludedPayCodes is not { Count: > 0 } && pack.ExcludedPayCodes is not { Count: > 0 })
        {
            return rows;
        }

        return rows.Where(r => PayCodeAllowed(r.PayCodeText(), pack)).ToList();
    }

    /// <summary><c>_classify_eligibility</c> (CALC-03): weight and the two floor outcomes for one employee.</summary>
    /// <param name="avgHours">Average weekly hours.</param>
    /// <param name="avgWages">Average weekly wages.</param>
    /// <param name="pack">The pack.</param>
    /// <returns>(weight, passed hours, passed wages).</returns>
    public static (double Weight, bool PassedHours, bool PassedWages) Classify(double avgHours, double avgWages, OneZeroPack pack)
    {
        ArgumentNullException.ThrowIfNull(pack);
        var minHours = Number(pack.MinWeeklyHours);
        var passedWages = avgWages + 1e-9 >= Number(pack.MinWeeklyWages);
        var passedHours = avgHours + 1e-9 >= minHours;
        if (passedHours && passedWages)
        {
            return (1.0, passedHours, passedWages);
        }

        // Python truthiness: a part-time weight of 0 or 0.0 is "no weight".
        if (pack.PtBandHours is { } band && pack.PtWeight is { } weight && Number(weight) != 0 && passedWages)
        {
            if (Number(band.Low) - 1e-9 <= avgHours && avgHours < minHours)
            {
                return (Number(weight), passedHours, passedWages);
            }
        }

        return (0.0, passedHours, passedWages);
    }

    /// <summary><c>_eligibility_filter</c>: annotates every row in place and returns those with a non-zero weight.</summary>
    /// <param name="averages">All averages.</param>
    /// <param name="pack">The pack.</param>
    /// <returns>The eligible rows.</returns>
    public static List<AverageRow> Filter(IReadOnlyList<AverageRow> averages, OneZeroPack pack)
    {
        ArgumentNullException.ThrowIfNull(averages);
        var eligible = new List<AverageRow>();
        foreach (var row in averages)
        {
            if (row.WeeksWorked <= 0)
            {
                row.Weight = 0.0;
                row.PassedHours = false;
                row.PassedWages = false;
                row.Eligible = false;
                continue;
            }

            var (weight, passedHours, passedWages) = Classify(row.AvgWeeklyHours, row.AvgWeeklyWages, pack);
            row.Weight = weight;
            row.PassedHours = passedHours;
            row.PassedWages = passedWages;
            row.Eligible = weight > 0;
            if (weight > 0)
            {
                eligible.Add(row);
            }
        }

        return eligible;
    }

    private static double Number(PyNumber n) => n.IsInt ? n.IntValue : n.FloatValue;
}
