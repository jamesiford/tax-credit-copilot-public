using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Trend;

namespace TaxCredit.Application.Features.ReadsCalc.Calculations;

public sealed partial class ReadsCalculationViews
{
    private sealed record LocationPrice(PyDict Reading, BaseYearResult Trend);

    private static Dictionary<long, PyDict> LocationSeries(IEnumerable<IReadOnlyDictionary<string, object?>> rows, string site) =>
        rows.Where(row => Equals(row.GetValueOrDefault("worksite_id"), site))
            .ToDictionary(row => (long)ReadValues.Number(row["tax_year"]), ReadValues.Engine);

    private static long BaseYear(Dictionary<long, PyDict> rows) =>
        rows.Where(pair => pair.Value.TryGetValue("is_base_year", out var value) && ReadValues.Bool(value))
            .Select(pair => (long?)pair.Key).FirstOrDefault() ?? rows.Keys.Min();

    private static int? OpenMonths(PyDict row) =>
        Text(row, "status") == "in_progress" && Num(row, "months_reachable") > 0 ? (int)Num(row, "months_reachable") : null;

    private static PyDict? UnitReading(OneZeroResult result, string site, int? closedMonths = null)
    {
        var summary = Rollups.ByTwoFields(OneZeroResultTrees.Matrix(result), "Worksite_ID", "Entity_FEIN");
        var unit = UnitTrendTools.AggregateUnits(summary).FirstOrDefault(row => Text(row, "unit_id") == site);
        if (unit is not null && closedMonths is > 0)
        {
            var totals = ((System.Collections.IEnumerable)unit["month_totals"]!).Cast<object?>().Take(closedMonths.Value);
            unit.Set("average_headcount", PyRound.Round(totals.Sum(ReadValues.Number) / closedMonths.Value, 2));
        }
        return unit;
    }

    private static BaseYearResult LocationTrend(Dictionary<long, PyDict> rows, string state, long baseYear, long year, double? average = null, bool asIfClosed = false)
    {
        var closed = rows.Where(pair => OpenMonths(pair.Value) is null || asIfClosed && pair.Key == year).ToDictionary();
        if (closed.Count == 0)
        {
            closed = rows;
        }

        var latest = closed[closed.Keys.Max()];
        var threshold = Num(latest, "threshold");
        var benefits = new OrderedMap<long, YearBenefit>();
        var series = new OrderedMap<long, PyDict>();
        foreach (var (key, row) in closed.OrderBy(pair => pair.Key))
        {
            benefits.Set(key, new YearBenefit(PyNumber.OfFloat(row.TryGetValue("threshold", out var value) && value is not null ? Num(row, "threshold") : threshold),
                PyNumber.OfFloat(Num(row, "per_job_usd"))));
            series.Set(key, Dict(("average_headcount", key == year && average is not null ? average.Value : Num(row, "average_headcount"))));
        }
        return UnitTrendTools.UnitTrend(series, state, baseYear, new BaseYearSettings(PyNumber.OfFloat(threshold),
            PyNumber.OfFloat(Num(latest, "per_job_usd")), (long)(Num(latest, "tranche_years") == 0 ? 5 : Num(latest, "tranche_years")), BenefitByYear: benefits));
    }

    private static LocationPrice PriceLocation(Dictionary<long, PyDict> rows, string state, long year, long baseYear, double? average = null)
    {
        var trend = LocationTrend(rows, state, baseYear, year, average);
        var target = rows[year];
        if (OpenMonths(target) is not null)
        {
            var statute = Select(target, "threshold", "per_job_usd");
            var reading = OpenYear.Reading(average ?? Num(target, "average_headcount"),
                new OpenYearTrend(trend.BaseAverageHeadcount, trend.FinalHighWaterMark, trend.PerJobUsd), statute, Num(target, "threshold"));
            return new LocationPrice(reading.ToDict(), trend);
        }
        var stair = trend.Years.FirstOrDefault(row => row.Year == year)
            ?? throw new ReadRefusalException(404, "The selected year is not a priced year in the location's series.");
        return new LocationPrice(stair.ToFields(), trend);
    }

    private static double? RunRate(Dictionary<long, PyDict> rows, string state, long year, long baseYear, double? average = null) =>
        OpenMonths(rows[year]) is null ? null
            : (double)LocationTrend(rows, state, baseYear, year, average, asIfClosed: true).Years.First(row => row.Year == year).AnnualCreditUsd;

    private static PyDict LocationReading(LocationPrice price, long year, long baseYear, int months, int reachable, bool open)
    {
        var row = price.Reading;
        return Dict(("average_headcount", PyRound.Round(Num(row, "average_headcount"), 2)),
            ("base_average_headcount", PyRound.Round(Num(row, "base_average_headcount"), 2)),
            ("net_new_vs_base", PyRound.Round(Num(row, "net_new"), 2)), ("threshold", row["threshold"]),
            ("jobs_margin", SignedMargin(row)), ("qualified", row["qualified"]),
            ("status", open ? UnitTrendTools.StatusInProgress : UnitTrendTools.UnitStatus(year, baseYear, ReadValues.Bool(row["qualified"]), months, reachable)),
            ("eligible_jobs", PyRound.Round(Num(row, "eligible_jobs"), 2)),
            ("annual_credit_usd", PyRound.RoundToInteger(Num(row, "annual_credit_usd"))),
            ("series_credit_usd", price.Trend.TotalAnnualCreditUsd));
    }

    private static double SignedMargin(PyDict stair) => PyRound.Round(
        Num(stair, "average_headcount") - Num(stair, "base_average_headcount") - Num(stair, "threshold"), 2);
}
