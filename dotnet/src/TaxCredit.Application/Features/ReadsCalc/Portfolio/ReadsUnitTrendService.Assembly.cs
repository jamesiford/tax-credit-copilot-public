using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Trend;

namespace TaxCredit.Application.Features.ReadsCalc.Portfolio;

public sealed partial class ReadsUnitTrendService
{
    private List<PyDict> Assemble(UnitTrendRequest query, IReadOnlyList<PayRow> payrollRows, ReplayResult replay)
    {
        var reachable = new OrderedMap<long, long>();
        foreach (var (year, meta) in replay.Meta)
        {
            reachable.Set(year, (long)meta["months_reachable"]!);
        }
        var benefit = PortfolioValues.Dict(replay.Meta.Single(p => p.Key == replay.Meta.Keys.Max()).Value, "benefit");
        return UnitTrendTools.BuildUnitSeries(replay.Units).OrderBy(p => p.Key, PyStr.Comparer)
            .Select(pair => AssembleUnit(query, pair.Key, pair.Value, (replay, reachable, benefit, payrollRows))).ToList();
    }

    private PyDict AssembleUnit(UnitTrendRequest query, string unitId, OrderedMap<long, PyDict> years,
        (ReplayResult Replay, OrderedMap<long, long> Reachable, PyDict Benefit, IReadOnlyList<PayRow> Payroll) context)
    {
        var baseYear = query.BaseYear ?? UnitTrendTools.InferBaseYear(years, context.Reachable) ?? years.Keys.Min();
        if (!years.ContainsKey(baseYear))
        {
            baseYear = years.Keys.Min();
        }
        var designation = TrendDesignations.At(designations, unitId, years.Keys.Max(), query.AccountId);
        var threshold = designation is null ? PortfolioValues.Number(context.Benefit, "threshold") : PortfolioValues.Number(designation, "min_new_jobs");
        var settings = new BaseYearSettings(PyNumber.OfFloat(threshold), PyNumber.OfFloat(PortfolioValues.Number(context.Benefit, "per_job_usd")),
            (long)PortfolioValues.Integer(context.Benefit["benefit_period_years"]));
        var trend = UnitTrendTools.UnitTrend(years, query.State, baseYear, settings);
        var rows = years.OrderBy(p => p.Key).Select(p =>
            AssembleRow(query, unitId, (p.Key, p.Value), trend, threshold, context.Reachable.Single(r => r.Key == p.Key).Value)).ToList();
        var site = referenceData.Worksite(unitId);
        var county = context.Payroll.Where(r => PortfolioValues.Text(r.Dict, "Worksite_ID") == unitId)
            .Select(r => PortfolioValues.Text(r.Dict, "Work_County").Trim()).FirstOrDefault(c => c.Length > 0);
        return UnitFields(unitId, baseYear, query.BaseYear.HasValue, trend, rows)
            .Add("name", site?.Name ?? unitId).Add("county", county ?? site?.County ?? "").Add("city", site?.City ?? "")
            .Add("census_tract", "").Add("threshold", threshold).Add("threshold_source", designation is null ? "rule_pack" : "designation")
            .Add("credit_years", PortfolioValues.List(UnitTrendTools.TrancheColumns(trend,
                Enumerable.Range(0, context.Replay.Units.Count + 1).Select(offset => baseYear + offset).ToList())));
    }

    private PyDict AssembleRow(UnitTrendRequest query, string unitId, (long Year, PyDict Unit) pair,
        BaseYearResult trend, double threshold, long reachable)
    {
        var stair = trend.Years.FirstOrDefault(y => y.Year == pair.Year);
        var designation = TrendDesignations.At(designations, unitId, pair.Year, query.AccountId);
        var row = new PyDict().Add("tax_year", pair.Year);
        foreach (var key in new[] { "month_totals", "total", "average_headcount", "months_with_headcount", "feins" })
        {
            row.Add(key, pair.Unit[key]);
        }
        return row.Add("tier", designation is null ? null : PortfolioValues.Get(designation, "tier"))
            .Add("designation", designation is null ? null : PortfolioValues.Get(designation, "designation"))
            .Add("tier_source", designation is null ? "unassigned" : "prototype")
            .Add("net_new", PyRound.Round(stair?.NetNew ?? 0.0, 2)).Add("threshold", threshold)
            .Add("qualified", stair?.Qualified ?? false).Add("backfilled", stair?.Backfilled ?? false)
            .Add("eligible_jobs", PyRound.Round(stair?.EligibleJobs ?? 0.0, 2))
            .Add("new_jobs_created", PyRound.Round(stair?.NewJobsCreated ?? 0.0, 2))
            .Add("high_water_mark", PyRound.Round(stair is null ? 0.0 : PortfolioValues.Number(stair.HighWaterMark), 2))
            .Add("annual_credit_usd", stair?.AnnualCreditUsd ?? System.Numerics.BigInteger.Zero)
            .Add("is_base_year", pair.Year == trend.BaseYear)
            .Add("status", UnitTrendTools.UnitStatus(pair.Year, trend.BaseYear, stair?.Qualified ?? false,
                (long)pair.Unit["months_with_headcount"]!, reachable));
    }

    private static PyDict UnitFields(string id, long baseYear, bool overridden, BaseYearResult trend, IReadOnlyList<PyDict> rows) =>
        new PyDict().Add("unit_id", id).Add("worksite_id", id)
            .Add("feins", PortfolioValues.List(rows.SelectMany(r => (List<object?>)r["feins"]!).Distinct().Cast<string>().Order(PyStr.Comparer)))
            .Add("base_year", baseYear).Add("base_year_source", overridden ? "override" : "inferred")
            .Add("base_average_headcount", PyRound.Round(PortfolioValues.Number(trend.BaseAverageHeadcount), 2))
            .Add("rows", PortfolioValues.List(rows)).Add("total_annual_credit_usd", trend.TotalAnnualCreditUsd)
            .Add("total_tranche_lifetime_usd", trend.TotalTrancheLifetimeUsd)
            .Add("final_high_water_mark", PyRound.Round(PortfolioValues.Number(trend.FinalHighWaterMark), 2));
}
