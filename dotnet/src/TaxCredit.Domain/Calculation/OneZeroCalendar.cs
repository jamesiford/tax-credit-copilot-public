using System.Numerics;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>A dictionary key that may be Python <c>None</c> (C# dictionaries reject null keys).</summary>
/// <param name="Value">The text, or null for <c>None</c>.</param>
internal readonly record struct NullableKey(string? Value);

/// <summary>Ordering of string-or-None keys as Python's <c>sorted</c> sees them.</summary>
internal static class KeyOrder
{
    /// <summary>Compares two keys by code point; raises <c>TypeError</c> when either is None (Python cannot order None).</summary>
    public static int Compare(string? a, string? b)
    {
        if (a is null || b is null)
        {
            throw new PyTypeError("'<' not supported between instances of 'NoneType' and 'str'");
        }

        return PyStr.Compare(a, b);
    }

    /// <summary>Comparer over single keys (<c>key=lambda x: x["Employee_ID"]</c>).</summary>
    public static IComparer<string?> Single { get; } = Comparer<string?>.Create(Compare);

    /// <summary>Tuple comparison: equal components are skipped (Python tests <c>==</c> first), the first differing pair is ordered.</summary>
    public static int CompareTuple(string? a1, string? b1, string? a2, string? b2)
    {
        if (!string.Equals(a1, b1, StringComparison.Ordinal))
        {
            return Compare(a1, b1);
        }

        return string.Equals(a2, b2, StringComparison.Ordinal) ? 0 : Compare(a2, b2);
    }
}

/// <summary>
/// Calendar helpers of the One/Zero engine (Python <c>onezero.py</c>): twelve measuring dates, the measuring-date rule
/// (CALC-04), the Month-12 rule, fiscal-year labelling (CALC-05) and the stub-month derivation (OZ-01).
/// </summary>
public static class OneZeroCalendar
{
    /// <summary><c>fiscal_year_of</c>: fiscal year labelled by the year it ENDS (CALC-05).</summary>
    /// <param name="payDate">The pay date.</param>
    /// <param name="fiscalYearEndMonth">Last month of the fiscal year (12 = calendar).</param>
    /// <returns>The fiscal year.</returns>
    public static long FiscalYearOf(DateOnly payDate, long fiscalYearEndMonth = 12)
    {
        if (fiscalYearEndMonth == 12)
        {
            return payDate.Year;
        }

        return payDate.Month <= fiscalYearEndMonth ? payDate.Year : payDate.Year + 1;
    }

    /// <summary><c>fiscal_window_start</c>: first day of the 12-month analysis window (CALC-05).</summary>
    /// <param name="taxYear">The fiscal year.</param>
    /// <param name="fiscalYearEndMonth">Last month of the fiscal year.</param>
    /// <returns>The first day.</returns>
    public static DateOnly FiscalWindowStart(long taxYear, long fiscalYearEndMonth = 12)
    {
        if (fiscalYearEndMonth == 12)
        {
            return PyDate.Make((int)taxYear, 1, 1);
        }

        var startMonth = (((fiscalYearEndMonth % 12) + 12) % 12) + 1;
        var startYear = startMonth > 1 ? taxYear - 1 : taxYear;
        return PyDate.Make((int)startYear, (int)startMonth, 1);
    }

    /// <summary><c>_twelve_month_ends</c>: the last calendar day of each of 12 months from <paramref name="startMonth"/>.</summary>
    /// <param name="startMonth">Any date in the first month.</param>
    /// <returns>Twelve month-end dates.</returns>
    public static IReadOnlyList<DateOnly> TwelveMonthEnds(DateOnly startMonth)
    {
        var result = new List<DateOnly>(12);
        int y = startMonth.Year, m = startMonth.Month;
        for (var i = 0; i < 12; i++)
        {
            DateOnly last;
            int y2, m2;
            if (m == 12)
            {
                last = PyDate.Make(y, 12, 31);
                y2 = y + 1;
                m2 = 1;
            }
            else
            {
                last = PyDate.AddDays(PyDate.Make(y, m + 1, 1), -1);
                y2 = y;
                m2 = m + 1;
            }

            result.Add(last);
            y = y2;
            m = m2;
        }

        return result;
    }

    /// <summary><c>_period_spans</c>: (start, end) of every row, start parsed first.</summary>
    internal static List<(DateOnly Start, DateOnly End)> PeriodSpans(IReadOnlyList<PayrollRow> rows)
    {
        var spans = new List<(DateOnly, DateOnly)>(rows.Count);
        foreach (var r in rows)
        {
            var start = Coerce.ParseIso(r.RequireStart());
            var end = Coerce.ParseIso(r.RequireEnd());
            spans.Add((start, end));
        }

        return spans;
    }

    private static bool Spanned(DateOnly target, List<(DateOnly Start, DateOnly End)> spans)
    {
        foreach (var (start, end) in spans)
        {
            if (start <= target && target <= end)
            {
                return true;
            }
        }

        return false;
    }

    /// <summary><c>first_measurable_month</c> (OZ-01): the first month whose month-end some pay period actually spans.</summary>
    /// <param name="rows">The rows.</param>
    /// <param name="windowStart">Window begin.</param>
    /// <param name="windowEnd">Window end.</param>
    /// <returns>The first day of that month, or the window start when none is covered.</returns>
    public static DateOnly FirstMeasurableMonth(IReadOnlyList<PayrollRow> rows, DateOnly windowStart, DateOnly windowEnd)
    {
        ArgumentNullException.ThrowIfNull(rows);
        var cursor = PyDate.Make(windowStart.Year, windowStart.Month, 1);
        var spans = PeriodSpans(rows);
        while (cursor <= windowEnd)
        {
            var monthEnd = TwelveMonthEnds(cursor)[0];
            if (Spanned(monthEnd, spans))
            {
                return cursor;
            }

            cursor = cursor.Month == 12 ? PyDate.Make(cursor.Year + 1, 1, 1) : PyDate.Make(cursor.Year, cursor.Month + 1, 1);
        }

        return windowStart;
    }

    /// <summary><c>unreachable_months</c>: positions whose measuring date no pay period spans.</summary>
    /// <param name="rows">The rows.</param>
    /// <param name="months">Measuring dates.</param>
    /// <returns>Zero-based positions.</returns>
    public static IReadOnlyList<long> UnreachableMonths(IReadOnlyList<PayrollRow> rows, IReadOnlyList<DateOnly> months)
    {
        ArgumentNullException.ThrowIfNull(rows);
        ArgumentNullException.ThrowIfNull(months);
        var spans = PeriodSpans(rows);
        var result = new List<long>();
        for (var i = 0; i < months.Count; i++)
        {
            if (!Spanned(months[i], spans))
            {
                result.Add(i);
            }
        }

        return result;
    }

    /// <summary><c>_adjusted_target_for_month</c>: the Month-12 rule (a last period end after the 15th replaces the month-end).</summary>
    /// <param name="monthEnd">Base target for the month.</param>
    /// <param name="lastPpeInRange">Last pay-period end.</param>
    /// <param name="isMonth12">Whether this is the twelfth month.</param>
    /// <returns>The target date.</returns>
    public static DateOnly AdjustedTargetForMonth(DateOnly monthEnd, DateOnly lastPpeInRange, bool isMonth12) =>
        isMonth12 && lastPpeInRange.Month == monthEnd.Month && lastPpeInRange.Year == monthEnd.Year && lastPpeInRange.Day > 15
            ? lastPpeInRange
            : monthEnd;

    /// <summary><c>_measuring_date_for_month</c> (CALC-04): <c>last_day</c> or a day-of-month clamped to the month.</summary>
    /// <param name="monthEnd">Last day of the month.</param>
    /// <param name="measuringDate">The pack's measuring-date text.</param>
    /// <returns>The date.</returns>
    public static DateOnly MeasuringDateForMonth(DateOnly monthEnd, string? measuringDate)
    {
        if (measuringDate is null || measuringDate.Length == 0 || measuringDate == "last_day")
        {
            return monthEnd;
        }

        if (!PyInt.TryParse(measuringDate, out var parsed))
        {
            return monthEnd;
        }

        var day = (int)BigInteger.Max(1, BigInteger.Min(parsed, monthEnd.Day));
        return PyDate.Make(monthEnd.Year, monthEnd.Month, day);
    }
}
