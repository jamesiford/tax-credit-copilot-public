using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>The partner's 7-step Pay Period Method (Python <c>run_pay_period_method</c>; BA-03, BA-06, BA-09, BA-12).</summary>
public static class PayPeriodMethod
{
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

        // Step 1: totals per employee.
        var totals = OneZeroShared.Totals(prepared, m);
        var totalHoursAndWages = OneZeroShared.SortedTotals(totals);
        recorder?.Record(
            "onezero.pp.step1_totals",
            new PyDict().Add("row_count", (long)prepared.Count),
            "sum(Hours_Worked) AND sum(Gross_Wages) GROUP BY Employee_ID",
            new PyDict().Add("employees", (long)totalHoursAndWages.Count),
            "One Zero Pay Periods.docx Step 1");

        // Step 2: major pay periods per cycle.
        var isMajor = DetectMajorPayPeriods(prepared);
        if (recorder is not null)
        {
            var majorCount = isMajor.Values.Count(v => v);
            recorder.Record(
                "onezero.pp.step2_major_periods",
                new PyDict().Add("distinct_periods", (long)isMajor.Count),
                "bucket by frequency; period is major if employee_count >= median/2",
                new PyDict().Add("major_periods", (long)majorCount).Add("off_cycle_periods", (long)(isMajor.Count - majorCount)),
                "One Zero Pay Periods.docx Step 2");
        }

        // Step 3: weeks worked per employee.
        var eeMajorPeriods = new OrderedDictionary<NullableKey, List<(string? Start, string? End)>>();
        var eeFreqCounts = new OrderedDictionary<NullableKey, OrderedDictionary<string, long>>();
        var shortPeriodRows = 0L;
        foreach (var r in prepared)
        {
            if (!OneZeroShared.Qualifies(r, m))
            {
                shortPeriodRows++;
                continue;
            }

            var pps = r.RequireStart();
            var ppe = r.RequireEnd();
            var days = OneZeroShared.PeriodDays(r);
            var freq = OneZeroShared.InferFrequency(days);
            if (m.ExcludeOffCyclePeriods && !isMajor.GetValueOrDefault((pps, ppe, freq), false))
            {
                continue;
            }

            var key = new NullableKey(r.RequireEmployeeId());
            if (!eeMajorPeriods.TryGetValue(key, out var periods))
            {
                periods = [];
                eeMajorPeriods[key] = periods;
            }

            // Python keeps a set; the list holds each distinct pair once, in first-seen order.
            if (!periods.Contains((pps, ppe)))
            {
                periods.Add((pps, ppe));
            }

            if (!eeFreqCounts.TryGetValue(key, out var counts))
            {
                counts = [];
                eeFreqCounts[key] = counts;
            }

            counts[freq] = counts.GetValueOrDefault(freq) + 1;
        }

        var weeksWorked = new OrderedDictionary<NullableKey, (string? Id, double Weeks)>();
        var over53 = new List<(string? Id, double Weeks)>();
        foreach (var (key, periods) in eeMajorPeriods)
        {
            var freqCounts = eeFreqCounts[key];
            var primaryFreq = freqCounts.Count > 0
                ? PySort.MaxBy(freqCounts.ToList(), kv => kv.Value, Comparer<long>.Default).Key
                : "weekly";
            double weeks;
            if (m.PayPeriodDenominatorMode == "frequency_code")
            {
                weeks = periods.Count * FrequencyWeeksPerPeriod(primaryFreq);
            }
            else
            {
                // BA-03: each period contributes its own measured span. Python sums over a set whose order depends on the
                // string hash seed; the compensated sum is order-insensitive in practice (see findings F-02).
                var terms = new List<double>(periods.Count);
                foreach (var (pps, ppe) in periods)
                {
                    terms.Add(((Coerce.ParseIso(ppe).DayNumber - Coerce.ParseIso(pps).DayNumber) + 1) / 7.0);
                }

                weeks = PySum.Sum(terms);
            }

            weeksWorked[key] = (key.Value, weeks);
            if (weeks > Number(m.MaximumWeeksWithoutReview))
            {
                over53.Add((key.Value, weeks));
            }
        }

        if (recorder is not null)
        {
            var formula = m.PayPeriodDenominatorMode == "frequency_code"
                ? "weeks_worked = COUNT(unique major periods) * weeks_per_period(primary_freq)"
                : "weeks_worked = SUM((PayPeriodEnd - PayPeriodStart + 1) / 7) over unique major periods";
            recorder.Record(
                "onezero.pp.step3_weeks_worked",
                new PyDict()
                    .Add("employees_with_major_periods", (long)weeksWorked.Count)
                    .Add("minimum_pay_period_days", m.MinimumPayPeriodDays)
                    .Add("short_period_rows_excluded", shortPeriodRows),
                $"{formula}; periods spanning < {m.MinimumPayPeriodDays} days excluded",
                new PyDict().Add("employees", (long)weeksWorked.Count).Add("over_53_week_flags", (long)over53.Count),
                "One Zero Pay Periods.docx Step 3; BA-03, BA-12");
        }

        // Step 4: averages.
        var averages = new List<AverageRow>();
        foreach (var (key, t) in totals)
        {
            if (!weeksWorked.TryGetValue(key, out var ww) || ww.Weeks <= 0)
            {
                continue;
            }

            var avgHours = OneZeroEligibility.RoundHalfUp(t.TotalHours / ww.Weeks, m.AverageDecimals);
            var avgWages = OneZeroEligibility.RoundHalfUp(t.TotalWages / ww.Weeks, m.AverageDecimals);
            averages.Add(new AverageRow
            {
                EmployeeId = key.Value,
                TotalHours = t.TotalHours,
                TotalWages = t.TotalWages,
                WeeksWorked = PyRound.Round(ww.Weeks, m.AverageDecimals),
                AvgWeeklyHours = avgHours,
                AvgWeeklyWages = avgWages,
            });
        }

        averages = OneZeroShared.SortByWagesDescending(averages);
        recorder?.Record(
            "onezero.pp.step4_averages",
            new PyDict().Add("employees", (long)averages.Count),
            "avg_weekly_hours = total_hours/weeks_worked; avg_weekly_wages = total_wages/weeks_worked",
            new PyDict().Add("employees", (long)averages.Count),
            "One Zero Pay Periods.docx Step 4");

        // Step 5: eligibility filter.
        var eligible = OneZeroEligibility.Filter(averages, pack);
        recorder?.Record(
            "onezero.pp.step5_eligible",
            new PyDict().Add("min_weekly_hours", TrailValues.Of(pack.MinWeeklyHours)).Add("min_weekly_wages", TrailValues.Of(pack.MinWeeklyWages)),
            $"avg_weekly_hours >= {OneZeroShared.Fmt(pack.MinWeeklyHours)} AND avg_weekly_wages >= {OneZeroShared.Fmt(pack.MinWeeklyWages)}",
            new PyDict().Add("eligible_employees", (long)eligible.Count).Add("ineligible_employees", (long)(averages.Count - eligible.Count)),
            pack.Citation);
        var eligibleWeight = new Dictionary<NullableKey, double>();
        foreach (var e in eligible)
        {
            eligibleWeight[new NullableKey(e.EmployeeId)] = e.Weight ?? 1.0;
        }

        // Step 6: One/Zero matrix.
        var matrix = new List<MatrixRow>();
        foreach (var r in prepared)
        {
            var eeKey = new NullableKey(r.RequireEmployeeId());
            if (!eligibleWeight.ContainsKey(eeKey))
            {
                continue;
            }

            if (!OneZeroShared.Qualifies(r, m))
            {
                continue;
            }

            var pps = r.RequireStart();
            var ppe = r.RequireEnd();
            var days = OneZeroShared.PeriodDays(r);
            var freq = OneZeroShared.InferFrequency(days);
            if (m.ExcludeOffCyclePeriods && !isMajor.GetValueOrDefault((pps, ppe, freq), false))
            {
                continue;
            }

            var ppsDate = Coerce.ParseIso(pps);
            var ppeDate = Coerce.ParseIso(ppe);
            var weight = eligibleWeight.GetValueOrDefault(eeKey, 1.0);
            matrix.Add(new MatrixRow
            {
                EmployeeId = r.RequireEmployeeId(),
                WorksiteId = r.RequireWorksiteId(),
                EntityFein = r.EntityFeinOrEmpty(),
                PayPeriodStart = pps,
                PayPeriodEnd = ppe,
                PayDate = r.RequirePayDate(),
                Weight = weight,
                Months = OneZeroShared.MonthCells(months, pack.MeasuringDate, ppeDate, ppsDate, ppeDate, weight),
            });
        }

        var deduped = OneZeroSummary.DedupeOnePerMonth(matrix);
        recorder?.Record(
            "onezero.pp.step6_matrix",
            new PyDict().Add("eligible_employees", (long)eligibleWeight.Count).Add("major_period_lines", (long)deduped.Count),
            "for each (EE,Unit,major_period): 1 if PPS<=month_end<=PPE (Month-12 special rule applied)",
            new PyDict().Add("matrix_rows", (long)deduped.Count),
            "One Zero Pay Periods.docx Step 6");

        // Step 7: summary by unit by month.
        var (summary, avgPerUnit, annualAverage) = OneZeroSummary.Build(deduped);
        recorder?.Record(
            "onezero.pp.step7_summary",
            new PyDict().Add("units", (long)summary.Count).Add("months", 12L),
            "SUM(1s) per (Worksite_ID, month) -> 12-col table + 12-month average per unit",
            new PyDict().Add("unit_count", (long)summary.Count).Add("annual_average", annualAverage),
            "One Zero Pay Periods.docx Step 7");

        var flags = over53.Select(f => new OneZeroFlag("over_53_weeks", f.Id, Weeks: f.Weeks)).ToList();
        return new OneZeroResult("pay_period", taxYear, analysisStartMonth, months, totalHoursAndWages, eligible, deduped, summary, avgPerUnit, annualAverage, flags, averages);
    }

    private static double Number(PyNumber n) => n.IsInt ? n.IntValue : n.FloatValue;

    /// <summary><c>_frequency_weeks_per_period</c>: legacy <c>frequency_code</c> replay only; not the certified path.</summary>
    private static double FrequencyWeeksPerPeriod(string freq) => freq switch
    {
        "weekly" => 1.0,
        "biweekly" => 2.0,
        "semimonthly" => 52.0 / 24,
        "monthly" => 52.0 / 12,
        _ => 1.0,
    };

    /// <summary><c>_detect_major_pay_periods</c>: a period is major when it has at least half the median employee count of its cadence.</summary>
    private static OrderedDictionary<(string? Start, string? End, string Freq), bool> DetectMajorPayPeriods(IReadOnlyList<PayrollRow> rows)
    {
        var byPeriod = new OrderedDictionary<(string?, string?), HashSet<NullableKey>>();
        var periodDays = new Dictionary<(string?, string?), long>();
        foreach (var r in rows)
        {
            var pps = r.RequireStart();
            var ppe = r.RequireEnd();
            var days = Coerce.ParseIso(ppe).DayNumber - Coerce.ParseIso(pps).DayNumber + 1;
            periodDays[(pps, ppe)] = days;
            if (!byPeriod.TryGetValue((pps, ppe), out var set))
            {
                set = [];
                byPeriod[(pps, ppe)] = set;
            }

            set.Add(new NullableKey(r.RequireEmployeeId()));
        }

        var buckets = new OrderedDictionary<string, List<((string?, string?) Key, int Count)>>();
        foreach (var (key, employees) in byPeriod)
        {
            var freq = OneZeroShared.InferFrequency(periodDays[key]);
            if (!buckets.TryGetValue(freq, out var list))
            {
                list = [];
                buckets[freq] = list;
            }

            list.Add((key, employees.Count));
        }

        var isMajor = new OrderedDictionary<(string?, string?, string), bool>();
        foreach (var (freq, items) in buckets)
        {
            var counts = items.Select(i => i.Count).Order().ToList();
            var median = counts.Count > 0 ? counts[counts.Count / 2] : 0;
            var threshold = Math.Max(1, median / 2);
            foreach (var (key, count) in items)
            {
                isMajor[(key.Item1, key.Item2, freq)] = count >= threshold;
            }
        }

        return isMajor;
    }
}
