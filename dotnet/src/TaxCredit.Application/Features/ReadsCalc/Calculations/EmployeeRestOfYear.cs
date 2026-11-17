using System.Globalization;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Application.Features.ReadsCalc.Calculations;

/// <summary>Changes future source lines as one scenario; statutory eligibility remains the certified engine's decision.</summary>
public static class EmployeeRestOfYear
{
    /// <summary>Keeps paid periods immutable and scales each future period once, including split pay-code lines.</summary>
    public static (IReadOnlyList<PayRow> Rows, PyDict Applied) Apply(
        IReadOnlyList<PayRow> rows, string employeeId, DateOnly asOf, double extraWeeklyHours,
        DateOnly? windowEnd = null, double hourlyRaise = 0)
    {
        ArgumentNullException.ThrowIfNull(rows);
        var mine = rows.Where(row => Equals(row.Get("Employee_ID"), employeeId)).ToList();
        var closed = mine.Where(row => Day(row, "Pay_Period_End") <= asOf).ToList();
        var hours = closed.Sum(row => Number(row, "Hours_Worked"));
        var wages = closed.Sum(row => Number(row, "Gross_Wages"));
        if (closed.Count == 0 || hours <= 0)
        {
            throw new ReadRefusalException(404, "No hours closed by the checkpoint to take a pace from.");
        }

        var weeks = Math.Max((closed.Max(row => Day(row, "Pay_Period_End")).DayNumber - closed.Min(row => Day(row, "Pay_Period_Start")).DayNumber) / 7.0, 1 / 7.0);
        var pace = hours / weeks;
        var rate = wages / hours;
        var open = mine.Where(row => Day(row, "Pay_Period_End") > asOf).ToList();
        var projected = open.Count == 0 && windowEnd is { } end && asOf < end ? ProjectPeriods(closed, asOf, end) : [];
        open.AddRange(projected);
        var periods = open.GroupBy(row => (row.Get("Pay_Period_Start"), row.Get("Pay_Period_End"))).ToList();
        if (periods.Count == 0)
        {
            throw new ReadRefusalException(404, "No pay periods after the checkpoint: the year is closed for this employee.");
        }

        var replacements = new Dictionary<PayRow, PayRow>(ReferenceEqualityComparer.Instance);
        foreach (var period in periods)
        {
            ReplacePeriod(period.ToList(), pace + extraWeeklyHours, rate + hourlyRaise, replacements);
        }

        var moved = rows.Select(row => replacements.GetValueOrDefault(row, row)).Concat(projected.Select(row => replacements[row])).ToList();
        var applied = new PyDict().Add("pace_weekly_hours", PyRound.Round(pace, 2)).Add("projected_weekly_hours", PyRound.Round(pace + extraWeeklyHours, 2))
            .Add("rate", PyRound.Round(rate, 2)).Add("projected_rate", PyRound.Round(rate + hourlyRaise, 2))
            .Add("periods_changed", (long)periods.Count).Add("periods_projected", (long)projected.Count);
        return (moved, applied);
    }

    private static void ReplacePeriod(List<PayRow> lines, double weeklyHours, double rate, Dictionary<PayRow, PayRow> replacements)
    {
        var first = lines[0];
        var weeks = (Day(first, "Pay_Period_End").DayNumber - Day(first, "Pay_Period_Start").DayNumber + 1) / 7.0;
        var targetHours = weeklyHours * weeks;
        var targetWages = targetHours * rate;
        var hours = lines.Sum(line => Number(line, "Hours_Worked"));
        var wages = lines.Sum(line => Number(line, "Gross_Wages"));
        for (var index = 0; index < lines.Count; index++)
        {
            var line = lines[index];
            var copy = line.Dict.Aggregate(new PyDict(), (result, pair) => result.Add(pair.Key, pair.Value));
            copy.Set("Hours_Worked", hours > 0 ? Number(line, "Hours_Worked") * targetHours / hours : index == 0 ? targetHours : 0)
                .Set("Gross_Wages", wages > 0 ? Number(line, "Gross_Wages") * targetWages / wages : index == 0 ? targetWages : 0);
            replacements[line] = PayRow.Of(copy);
        }
    }

    private static List<PayRow> ProjectPeriods(List<PayRow> closed, DateOnly asOf, DateOnly windowEnd)
    {
        var lastEnd = closed.Max(row => Day(row, "Pay_Period_End"));
        var template = closed.Where(row => Day(row, "Pay_Period_End") == lastEnd).MaxBy(row => Number(row, "Hours_Worked"))!;
        var length = Day(template, "Pay_Period_End").DayNumber - Day(template, "Pay_Period_Start").DayNumber;
        if (length < 0)
        {
            throw new ReadRefusalException(422, "A pay period cannot end before it starts.");
        }

        var lag = template.Get("Pay_Date") is null ? 0 : Day(template, "Pay_Date").DayNumber - lastEnd.DayNumber;
        var projected = new List<PayRow>();
        var start = lastEnd.AddDays(1);
        while (start.DayNumber + length + lag <= windowEnd.DayNumber)
        {
            var end = start.AddDays(length);
            var payDate = end.AddDays(lag);
            if (end > asOf)
            {
                var copy = template.Dict.Aggregate(new PyDict(), (result, pair) => result.Add(pair.Key, pair.Value));
                projected.Add(PayRow.Of(copy.Set("Pay_Period_Start", Iso(start)).Set("Pay_Period_End", Iso(end)).Set("Pay_Date", Iso(payDate))
                    .Set("Tax_Year", (long)payDate.Year).Set("Hours_Worked", 0.0).Set("Gross_Wages", 0.0).Set("_Source_Payroll_Id", null).Set("_Projected", true)));
            }
            start = end.AddDays(1);
        }
        return projected;
    }

    private static string Iso(DateOnly day) => day.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    private static DateOnly Day(PayRow row, string key) => DateOnly.ParseExact(((string)row.Get(key)!)[..10], "yyyy-MM-dd", CultureInfo.InvariantCulture);
    private static double Number(PayRow row, string key) => ReadValues.Number(row.Get(key));
}
