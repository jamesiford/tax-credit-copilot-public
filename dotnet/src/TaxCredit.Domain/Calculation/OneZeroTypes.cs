using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>
/// How the calculation is measured (Python <c>OneZeroMethodology</c>): defaults are the v7 rule set certified against
/// the partner. Rule ids BA-03, BA-05, BA-06, BA-09, BA-11, BA-12 are documented in the Python source.
/// </summary>
public sealed record OneZeroMethodology
{
    /// <summary>BA-12: pay periods shorter than this many days are not real pay periods.</summary>
    public long MinimumPayPeriodDays { get; init; } = 7;

    /// <summary>BA-12 asymmetry switch: drop short periods from the numerator too.</summary>
    public bool ShortPeriodsExcludedFromNumerator { get; init; }

    /// <summary>BA-03: <c>actual_span</c> or <c>frequency_code</c>.</summary>
    public string PayPeriodDenominatorMode { get; init; } = "actual_span";

    /// <summary>BA-11: <c>exclusive_days</c> or <c>inclusive_days</c>.</summary>
    public string MinMaxSpanMode { get; init; } = "exclusive_days";

    /// <summary>BA-05: zero-hour rows stay in the totals.</summary>
    public bool CountZeroHourPeriods { get; init; } = true;

    /// <summary>BA-06: decimals the averages round to (half-up).</summary>
    public int AverageDecimals { get; init; } = 2;

    /// <summary>BA-09: weeks above this are flagged, never capped.</summary>
    public PyNumber MaximumWeeksWithoutReview { get; init; } = PyNumber.OfFloat(53.0);

    /// <summary>Legacy off-cycle heuristic (superseded by BA-12; off in the certified path).</summary>
    public bool ExcludeOffCyclePeriods { get; init; }
}

/// <summary>Eligibility parameters lifted from a rule pack's <c>one_zero</c> block (Python <c>OneZeroPack</c>).</summary>
public sealed record OneZeroPack
{
    /// <summary>Weekly hours floor; int or float exactly as the pack JSON held it (it is printed in the trail).</summary>
    public required PyNumber MinWeeklyHours { get; init; }

    /// <summary>Weekly wages floor (int or float).</summary>
    public required PyNumber MinWeeklyWages { get; init; }

    /// <summary>Statutory citation for trail rows.</summary>
    public string Citation { get; init; } = string.Empty;

    /// <summary>CALC-03: part-time band (lo, hi) or null.</summary>
    public (PyNumber Low, PyNumber High)? PtBandHours { get; init; }

    /// <summary>CALC-03: fractional weight for the part-time band; null, 0 and 0.0 are all "no weight".</summary>
    public PyNumber? PtWeight { get; init; }

    /// <summary>CALC-04: <c>last_day</c> or a numeric day-of-month text; null behaves as <c>last_day</c>.</summary>
    public string? MeasuringDate { get; init; } = "last_day";

    /// <summary>CALC-11: pay codes counted (null = all).</summary>
    public IReadOnlyList<string>? IncludedPayCodes { get; init; }

    /// <summary>CALC-11: pay codes suppressed; wins over included.</summary>
    public IReadOnlyList<string>? ExcludedPayCodes { get; init; }

    /// <summary>How the calculation is measured.</summary>
    public OneZeroMethodology Methodology { get; init; } = new();
}

/// <summary>A per-employee totals slot (<c>total_hours_and_wages</c> element); shared by reference like the Python dicts.</summary>
public sealed class EmployeeTotals(string? employeeId)
{
    /// <summary>Employee_ID.</summary>
    public string? EmployeeId { get; } = employeeId;

    /// <summary>Running and then rounded hours.</summary>
    public double TotalHours { get; set; }

    /// <summary>Running and then rounded wages.</summary>
    public double TotalWages { get; set; }
}

/// <summary>Min-Max span columns an average row carries only under that method.</summary>
/// <param name="FirstStart">ISO date text of the earliest period start.</param>
/// <param name="LastEnd">ISO date text of the latest period end.</param>
/// <param name="Days">Day count of the span.</param>
public sealed record MinMaxSpan(string FirstStart, string LastEnd, long Days);

/// <summary>One employee's averages. Python annotates the same dict in place after building it; this mirrors that.</summary>
public sealed class AverageRow
{
    /// <summary>Employee_ID.</summary>
    public string? EmployeeId { get; init; }

    /// <summary>Total hours.</summary>
    public double TotalHours { get; init; }

    /// <summary>Total wages.</summary>
    public double TotalWages { get; init; }

    /// <summary>Weeks worked rounded to the average decimals.</summary>
    public double WeeksWorked { get; init; }

    /// <summary>Average weekly hours.</summary>
    public double AvgWeeklyHours { get; init; }

    /// <summary>Average weekly wages.</summary>
    public double AvgWeeklyWages { get; init; }

    /// <summary>Present only for Min-Max rows.</summary>
    public MinMaxSpan? Span { get; init; }

    /// <summary>Set by the eligibility filter.</summary>
    public double? Weight { get; set; }

    /// <summary>Set by the eligibility filter.</summary>
    public bool? PassedHours { get; set; }

    /// <summary>Set by the eligibility filter.</summary>
    public bool? PassedWages { get; set; }

    /// <summary>Set by the eligibility filter.</summary>
    public bool? Eligible { get; set; }
}

/// <summary>One One/Zero matrix row.</summary>
public sealed class MatrixRow
{
    /// <summary>Employee_ID.</summary>
    public string? EmployeeId { get; init; }

    /// <summary>Worksite_ID.</summary>
    public string? WorksiteId { get; init; }

    /// <summary>Entity_FEIN (null when the cell was None).</summary>
    public string? EntityFein { get; init; }

    /// <summary>Pay Period method only: raw Pay_Period_Start.</summary>
    public string? PayPeriodStart { get; init; }

    /// <summary>Pay Period method only: raw Pay_Period_End.</summary>
    public string? PayPeriodEnd { get; init; }

    /// <summary>Pay Period method only: raw Pay_Date.</summary>
    public string? PayDate { get; init; }

    /// <summary>Min-Max method only: ISO first period start at the unit.</summary>
    public string? FirstPps { get; init; }

    /// <summary>Min-Max method only: ISO last period end at the unit.</summary>
    public string? LastPpe { get; init; }

    /// <summary>The headcount weight.</summary>
    public double Weight { get; init; }

    /// <summary>The 12 month cells: the weight (float) when covered, int 0 otherwise, as in Python.</summary>
    public PyNumber[] Months { get; init; } = [];

    /// <summary>True for Min-Max rows (determines the key order of the row).</summary>
    public bool IsMinMax { get; init; }

    /// <summary>A copy with its own months array (Python <c>{**r, "months": list(r["months"])}</c>).</summary>
    /// <returns>The copy.</returns>
    public MatrixRow Clone() => new()
    {
        EmployeeId = EmployeeId,
        WorksiteId = WorksiteId,
        EntityFein = EntityFein,
        PayPeriodStart = PayPeriodStart,
        PayPeriodEnd = PayPeriodEnd,
        PayDate = PayDate,
        FirstPps = FirstPps,
        LastPpe = LastPpe,
        Weight = Weight,
        Months = [.. Months],
        IsMinMax = IsMinMax,
    };
}

/// <summary>One per-unit summary row.</summary>
/// <param name="WorksiteId">Worksite_ID.</param>
/// <param name="MonthTotals">12 rounded month totals.</param>
/// <param name="Total">Sum of the month totals.</param>
/// <param name="AverageHeadcount">Total divided by 12.</param>
public sealed record UnitSummary(string? WorksiteId, IReadOnlyList<double> MonthTotals, double Total, double AverageHeadcount);

/// <summary>A data-quality flag.</summary>
/// <param name="Type">Flag type.</param>
/// <param name="EmployeeId">Employee_ID.</param>
/// <param name="Weeks">over_53_weeks only.</param>
/// <param name="MonthIndex">multi_unit_double_count only.</param>
/// <param name="Count">multi_unit_double_count only (int or float as Python summed it).</param>
public sealed record OneZeroFlag(string Type, string? EmployeeId, double? Weeks = null, long? MonthIndex = null, PyNumber? Count = null);

/// <summary>Output of either method.</summary>
public sealed record OneZeroResult(
    string Method,
    long TaxYear,
    DateOnly AnalysisStartMonth,
    IReadOnlyList<DateOnly> Months,
    IReadOnlyList<EmployeeTotals> TotalHoursAndWages,
    IReadOnlyList<AverageRow> EligibleEmployees,
    IReadOnlyList<MatrixRow> EmployeeUnitMatrix,
    IReadOnlyList<UnitSummary> Summary,
    IReadOnlyList<KeyValuePair<string?, double>> AverageHeadcount,
    double AnnualAverage,
    IReadOnlyList<OneZeroFlag> Flags,
    IReadOnlyList<AverageRow> AllAverages);
