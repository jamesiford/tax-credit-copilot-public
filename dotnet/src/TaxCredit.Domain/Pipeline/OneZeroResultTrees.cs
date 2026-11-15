using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Pipeline;

/// <summary>
/// A One/Zero result as the plain dictionaries the Gold projections read (Python hands them the engine's own dicts and dataclass). Key order and the
/// int/float type of every number are the engine's; the projections' own goldens already cover what they do with them.
/// </summary>
public static class OneZeroResultTrees
{
    /// <summary><c>result.total_hours_and_wages</c>: <c>{Employee_ID, total_hours, total_wages}</c> per employee.</summary>
    /// <param name="result">The engine result.</param>
    /// <returns>The rows.</returns>
    public static IReadOnlyList<PyDict> Totals(OneZeroResult result)
    {
        ArgumentNullException.ThrowIfNull(result);
        return result.TotalHoursAndWages.Select(t => new PyDict().Add("Employee_ID", t.EmployeeId).Add("total_hours", t.TotalHours).Add("total_wages", t.TotalWages)).ToList();
    }

    /// <summary><c>result.all_averages</c>: the span columns only under Min-Max, the eligibility columns once the filter has set them.</summary>
    /// <param name="result">The engine result.</param>
    /// <returns>The rows.</returns>
    public static IReadOnlyList<PyDict> Averages(OneZeroResult result)
    {
        ArgumentNullException.ThrowIfNull(result);
        return result.AllAverages.Select(Average).ToList();
    }

    /// <summary><c>result.employee_unit_matrix</c>: the deduped matrix the result published.</summary>
    /// <param name="result">The engine result.</param>
    /// <returns>The rows.</returns>
    public static IReadOnlyList<PyDict> Matrix(OneZeroResult result)
    {
        ArgumentNullException.ThrowIfNull(result);
        return result.EmployeeUnitMatrix.Select(MatrixRow).ToList();
    }

    /// <summary><c>result.summary</c>: one row per unit.</summary>
    /// <param name="result">The engine result.</param>
    /// <returns>The rows.</returns>
    public static IReadOnlyList<PyDict> Summary(OneZeroResult result)
    {
        ArgumentNullException.ThrowIfNull(result);
        return result.Summary
            .Select(s => new PyDict().Add("Worksite_ID", s.WorksiteId).Add("month_totals", s.MonthTotals.Select(c => (object?)c).ToList()).Add("total", s.Total).Add("average_headcount", s.AverageHeadcount))
            .ToList();
    }

    /// <summary>What <c>run_method_summary_row</c> reads of a result.</summary>
    /// <param name="result">The engine result.</param>
    /// <returns>The facts.</returns>
    public static RunMethodResult Facts(OneZeroResult result)
    {
        ArgumentNullException.ThrowIfNull(result);
        return new RunMethodResult(
            result.AnnualAverage, result.EligibleEmployees.Count, result.TotalHoursAndWages.Count, result.EmployeeUnitMatrix.Count,
            result.Flags.Select(Flag).ToList(), result.Months.Select(m => (object?)m).ToList());
    }

    private static PyDict Average(AverageRow a)
    {
        var d = new PyDict().Add("Employee_ID", a.EmployeeId).Add("total_hours", a.TotalHours).Add("total_wages", a.TotalWages);
        if (a.Span is { } s)
        {
            d.Add("first_start", s.FirstStart).Add("last_end", s.LastEnd).Add("days", s.Days);
        }

        d.Add("weeks_worked", a.WeeksWorked).Add("avg_weekly_hours", a.AvgWeeklyHours).Add("avg_weekly_wages", a.AvgWeeklyWages);
        if (a.Eligible is not null)
        {
            d.Add("weight", a.Weight).Add("passed_hours", a.PassedHours).Add("passed_wages", a.PassedWages).Add("eligible", a.Eligible);
        }

        return d;
    }

    private static PyDict MatrixRow(MatrixRow m)
    {
        var d = new PyDict().Add("Employee_ID", m.EmployeeId).Add("Worksite_ID", m.WorksiteId).Add("Entity_FEIN", m.EntityFein);
        if (m.IsMinMax)
        {
            d.Add("first_pps", m.FirstPps).Add("last_ppe", m.LastPpe);
        }
        else
        {
            d.Add("Pay_Period_Start", m.PayPeriodStart).Add("Pay_Period_End", m.PayPeriodEnd).Add("Pay_Date", m.PayDate);
        }

        return d.Add("weight", m.Weight).Add("months", m.Months.Select(n => TrailValues.Of(n)).Cast<object?>().ToList());
    }

    private static PyDict Flag(OneZeroFlag f)
    {
        var d = new PyDict().Add("type", f.Type).Add("employee_id", f.EmployeeId);
        return f.Weeks is { } w ? d.Add("weeks", w) : d.Add("month_index", f.MonthIndex).Add("count", f.Count is { } c ? TrailValues.Of(c) : null);
    }
}
