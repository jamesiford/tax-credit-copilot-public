using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>The partner's 6-step Min Max Method (Python <c>run_min_max_method</c>; BA-06, BA-11, BA-12).</summary>
public static class MinMaxMethod
{
    private sealed class Span(DateOnly start, DateOnly end)
    {
        public DateOnly First { get; set; } = start;

        public DateOnly Last { get; set; } = end;
    }

    /// <summary>Runs the method.</summary>
    /// <param name="rows">Payroll rows.</param>
    /// <param name="taxYear">Fiscal year label.</param>
    /// <param name="analysisStartMonth">First of the twelve measuring months.</param>
    /// <param name="pack">Eligibility parameters.</param>
    /// <param name="fiscalYearEndMonth">Last month of the fiscal year (12 = calendar).</param>
    /// <param name="fiscalWindow">Explicit client window (BA-01).</param>
    /// <param name="recorder">Trail recorder; the ambient one when null.</param>
    /// <returns>The result.</returns>
    public static OneZeroResult Run(
        IReadOnlyList<PayrollRow> rows,
        long taxYear,
        DateOnly analysisStartMonth,
        OneZeroPack pack,
        long fiscalYearEndMonth = 12,
        (DateOnly Begin, DateOnly End)? fiscalWindow = null,
        TrailRecorder? recorder = null)
    {
        ArgumentNullException.ThrowIfNull(rows);
        ArgumentNullException.ThrowIfNull(pack);
        recorder ??= TrailContext.Current;
        var m = pack.Methodology;
        var policyRows = OneZeroEligibility.ApplyPayCodePolicy(rows, pack);
        var months = OneZeroCalendar.TwelveMonthEnds(analysisStartMonth);
        var prepared = OneZeroPreprocessing.Preprocess(policyRows, taxYear, fiscalYearEndMonth, fiscalWindow, m, recorder);

        // Step 1: totals per employee (same as Pay Period).
        var totals = OneZeroShared.Totals(prepared, m);
        var totalHoursAndWages = OneZeroShared.SortedTotals(totals);
        recorder?.Record(
            "onezero.mm.step1_totals",
            new PyDict().Add("row_count", (long)prepared.Count),
            "sum(Hours_Worked), sum(Gross_Wages) GROUP BY Employee_ID",
            new PyDict().Add("employees", (long)totalHoursAndWages.Count),
            "One Zero Min Max.docx Step 1");

        // Step 2: weeks worked = (latest PPE - earliest PPS) / 7, short periods define no span (BA-12).
        var spanRows = prepared.Where(r => OneZeroShared.Qualifies(r, m)).ToList();
        var shortPeriodRows = prepared.Count - spanRows.Count;
        var span = new OrderedDictionary<NullableKey, Span>();
        foreach (var r in spanRows)
        {
            var key = new NullableKey(r.RequireEmployeeId());
            var pps = Coerce.ParseIso(r.RequireStart());
            var ppe = Coerce.ParseIso(r.RequireEnd());
            if (!span.TryGetValue(key, out var slot))
            {
                span[key] = new Span(pps, ppe);
                continue;
            }

            if (pps < slot.First)
            {
                slot.First = pps;
            }

            if (ppe > slot.Last)
            {
                slot.Last = ppe;
            }
        }

        var weeksWorked = new OrderedDictionary<NullableKey, (DateOnly First, DateOnly Last, long Days, double Weeks)>();
        foreach (var (key, sl) in span)
        {
            // BA-11: exclusive day count, full precision kept; only the average rounds (BA-06).
            var days = (long)sl.Last.DayNumber - sl.First.DayNumber;
            if (m.MinMaxSpanMode == "inclusive_days")
            {
                days++;
            }

            weeksWorked[key] = (sl.First, sl.Last, days, days / 7.0);
        }

        recorder?.Record(
            "onezero.mm.step2_weeks",
            new PyDict()
                .Add("employees", (long)weeksWorked.Count)
                .Add("minimum_pay_period_days", m.MinimumPayPeriodDays)
                .Add("short_period_rows_excluded", (long)shortPeriodRows),
            "weeks_worked = (latest PayPeriodEnd - earliest PayPeriodStart) / 7"
            + $" over periods spanning >= {m.MinimumPayPeriodDays} days"
            + $" ({m.MinMaxSpanMode})",
            new PyDict().Add("employees", (long)weeksWorked.Count),
            "One Zero Min Max.docx Step 2; BA-11, BA-12");

        // Step 3: averages.
        var averages = new List<AverageRow>();
        foreach (var (key, t) in totals)
        {
            if (!weeksWorked.TryGetValue(key, out var ww) || ww.Weeks <= 0)
            {
                continue;
            }

            averages.Add(new AverageRow
            {
                EmployeeId = key.Value,
                TotalHours = t.TotalHours,
                TotalWages = t.TotalWages,
                Span = new MinMaxSpan(ww.First.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture), ww.Last.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture), ww.Days),
                WeeksWorked = PyRound.Round(ww.Weeks, m.AverageDecimals),
                AvgWeeklyHours = OneZeroEligibility.RoundHalfUp(t.TotalHours / ww.Weeks, m.AverageDecimals),
                AvgWeeklyWages = OneZeroEligibility.RoundHalfUp(t.TotalWages / ww.Weeks, m.AverageDecimals),
            });
        }

        averages = OneZeroShared.SortByWagesDescending(averages);
        recorder?.Record(
            "onezero.mm.step3_averages",
            new PyDict().Add("employees", (long)averages.Count),
            "avg_weekly_* = total_*/weeks_worked",
            new PyDict().Add("employees", (long)averages.Count),
            "One Zero Min Max.docx Step 3");

        // Step 4: eligibility.
        var eligible = OneZeroEligibility.Filter(averages, pack);
        recorder?.Record(
            "onezero.mm.step4_eligible",
            new PyDict().Add("min_weekly_hours", TrailValues.Of(pack.MinWeeklyHours)).Add("min_weekly_wages", TrailValues.Of(pack.MinWeeklyWages)),
            $"avg_weekly_hours >= {OneZeroShared.Fmt(pack.MinWeeklyHours)} AND avg_weekly_wages >= {OneZeroShared.Fmt(pack.MinWeeklyWages)}",
            new PyDict().Add("eligible_employees", (long)eligible.Count).Add("ineligible_employees", (long)(averages.Count - eligible.Count)),
            pack.Citation);
        var eligibleWeight = new Dictionary<NullableKey, double>();
        foreach (var e in eligible)
        {
            eligibleWeight[new NullableKey(e.EmployeeId)] = e.Weight ?? 1.0;
        }

        // Step 5: one matrix line per (employee, unit): earliest start and latest end at that unit (all rows, short periods included).
        var eeUnitSpan = new OrderedDictionary<(NullableKey, NullableKey), (DateOnly First, DateOnly Last, string? Fein)>();
        foreach (var r in prepared)
        {
            var ee = new NullableKey(r.RequireEmployeeId());
            if (!eligibleWeight.ContainsKey(ee))
            {
                continue;
            }

            var key = (ee, new NullableKey(r.RequireWorksiteId()));
            var pps = Coerce.ParseIso(r.RequireStart());
            var ppe = Coerce.ParseIso(r.RequireEnd());
            if (!eeUnitSpan.TryGetValue(key, out var slot))
            {
                eeUnitSpan[key] = (pps, ppe, r.EntityFeinOrEmpty());
                continue;
            }

            eeUnitSpan[key] = (pps < slot.First ? pps : slot.First, ppe > slot.Last ? ppe : slot.Last, slot.Fein);
        }

        var matrix = new List<MatrixRow>();
        foreach (var ((ee, unit), sl) in eeUnitSpan)
        {
            var weight = eligibleWeight.GetValueOrDefault(ee, 1.0);
            matrix.Add(new MatrixRow
            {
                EmployeeId = ee.Value,
                WorksiteId = unit.Value,
                EntityFein = sl.Fein,
                FirstPps = sl.First.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture),
                LastPpe = sl.Last.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture),
                Weight = weight,
                Months = OneZeroShared.MonthCells(months, pack.MeasuringDate, sl.Last, sl.First, sl.Last, weight),
                IsMinMax = true,
            });
        }

        matrix = PySort.Sorted(matrix, r => r, Comparer<MatrixRow>.Create((a, b) => KeyOrder.CompareTuple(a.EmployeeId, b.EmployeeId, a.WorksiteId, b.WorksiteId)));

        // Flag duplicates: the same employee with more than one non-zero in a month across units.
        var dupFlags = new List<OneZeroFlag>();
        var byEeMonth = new OrderedDictionary<(NullableKey, int), PyNumber>();
        foreach (var row in matrix)
        {
            for (var i = 0; i < row.Months.Length; i++)
            {
                var k = (new NullableKey(row.EmployeeId), i);
                var current = byEeMonth.GetValueOrDefault(k, PyNumber.OfInt(0));
                byEeMonth[k] = Add(current, row.Months[i]);
            }
        }

        foreach (var ((ee, i), c) in byEeMonth)
        {
            if (OneZeroSummary.Value(c) > 1)
            {
                dupFlags.Add(new OneZeroFlag("multi_unit_double_count", ee.Value, MonthIndex: i, Count: c));
            }
        }

        recorder?.Record(
            "onezero.mm.step5_matrix",
            new PyDict().Add("eligible_employees", (long)eligibleWeight.Count),
            "for each (EE,Unit): 1 if first_pps<=month_end<=last_ppe (Month-12 special rule)",
            new PyDict().Add("matrix_rows", (long)matrix.Count).Add("double_count_flags", (long)dupFlags.Count),
            "One Zero Min Max.docx Step 5");

        // Tie-breaker: no employee counts twice in a month (most recent unit wins). dupFlags above evidences every candidate.
        var dedupMatrix = OneZeroSummary.DedupeOnePerMonth(matrix);

        // Step 6: summary.
        var (summary, avgPerUnit, annualAverage) = OneZeroSummary.Build(dedupMatrix);
        recorder?.Record(
            "onezero.mm.step6_summary",
            new PyDict().Add("units", (long)summary.Count).Add("months", 12L),
            "SUM(1s) per (Worksite_ID, month) -> 12-col table + 12-month average per unit",
            new PyDict().Add("unit_count", (long)summary.Count).Add("annual_average", annualAverage),
            "One Zero Min Max.docx Step 6");

        return new OneZeroResult("min_max", taxYear, analysisStartMonth, months, totalHoursAndWages, eligible, dedupMatrix, summary, avgPerUnit, annualAverage, dupFlags, averages);
    }

    /// <summary>Python <c>a + b</c> on int/float: int only when both are ints.</summary>
    private static PyNumber Add(PyNumber a, PyNumber b) =>
        a.IsInt && b.IsInt ? PyNumber.OfInt(a.IntValue + b.IntValue) : PyNumber.OfFloat(OneZeroSummary.Value(a) + OneZeroSummary.Value(b));
}
