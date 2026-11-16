using System.Globalization;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Trend;

namespace TaxCredit.Application.Features.DraftsRuns;

internal static class UnitSeries
{
    internal static SortedDictionary<long, PyDict> Load(IGoldReadPort gold, long clientId, string unit, string method, string? program)
    {
        var rows = gold.UnitYears(clientId, method, programCode: program, limit: 5000).Items;
        var output = new SortedDictionary<long, PyDict>();
        foreach (var row in rows.Where(r => Equals(r.GetValueOrDefault("worksite_id"), unit)))
        {
            var map = new PyDict();
            foreach (var pair in row) { map.Add(pair.Key, pair.Value); }
            output[FeatureValues.Integer(map, "tax_year")] = map;
        }
        return output;
    }

    internal static bool Complete(PyDict row) =>
        FeatureValues.Integer(row, "months_with_headcount") >= FeatureValues.Integer(row, "months_reachable", 12);
    internal static bool Open(PyDict row) => FeatureValues.Text(row, "status") == "in_progress";
    internal static double Number(PyDict row, string key) =>
        row.TryGetValue(key, out var value) && value is not null ? double.Parse(TaxCredit.Domain.Gold.GoldValues.Str(value), CultureInfo.InvariantCulture) : 0;
    internal static long Inferred(SortedDictionary<long, PyDict> rows) =>
        rows.FirstOrDefault(p => p.Value.TryGetValue("is_base_year", out var value) && value is true).Key is var year && year != 0 ? year : rows.Keys.Min();

    internal static BaseYearResult Price(SortedDictionary<long, PyDict> rows, string state, long baseYear)
    {
        var closed = rows.Where(p => !Open(p.Value)).ToArray();
        if (closed.Length == 0) { closed = rows.ToArray(); }
        var last = closed[^1].Value;
        var threshold = Number(last, "threshold");
        var yearly = new OrderedMap<long, PyDict>();
        var benefits = new OrderedMap<long, YearBenefit>();
        foreach (var (year, row) in closed)
        {
            yearly.Set(year, row);
            benefits.Set(year, new YearBenefit(PyNumber.OfFloat(row["threshold"] is null ? threshold : Number(row, "threshold")),
                PyNumber.OfFloat(Number(row, "per_job_usd"))));
        }
        return UnitTrendTools.UnitTrend(yearly, state, baseYear, new BaseYearSettings(PyNumber.OfFloat(threshold),
            PyNumber.OfFloat(Number(last, "per_job_usd")), FeatureValues.Integer(last, "tranche_years", 5), BenefitByYear: benefits));
    }
}
