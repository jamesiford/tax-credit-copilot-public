using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

public static partial class Proximity
{
    private const string ClosedNote = "The year is closed.";

    /// <summary>
    /// What it takes over the REST of the year, as of a checkpoint (<c>rest_of_year</c>): the need re-spread over the pay
    /// periods still to be paid, with the larger of the hours and wage needs binding.
    /// </summary>
    /// <param name="periods">Pay periods (<c>pay_period_start</c>, <c>pay_period_end</c>, <c>hours</c>, <c>wages</c>, optional <c>pay_date</c>); dates are <see cref="DateOnly"/> or ISO text.</param>
    /// <param name="floors">The year's floors.</param>
    /// <param name="asOf">The checkpoint (a <see cref="DateOnly"/> or text whose first ten characters are an ISO date).</param>
    /// <param name="yearEnd">The last day of the window, same shapes.</param>
    /// <param name="method"><c>pay_period</c> measures weeks by period length; anything else spans first start to last end.</param>
    /// <param name="decimals">Places to round to; negative values are not modelled (Python's <c>10 ** decimals</c> turns into a float).</param>
    /// <returns>The reading tree, keys in Python order.</returns>
    public static PyDict RestOfYear(
        IReadOnlyList<PyDict> periods,
        StatutoryFloors floors,
        object? asOf,
        object? yearEnd,
        string? method = "min_max",
        int decimals = 2)
    {
        ArgumentNullException.ThrowIfNull(periods);
        ArgumentNullException.ThrowIfNull(floors);
        var checkpoint = AsDate(asOf);
        var end = AsDate(yearEnd);
        var minHours = ProximityCoerce.ToFloat(floors.MinWeeklyHours);
        var minWages = ProximityCoerce.ToFloat(floors.MinWeeklyWages);

        var closed = ClosedPeriods(periods, checkpoint);
        var lags = PaymentLags(periods, checkpoint);
        if (checkpoint >= end)
        {
            return Closed();
        }

        if (closed.Count == 0)
        {
            return new PyDict().Add("state", "no_payroll_to_date").Add("note", "Hired after the checkpoint");
        }

        var firstStart = closed[0].Start;
        var lastEnd = closed[^1].End;
        var weeksToDate = method == "pay_period"
            ? PySum.Sum(closed.Select(p => (double)(PyDate.ToOrdinal(p.End) - PyDate.ToOrdinal(p.Start) + 1) / 7.0).ToList())
            // BA-11: Min-Max spans first PPS to last PPE, exclusive of the end day.
            : (PyDate.ToOrdinal(lastEnd) - PyDate.ToOrdinal(firstStart)) / 7.0;

        // The rest of the year is the whole pay periods still to be PAID inside it, on this employee's own cadence.
        var periodDays = closed.Select(p => (long)(PyDate.ToOrdinal(p.End) - PyDate.ToOrdinal(p.Start) + 1)).Order().ToList();
        var periodLength = periodDays[periodDays.Count / 2];
        var lag = lags.Count > 0 ? lags[lags.Count / 2] : 0;
        var remaining = CountRemainingPeriods(lastEnd, periodLength, lag, end);
        var weeksRemaining = (double)(remaining * periodLength) / 7.0;
        if (weeksToDate <= 0 || weeksRemaining <= 0)
        {
            return Closed();
        }

        var hoursToDate = PySum.Sum(closed.Select(p => p.Hours).ToList());
        var wagesToDate = PySum.Sum(closed.Select(p => p.Wages).ToList());
        var weeksInYear = weeksToDate + weeksRemaining;
        var paceHours = hoursToDate / weeksToDate;
        var paceWages = wagesToDate / weeksToDate;
        var rate = Rate(hoursToDate, wagesToDate);
        double? thresholdRate = ProximityCoerce.Truthy(floors.MinWeeklyHours) ? minWages / minHours : null;

        var neededHoursPace = (minHours * weeksInYear - hoursToDate) / weeksRemaining;
        var neededWagesPace = (minWages * weeksInYear - wagesToDate) / weeksRemaining;
        var extraForHours = PyArith.Max(0.0, neededHoursPace - paceHours);
        var extraWages = PyArith.Max(0.0, neededWagesPace - paceWages);
        var hasRate = rate is not null && ProximityCoerce.Truthy(rate.Value);
        var extraForWages = extraWages > 0 && hasRate ? extraWages / rate!.Value : 0.0;
        if (extraWages > 0 && !hasRate)
        {
            return new PyDict().Add("state", "no_rate").Add("note", "No hours on record to price extra hours at.");
        }

        var extra = PyArith.Max(extraForHours, extraForWages);
        if (extra <= 0)
        {
            return new PyDict()
                .Add("state", "on_pace")
                .Add("weeks_remaining", ProximityCoerce.RoundHalfUp(weeksRemaining, decimals))
                .Add("remaining_pay_periods", remaining)
                .Add("pace_weekly_hours", ProximityCoerce.RoundHalfUp(paceHours, decimals))
                .Add("note", "On pace to clear both floors if the year continues as it has.");
        }

        var state = new OpenReading(checkpoint, weeksToDate, weeksRemaining, remaining, periodLength, hoursToDate, paceHours, neededWagesPace, extra, extraForHours, extraForWages, rate, thresholdRate);
        return OpenState(state, decimals);
    }

    /// <summary>Python <c>_d(value)</c>: a date as is, else <c>date.fromisoformat(str(value)[:10])</c>.</summary>
    private static DateOnly AsDate(object? value) =>
        value is DateOnly d ? d : PyDate.FromIsoFormat(PyStr.Prefix(ProximityCoerce.Str(value), 10));

    private static PyDict Closed() => new PyDict().Add("state", "closed").Add("note", ClosedNote);

    private static object? RequireKey(PyDict p, string key) =>
        p.TryGetValue(key, out var v) ? v : throw ProximityCoerce.Missing(key);

    private static List<ClosedPeriod> ClosedPeriods(IReadOnlyList<PyDict> periods, DateOnly checkpoint)
    {
        var rows = new List<ClosedPeriod>();
        foreach (var p in periods)
        {
            if (AsDate(RequireKey(p, "pay_period_end")) > checkpoint)
            {
                continue;
            }

            // Tuple elements evaluate left to right: start, end, hours, wages.
            var start = AsDate(RequireKey(p, "pay_period_start"));
            var periodEnd = AsDate(RequireKey(p, "pay_period_end"));
            rows.Add(new ClosedPeriod(start, periodEnd, ProximityCoerce.FloatOrZero(p, "hours"), ProximityCoerce.FloatOrZero(p, "wages")));
        }

        // sorted(key=(end, start)): stable, so duplicates keep input order.
        return PySort.Sorted(rows, r => r, Comparer<ClosedPeriod>.Create((a, b) =>
        {
            var c = a.End.CompareTo(b.End);
            return c != 0 ? c : a.Start.CompareTo(b.Start);
        }));
    }

    /// <summary>Days from period end to pay date for each closed period that has a pay date, ascending.</summary>
    private static List<long> PaymentLags(IReadOnlyList<PyDict> periods, DateOnly checkpoint)
    {
        var lags = new List<long>();
        foreach (var p in periods)
        {
            if (!(p.TryGetValue("pay_date", out var payDate) && ProximityCoerce.Truthy(payDate)) || AsDate(RequireKey(p, "pay_period_end")) > checkpoint)
            {
                continue;
            }

            lags.Add(PyDate.ToOrdinal(AsDate(payDate)) - PyDate.ToOrdinal(AsDate(RequireKey(p, "pay_period_end"))));
        }

        lags.Sort();
        return lags;
    }

    /// <summary>
    /// How many more whole periods are paid inside the window. A non-positive period length never terminates in Python until
    /// the date range overflows; the port reproduces that (the <c>OverflowError</c> comes from <see cref="PyDate.AddDays"/>).
    /// </summary>
    private static long CountRemainingPeriods(DateOnly lastEnd, long periodLength, long lagDays, DateOnly end)
    {
        long n = 0;
        while (true)
        {
            var next = PyDate.AddDays(PyDate.AddDays(lastEnd, ToDays(periodLength * (n + 1))), ToDays(lagDays));
            if (next > end)
            {
                return n;
            }

            n++;
        }
    }

    private static int ToDays(long days) =>
        days is >= int.MinValue and <= int.MaxValue ? (int)days : throw new PyOverflowError("date value out of range");

    private static PyDict OpenState(OpenReading s, int decimals)
    {
        if (decimals is < 0 or > 18)
        {
            throw new PyUnsupportedException("rest_of_year with decimals outside 0..18 is not modelled (10 ** decimals leaves int)");
        }

        long step = 1;
        for (var i = 0; i < decimals; i++)
        {
            step *= 10;
        }

        // Rounded UP, so the figure offered actually clears the line.
        var extraUp = ProximityCoerce.CeilOver(s.Extra * step, step);
        var rateLimited = s.ExtraForWages > s.ExtraForHours && s.Rate is not null && s.ThresholdRate is not null && s.Rate < s.ThresholdRate;
        double suggestedHours;
        double suggestedRaise;
        if (rateLimited)
        {
            suggestedHours = ProximityCoerce.CeilOver(s.ExtraForHours * step, step);
            var week = s.PaceHours + suggestedHours;
            var neededRate = week > 0 ? s.NeededWagesPace / week : 0.0;
            suggestedRaise = PyArith.Max(0.0, ProximityCoerce.CeilOver((neededRate - s.Rate!.Value) * 100, 100));
        }
        else
        {
            (suggestedHours, suggestedRaise) = (extraUp, 0.0);
        }

        return new PyDict()
            .Add("state", "open")
            .Add("as_of", s.Checkpoint.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture))
            .Add("weeks_to_date", ProximityCoerce.RoundHalfUp(s.WeeksToDate, decimals))
            .Add("weeks_remaining", ProximityCoerce.RoundHalfUp(s.WeeksRemaining, decimals))
            .Add("remaining_pay_periods", s.Remaining)
            .Add("pay_period_weeks", ProximityCoerce.RoundHalfUp((double)s.PeriodLength / 7.0, decimals))
            .Add("hours_to_date", ProximityCoerce.RoundHalfUp(s.HoursToDate, decimals))
            .Add("pace_weekly_hours", ProximityCoerce.RoundHalfUp(s.PaceHours, decimals))
            .Add("needed_weekly_hours", ProximityCoerce.RoundHalfUp(s.PaceHours + extraUp, decimals))
            .Add("additional_weekly_hours", extraUp)
            .Add("additional_hours_total", ProximityCoerce.RoundHalfUp(extraUp * s.WeeksRemaining, decimals))
            .Add("binding", s.ExtraForWages > s.ExtraForHours ? "wages" : "hours")
            .Add("rate_limited", rateLimited)
            // For a rate-limited employee the honest lever is pay, at current hours.
            .Add("hourly_rate_to_qualify", rateLimited && s.PaceHours > 0 ? ProximityCoerce.RoundHalfUp(s.NeededWagesPace / s.PaceHours, decimals) : null)
            .Add("exceeds_plausible_week", s.PaceHours + extraUp > PlausibleWeeklyHours)
            .Add("suggested_additional_weekly_hours", suggestedHours)
            .Add("suggested_hourly_raise", suggestedRaise);
    }

    private readonly record struct ClosedPeriod(DateOnly Start, DateOnly End, double Hours, double Wages);

    private readonly record struct OpenReading(
        DateOnly Checkpoint,
        double WeeksToDate,
        double WeeksRemaining,
        long Remaining,
        long PeriodLength,
        double HoursToDate,
        double PaceHours,
        double NeededWagesPace,
        double Extra,
        double ExtraForHours,
        double ExtraForWages,
        double? Rate,
        double? ThresholdRate);
}
