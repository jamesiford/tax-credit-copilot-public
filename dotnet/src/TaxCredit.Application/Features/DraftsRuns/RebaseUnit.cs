using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Trend;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Reprices recorded averages through the certified tranche engine without changing the saved run.</summary>
public sealed record RebaseUnitQuery(long ClientId, string UnitId, long BaseYear, string Method = "min_max",
    string? State = null, string? ProgramCode = null) : IQuery<object>;

internal sealed class RebaseUnitHandler(IGoldReadPort gold, ProgramDefaults defaults) : IRequestHandler<RebaseUnitQuery, object>
{
    public ValueTask<object> Handle(RebaseUnitQuery request, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (request.Method is not ("min_max" or "pay_period")) { throw new PyValueError("Unknown calculation method."); }
        using var scope = gold.Scope();
        var run = gold.LatestRun(request.ClientId);
        var rows = UnitSeries.Load(gold, request.ClientId, request.UnitId, request.Method, request.ProgramCode);
        if (rows.Count == 0 || !rows.TryGetValue(request.BaseYear, out var chosen) || !UnitSeries.Complete(chosen) || UnitSeries.Open(chosen))
        {
            throw new DraftsRunsRefusalException(404, "A complete, closed calculated year is required for this location's base.");
        }
        var trend = UnitSeries.Price(rows, defaults.LocationState(request.ClientId, request.UnitId, request.State, request.ProgramCode), request.BaseYear);
        var years = new List<object?>();
        foreach (var (year, row) in rows)
        {
            var entry = new PyDict().Add("tax_year", year).Add("average_headcount", PyRound.Round(UnitSeries.Number(row, "average_headcount"), 2));
            if (year <= request.BaseYear)
            {
                var role = year == request.BaseYear ? "base" : "before_base";
                entry.Add("role", role).Add("status", role);
            }
            else
            {
                var open = UnitSeries.Open(row);
                var stair = open ? OpenYear.Reading(row["average_headcount"],
                    new OpenYearTrend(ToDouble(trend.BaseAverageHeadcount), ToDouble(trend.FinalHighWaterMark), ToDouble(trend.PerJobUsd)),
                    row, UnitSeries.Number(row, "threshold")).ToDict() : trend.Years.Single(y => y.Year == year).ToDict();
                entry.Add("role", "evaluated").Add("year_number", year - request.BaseYear)
                    .Add("net_new_vs_base", PyRound.Round(UnitSeries.Number(stair, "net_new"), 2)).Add("threshold", stair["threshold"])
                    .Add("qualified", stair["qualified"]).Add("eligible_jobs", PyRound.Round(UnitSeries.Number(stair, "eligible_jobs"), 2))
                    .Add("annual_credit_usd", stair["annual_credit_usd"]).Add("backfilled", stair["backfilled"])
                    .Add("status", open ? "in_progress" : UnitTrendTools.UnitStatus(year, request.BaseYear, stair["qualified"] is true,
                        FeatureValues.Integer(row, "months_with_headcount"), FeatureValues.Integer(row, "months_reachable", 12)));
            }
            years.Add(entry);
        }
        var oldTotal = PyRound.RoundToInteger(rows.Values.Sum(r => UnitSeries.Number(r, "annual_credit_usd")));
        var inferred = UnitSeries.Inferred(rows);
        return ValueTask.FromResult<object>(new PyDict().Add("client_id", request.ClientId).Add("worksite_id", request.UnitId)
            .Add("method", request.Method).Add("base_year", request.BaseYear).Add("inferred_base_year", inferred)
            .Add("candidate_base_years", rows.Where(p => UnitSeries.Complete(p.Value) && !UnitSeries.Open(p.Value)).Select(p => (object?)p.Key).ToList())
            .Add("base_average_headcount", PyRound.Round(ToDouble(trend.BaseAverageHeadcount), 2)).Add("years", years)
            .Add("total_annual_credit_usd", trend.TotalAnnualCreditUsd).Add("run_total_annual_credit_usd", oldTotal)
            .Add("delta_annual_credit_usd", trend.TotalAnnualCreditUsd - oldTotal).Add("run_id", run?.GetValueOrDefault("run_id"))
            .Add("saved", false).Add("note", $"Re-priced against TY{request.BaseYear} from the run's own averages. Not saved, and not the certified figures — those are measured from TY{inferred}."));
    }

    private static double ToDouble(PyNumber number) => number.IsInt ? number.IntValue : number.FloatValue;
}
