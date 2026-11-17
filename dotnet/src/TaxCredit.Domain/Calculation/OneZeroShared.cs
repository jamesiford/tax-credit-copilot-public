using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>Step shared by both methods and the period helpers (Python <c>onezero.py</c>; BA-12).</summary>
internal static class OneZeroShared
{
    /// <summary><c>_period_days</c>: inclusive day count of a pay period (a Mon-Sun week is 7).</summary>
    public static long PeriodDays(PayrollRow r)
    {
        var end = Coerce.ParseIso(r.RequireEnd());
        var start = Coerce.ParseIso(r.RequireStart());
        return end.DayNumber - start.DayNumber + 1;
    }

    /// <summary>BA-12: is this a real pay period rather than a payroll artefact?</summary>
    public static bool Qualifies(PayrollRow r, OneZeroMethodology m) => PeriodDays(r) >= m.MinimumPayPeriodDays;

    /// <summary><c>_infer_frequency</c>.</summary>
    public static string InferFrequency(long days)
    {
        if (days is >= 5 and <= 8)
        {
            return "weekly";
        }

        if (days is >= 12 and <= 16)
        {
            return "biweekly";
        }

        if (days is >= 14 and <= 17)
        {
            return "semimonthly";
        }

        return days is >= 28 and <= 32 ? "monthly" : "days_" + days.ToString(System.Globalization.CultureInfo.InvariantCulture);
    }

    /// <summary>Step 1 of both methods: running totals per employee (naive left-to-right float adds, as Python's <c>+=</c>), then rounded.</summary>
    public static OrderedDictionary<NullableKey, EmployeeTotals> Totals(IReadOnlyList<PayrollRow> rows, OneZeroMethodology m)
    {
        var numerator = m.ShortPeriodsExcludedFromNumerator ? rows.Where(r => Qualifies(r, m)).ToList() : rows;
        var totals = new OrderedDictionary<NullableKey, EmployeeTotals>();
        foreach (var r in numerator)
        {
            var ee = r.RequireEmployeeId();
            var key = new NullableKey(ee);
            if (!totals.TryGetValue(key, out var slot))
            {
                slot = new EmployeeTotals(ee);
                totals[key] = slot;
            }

            slot.TotalHours += Coerce.ToFloat(r.RequireHours());
            slot.TotalWages += Coerce.ToFloat(r.RequireWages());
        }

        foreach (var slot in totals.Values)
        {
            slot.TotalHours = PyRound.Round(slot.TotalHours, 2);
            slot.TotalWages = PyRound.Round(slot.TotalWages, 2);
        }

        return totals;
    }

    /// <summary>The totals sorted by Employee_ID (code point order, stable).</summary>
    public static List<EmployeeTotals> SortedTotals(OrderedDictionary<NullableKey, EmployeeTotals> totals) =>
        PySort.Sorted(totals.Values, t => t.EmployeeId, KeyOrder.Single);

    /// <summary>Annotated averages sort: wages descending, stable.</summary>
    public static List<AverageRow> SortByWagesDescending(List<AverageRow> averages) =>
        PySort.Sorted(averages, a => a.AvgWeeklyWages, PySort.FloatComparer, reverse: true);

    /// <summary>Builds the 12 month cells of one matrix row (CALC-04 + Month-12 rule).</summary>
    public static PyNumber[] MonthCells(IReadOnlyList<DateOnly> months, string? measuringDate, DateOnly lastPpe, DateOnly first, DateOnly last, double weight)
    {
        var cells = new PyNumber[12];
        for (var i = 0; i < 12; i++)
        {
            var baseTarget = OneZeroCalendar.MeasuringDateForMonth(months[i], measuringDate);
            var target = OneZeroCalendar.AdjustedTargetForMonth(baseTarget, lastPpe, i == 11);
            var covers = first <= target && target <= last;
            cells[i] = covers ? PyNumber.OfFloat(weight) : PyNumber.OfInt(0);
        }

        return cells;
    }

    /// <summary>Formats a number the way an f-string does (int vs float).</summary>
    public static string Fmt(PyNumber n) => TrailValues.Str(n);
}
