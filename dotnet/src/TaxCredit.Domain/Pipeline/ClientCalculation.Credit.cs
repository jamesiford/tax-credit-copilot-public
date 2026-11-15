using System.Globalization;
using System.Numerics;
using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Trend;

namespace TaxCredit.Domain.Pipeline;

public sealed partial class ClientCalculation
{
    private const long DefaultReachableMonths = 12;

    // The credit layer of one method: per unit, the base year, the threshold, the stair-step trend and its installments (the second half of `_replay_unit_series`).
    private void CreditLayer(
        Replayed output, long clientId, string state, string programCode, string method, string runId, PyDateTime appendedAt,
        OrderedMap<long, IReadOnlyList<PyDict>> perYearUnits, OrderedMap<long, long> reachableByYear, HashSet<long> openYears, IReadOnlyDictionary<string, long> overrides)
    {
        var years = perYearUnits.Keys.Order().ToList();
        // Statute is versioned by tax year [ADR-005], so the benefit is resolved PER YEAR; a TY2020 credit priced at TY2025's rate is the defect this prevents.
        var benefitByYear = years.Select(y => (Year: y, Benefit: UnitTrendQueryHelpers.YearBenefit(_p.Library, programCode, y))).ToList();
        var latest = benefitByYear[^1].Benefit;
        var latestThreshold = ProximityCoerce.ToFloat(latest["threshold"]);
        var latestRate = ProximityCoerce.ToFloat(latest["per_job_usd"]);
        var latestWindow = Convert.ToInt64(latest["benefit_period_years"], CultureInfo.InvariantCulture);
        var series = UnitTrendTools.BuildUnitSeries(perYearUnits);

        foreach (var (unitId, unitYears) in PySort.Sorted(series, kv => kv.Key, PyStr.Comparer))
        {
            // An open year is neither a base nor a priced year: its tranches would be opened on months that have not happened.
            var closed = Closed(unitYears, openYears);
            var (baseYear, baseSource) = BaseYearFor(unitId, closed, reachableByYear, overrides);
            var latestDesignation = _p.Designations.DesignationAt(unitId, unitYears.Keys.Max(), clientId);
            var threshold = latestDesignation is not null ? ProximityCoerce.ToFloat(latestDesignation["min_new_jobs"]) : latestThreshold;
            // A negotiated designation is a CURRENT fact about the location, so it overrides the pack in every year (prototype data, DISC-10).
            var perYear = new OrderedMap<long, YearBenefit>();
            var perYearTree = new Dictionary<long, PyDict>();
            foreach (var (year, benefit) in benefitByYear)
            {
                var yearThreshold = latestDesignation is not null ? threshold : ProximityCoerce.ToFloat(benefit["threshold"]);
                var rate = ProximityCoerce.ToFloat(benefit["per_job_usd"]);
                perYear.Set(year, new YearBenefit(PyNumber.OfFloat(yearThreshold), PyNumber.OfFloat(rate)));
                perYearTree[year] = new PyDict().Add("threshold", yearThreshold).Add("per_job_usd", rate);
            }

            var trend = UnitTrendTools.UnitTrend(closed, state, baseYear, new BaseYearSettings(PyNumber.OfFloat(threshold), PyNumber.OfFloat(latestRate), latestWindow, BenefitByYear: perYear));
            var byYear = trend.Years.ToDictionary(y => y.Year);
            var view = BaseYearView.From(trend);
            foreach (var taxYear in years)
            {
                if (!unitYears.TryGetValue(taxYear, out var unitYear))
                {
                    continue;
                }

                output.Master.Add(MasterRow(
                    new MasterContext(clientId, programCode, method, runId, appendedAt, unitId, baseYear, baseSource, threshold, latestDesignation is not null, reachableByYear, openYears),
                    taxYear, unitYear, byYear.GetValueOrDefault(taxYear), trend, view, perYearTree.GetValueOrDefault(taxYear) ?? new PyDict()));
            }

            // An open year's installment is still a forecast.
            output.Installments.AddRange(GoldProjection.UnitCreditInstallmentRows(view, clientId, unitId, programCode, method, years.Where(y => !openYears.Contains(y)).ToList(), runId, appendedAt));
        }
    }

    private static OrderedMap<long, PyDict> Closed(OrderedMap<long, PyDict> unitYears, HashSet<long> openYears)
    {
        var closed = new OrderedMap<long, PyDict>();
        foreach (var (year, unit) in unitYears)
        {
            if (!openYears.Contains(year))
            {
                closed.Set(year, unit);
            }
        }

        return closed.Count > 0 ? closed : unitYears;
    }

    /// <summary>
    /// Python <c>_base_year_for</c>: the base a location is measured from, and where it came from. A saved choice (WI-21) wins when the payroll still supports it
    /// (the year exists and is complete); otherwise the run infers one and says so, because a partial year makes a flattering base.
    /// </summary>
    private static (long Year, string Source) BaseYearFor(string unitId, OrderedMap<long, PyDict> unitYears, OrderedMap<long, long> reachableByYear, IReadOnlyDictionary<string, long> overrides)
    {
        if (overrides.TryGetValue(unitId, out var chosen) && unitYears.TryGetValue(chosen, out var year))
        {
            var raw = year.TryGetValue("months_with_headcount", out var m) ? m : null;
            var months = ProximityCoerce.Truthy(raw) ? ProximityCoerce.ToInt(raw) : 0L;
            var needed = reachableByYear.TryGetValue(chosen, out var r) ? r : DefaultReachableMonths;
            if ((months is BigInteger big ? big : (long)months) >= needed)
            {
                return (chosen, "override");
            }
        }

        var inferred = UnitTrendTools.InferBaseYear(unitYears, reachableByYear);
        return inferred is { } y && unitYears.ContainsKey(y) ? (y, "inferred") : (unitYears.Keys.Min(), "inferred");
    }

    private sealed record MasterContext(
        long ClientId, string ProgramCode, string Method, string RunId, PyDateTime AppendedAt, string UnitId, long BaseYear, string BaseSource, double Threshold, bool Designated,
        OrderedMap<long, long> ReachableByYear, HashSet<long> OpenYears);

    private GoldRow MasterRow(MasterContext c, long taxYear, PyDict unitYear, TrancheYear? closedYear, BaseYearResult trend, BaseYearView view, PyDict statute)
    {
        StairView? stair = closedYear is null ? null : StairView.From(closedYear);
        string? status = null;
        if (c.OpenYears.Contains(taxYear) && taxYear != c.BaseYear)
        {
            var reading = OpenYear.Reading(
                unitYear.TryGetValue("average_headcount", out var average) ? average : null,
                new OpenYearTrend(PyNum.Tree(trend.BaseAverageHeadcount), PyNum.Tree(trend.FinalHighWaterMark), PyNum.Tree(trend.PerJobUsd)), statute, c.Threshold);
            stair = new StairView(reading.NetNew, reading.Threshold, reading.Qualified, reading.EligibleJobs, reading.NewJobsCreated, reading.HighWaterMark, reading.Backfilled, reading.AnnualCreditUsd, reading.PerJobUsd);
            status = UnitTrendTools.StatusInProgress;
        }

        var designation = _p.Designations.DesignationAt(c.UnitId, taxYear, c.ClientId);
        var feins = unitYear.TryGetValue("feins", out var f) && f is List<object?> { Count: > 0 } list ? list : [];
        var monthsReachable = c.ReachableByYear.TryGetValue(taxYear, out var r) ? r : DefaultReachableMonths;
        var monthsWith = (long)unitYear["months_with_headcount"]!;
        var key = new UnitYearKey(
            c.ClientId, c.UnitId, feins.Count == 1 ? ProximityCoerce.Str(feins[0]) : null, c.ProgramCode, c.Method, taxYear, c.BaseYear, c.BaseSource, monthsReachable, false, null,
            c.Designated ? "designation" : "rule_pack",
            status ?? UnitTrendTools.UnitStatus(taxYear, c.BaseYear, stair is not null && GoldValues.Truthy(stair.Qualified), monthsWith, monthsReachable),
            designation is not null && designation.TryGetValue("tier", out var tier) ? tier : null,
            designation is not null && designation.TryGetValue("designation", out var name) ? name : null,
            designation is not null ? "prototype" : "unassigned", c.RunId);
        return GoldProjection.UnitYearMasterRow(key, stair, view, unitYear, c.AppendedAt);
    }
}
