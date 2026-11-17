using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Domain.Forecast;

/// <summary>The optional inputs of <see cref="ForecastProjection.ProjectStateYearEnd"/> (Python keyword arguments).</summary>
/// <param name="FiscalYearEndMonth"><c>fiscal_year_end_month</c>: last month of the fiscal year (12 = calendar).</param>
/// <param name="MonthsElapsed"><c>months_elapsed</c>; <c>null</c> derives it from <c>as_of</c> against the fiscal window.</param>
/// <param name="YtdAverageHeadcount"><c>ytd_average_headcount</c> already READ from the run; <c>null</c> replays <c>rows</c>.</param>
/// <param name="PriorAverageHeadcount"><c>prior_average_headcount</c> already READ from the run; <c>null</c> replays <c>prior_rows</c>.</param>
public sealed record ForecastOptions(long FiscalYearEndMonth = 12, long? MonthsElapsed = null, double? YtdAverageHeadcount = null, double? PriorAverageHeadcount = null);

/// <summary>
/// Python <c>tools/forecast.py</c> [N2] FCST-01: the linear run-rate projection of a state's year-end One/Zero credit from
/// year-to-date actuals. Deterministic compute over rows and a rule library; no seasonality, no extrapolation beyond the run-rate.
/// </summary>
/// <param name="library">Where rule packs and the credit math come from (Python <c>tools.credit_math</c>).</param>
public sealed class ForecastProjection(RuleLibrary library)
{
    private const string RoadmapTag = "N2";
    private const string Story = "FCST-01";

    /// <summary>
    /// Python <c>_months_elapsed</c>: how many of the 12 fiscal months have closed by <paramref name="asOf"/> (a month counts once its
    /// month-end is on or before it), clamped to 1..12 so a forecast always has a month of actuals and never claims more than a year.
    /// </summary>
    /// <param name="analysisStart">First day of the fiscal window.</param>
    /// <param name="asOf">The as-of date.</param>
    /// <returns>The month count, 1 to 12.</returns>
    public static long MonthsElapsed(DateOnly analysisStart, DateOnly asOf)
    {
        var elapsed = OneZeroCalendar.TwelveMonthEnds(analysisStart).Count(me => me <= asOf);
        return Math.Max(1, Math.Min(elapsed, 12));
    }

    /// <summary>
    /// Python <c>_ytd_average_headcount</c>: the first <paramref name="monthsElapsed"/> month totals of every unit, summed and divided by
    /// the months elapsed, rounded to 2 places. A count above 12 still divides by itself (the slice just runs out), as in Python.
    /// </summary>
    /// <param name="monthTotalsByUnit">Each unit's <c>month_totals</c> (ints or floats, as the caller holds them).</param>
    /// <param name="monthsElapsed">The denominator; zero or less answers 0.0.</param>
    /// <returns>The run-rate headcount.</returns>
    public static double YtdAverageHeadcount(IReadOnlyList<IReadOnlyList<PyNumber>> monthTotalsByUnit, long monthsElapsed)
    {
        ArgumentNullException.ThrowIfNull(monthTotalsByUnit);
        if (monthsElapsed <= 0)
        {
            return 0.0;
        }

        // `total = 0.0; total += sum(unit[:n])`: the inner sum is Python's compensated builtin, the outer addition is plain.
        var total = 0.0;
        foreach (var unit in monthTotalsByUnit)
        {
            var slice = unit.Take((int)Math.Min(monthsElapsed, int.MaxValue)).ToList();
            total += ProximityCoerce.ToFloat(PySum.Sum(slice));
        }

        return PyRound.Round(total / monthsElapsed, 2);
    }

    /// <summary>
    /// Python <c>project_state_year_end</c>: projects a state's year-end credit from YTD actuals. Returns <c>null</c> when the state has no
    /// rule pack. <paramref name="rows"/> are replayed in full (NOT filtered by state, as in Python) unless the average is supplied.
    /// </summary>
    /// <param name="state">A state, or a program code (it then prices that program).</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="rows">Pay-period rows already bucketed into <paramref name="taxYear"/>.</param>
    /// <param name="priorRows">Rows bucketed into the prior year; filtered to the state's worksites here.</param>
    /// <param name="asOf">The projection date.</param>
    /// <param name="options">The keyword arguments.</param>
    /// <returns>The projection tree, or <c>null</c>.</returns>
    public PyDict? ProjectStateYearEnd(string state, long taxYear, IReadOnlyList<PayrollRow> rows, IReadOnlyList<PayrollRow> priorRows, DateOnly asOf, ForecastOptions? options = null)
    {
        ArgumentNullException.ThrowIfNull(state);
        ArgumentNullException.ThrowIfNull(rows);
        ArgumentNullException.ThrowIfNull(priorRows);
        options ??= new ForecastOptions();
        var key = PyStr.Upper(state);
        var stateU = library.StateOf(state);
        var pack = library.LoadPackOneZero(key, taxYear);
        if (pack is null)
        {
            return null;
        }

        var fy = options.FiscalYearEndMonth;
        var analysisStart = OneZeroCalendar.FiscalWindowStart(taxYear, fy);
        var monthsElapsed = options.MonthsElapsed ?? MonthsElapsed(analysisStart, asOf);
        double ytdAvg;
        if (options.YtdAverageHeadcount is null)
        {
            var full = PayPeriodMethod.Run(rows, taxYear, analysisStart, pack, fy);
            ytdAvg = YtdAverageHeadcount(full.Summary.Select(u => (IReadOnlyList<PyNumber>)u.MonthTotals.Select(PyNumber.OfFloat).ToList()).ToList(), monthsElapsed);
        }
        else
        {
            ytdAvg = PyRound.Round(options.YtdAverageHeadcount.Value, 2);
        }

        // Linear run-rate: projected full-year Average Headcount == the YTD run-rate, assumed to hold through year-end.
        var projectedAvg = ytdAvg;
        var priorAvg = options.PriorAverageHeadcount ?? PriorAverage(key, stateU, taxYear, priorRows, fy);
        var credit = library.ApplyOneZeroStateCredit(key, projectedAvg, priorAvg, null);
        return Result(credit, (stateU, taxYear, asOf), (monthsElapsed, ytdAvg, projectedAvg, priorAvg));
    }

    // The frozen comparison base for net-new: the state's prior-year Average Headcount, 0.0 when there is nothing to replay.
    private double PriorAverage(string key, string stateU, long taxYear, IReadOnlyList<PayrollRow> priorRows, long fy)
    {
        var priorPack = library.LoadPackOneZero(key, taxYear - 1);
        var prefix = stateU + "_";
        var stateRows = priorRows.Where(r => (r.RequireWorksiteId() ?? "None").StartsWith(prefix, StringComparison.Ordinal)).ToList();
        if (priorPack is null || stateRows.Count == 0)
        {
            return 0.0;
        }

        return PayPeriodMethod.Run(stateRows, taxYear - 1, OneZeroCalendar.FiscalWindowStart(taxYear - 1, fy), priorPack, fy).AnnualAverage;
    }

    private static PyDict Result(PyDict credit, (string StateU, long TaxYear, DateOnly AsOf) scope, (long Months, double Ytd, double Projected, double Prior) avg)
    {
        var threshold = GetOr(credit, "threshold", null) is { } t && ProximityCoerce.Truthy(t) ? ProximityCoerce.ToFloat(t) : 0.0;
        // The "finish line": the Average Headcount at which net-new first clears the statutory minimum.
        var finishLine = PyRound.Round(avg.Prior + threshold, 2);
        var gap = PyRound.Round(PyArith.Max(0.0, finishLine - avg.Projected), 2);
        var netNew = PyRound.Round(PyArith.Max(0.0, avg.Projected - avg.Prior), 2);
        var annual = GetOr(credit, "annual_credit_usd", 0L);
        var asOfText = scope.AsOf.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);
        var note = $"Linear run-rate from {avg.Months} month(s) of {scope.TaxYear} actuals (YTD Average Monthly Headcount {PyFloat.Repr(avg.Ytd)}); "
            + "assumes the current run-rate holds through year-end. No seasonality applied.";
        TrailContext.Current?.Record(
            $"{scope.StateU}: project {scope.TaxYear} year-end credit (run-rate as of {asOfText})",
            new PyDict().Add("months_elapsed", avg.Months).Add("ytd_average_headcount", avg.Ytd).Add("prior_year_average_headcount", avg.Prior).Add("threshold", threshold),
            "projected_avg = ytd_avg (run-rate); net_new = max(0, projected_avg - prior_avg); finish_line = prior_avg + threshold",
            new PyDict().Add("projected_average_headcount", avg.Projected).Add("projected_credit_usd", annual).Add("gap_to_finish", gap),
            $"{Story} run-rate forecast (no extrapolation beyond run-rate)");
        return new PyDict()
            .Add("_roadmap_tag", RoadmapTag)
            .Add("_story", Story)
            .Add("state", scope.StateU)
            .Add("program_code", GetOr(credit, "credit_code", null))
            .Add("tax_year", scope.TaxYear)
            .Add("as_of", asOfText)
            .Add("months_elapsed", avg.Months)
            .Add("ytd_average_headcount", avg.Ytd)
            .Add("projected_average_headcount", avg.Projected)
            .Add("prior_year_average_headcount", avg.Prior)
            .Add("threshold", threshold)
            .Add("finish_line_headcount", finishLine)
            .Add("gap_to_finish", gap)
            .Add("projected_net_new", netNew)
            .Add("on_track", avg.Projected + 1e-9 >= finishLine)
            .Add("projected_annual_credit_usd", annual)
            .Add("projected_lifetime_credit_usd", GetOr(credit, "lifetime_credit_usd", 0L))
            .Add("credit_code", GetOr(credit, "credit_code", null))
            .Add("credit_name", GetOr(credit, "credit_name", null))
            .Add("method_note", note);
    }

    // Python `d.get(key, default)`.
    private static object? GetOr(PyDict d, string key, object? fallback) => d.TryGetValue(key, out var v) ? v : fallback;
}
