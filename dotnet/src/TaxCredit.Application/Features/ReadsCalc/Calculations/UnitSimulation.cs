using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Simulation;

namespace TaxCredit.Application.Features.ReadsCalc.Calculations;

public sealed partial class ReadsCalculationViews
{
    private PyDict SimulateUnit(ReadArguments args)
    {
        var year = Year(args);
        var client = args.Client("client_id") ?? throw new ReadRefusalException(422, "client_id is required.");
        var site = args.Text("worksite_id") ?? throw new ReadRefusalException(422, "worksite_id is required.");
        var method = args.Method();
        var code = args.Text("program_code");
        var state = defaults.LocationState(client, site, args.Text("state", "GA"), code);
        using var scope = gold.Scope();
        var latestRun = gold.LatestRun(client, code);
        var series = LocationSeries(gold.UnitYears(client, method, programCode: code, limit: 5000).Items, site);
        if (series.Count == 0)
        {
            throw new ReadRefusalException(404, "No calculated run holds that location for this client.");
        }

        if (!series.TryGetValue(year, out var target))
        {
            throw new ReadRefusalException(404, "The run does not hold that location-year.");
        }

        var baseYear = BaseYear(series);
        if (baseYear == year)
        {
            throw new ReadRefusalException(404, "Changing the base year is a restatement, not a what-if about that year.");
        }

        var run = resolver.ResolveClientRun(client, state, year, programCode: code, requireProgram: true);
        var atSite = run.Rows.Where(row => Equals(row.Get("Worksite_ID"), site)).ToList();
        if (atSite.Count == 0)
        {
            throw new ReadRefusalException(404, "No payroll at that location inside the client's fiscal window.");
        }

        var closed = OpenMonths(target);
        var beforeUnit = UnitReading(RunClient(run, EngineRows(run.Rows), method), site, closed);
        if (beforeUnit is null || Math.Abs(Num(beforeUnit, "average_headcount") - Num(target, "average_headcount")) > 0.011)
        {
            throw new ReadRefusalException(404, "Payroll no longer reproduces the run that wrote the grid. Re-run the calculation before projecting.");
        }

        var lever = Lever(args, run.Pack, state, "add_headcount", 1) with { Fein = null };
        var (moved, detail) = OneZeroLever.Apply(EngineRows(atSite), lever);
        var afterRows = EngineRows(run.Rows.Where(row => !Equals(row.Get("Worksite_ID"), site))).Concat(moved).ToList();
        var afterUnit = UnitReading(RunClient(run, afterRows, method), site, closed) ?? Dict(("average_headcount", 0.0), ("months_with_headcount", 0L));
        var baselinePrice = PriceLocation(series, state, year, baseYear);
        if (ReadValues.Bool(baselinePrice.Reading["qualified"]) != ReadValues.Bool(target["qualified"])
            || Math.Abs(Num(baselinePrice.Reading, "annual_credit_usd") - Num(target, "annual_credit_usd")) > 1)
        {
            throw new ReadRefusalException(404, "Re-pricing the location's series does not reproduce the grid. Re-run the calculation.");
        }

        var projectedPrice = PriceLocation(series, state, year, baseYear, Num(afterUnit, "average_headcount"));
        var reachable = (int)(Num(target, "months_reachable") == 0 ? 12 : Num(target, "months_reachable"));
        var baseline = LocationReading(baselinePrice, year, baseYear,
            (int)(Num(target, "months_with_headcount") == 0 ? Num(beforeUnit, "months_with_headcount") : Num(target, "months_with_headcount")), reachable, closed is not null);
        var projected = LocationReading(projectedPrice, year, baseYear, (int)Num(afterUnit, "months_with_headcount"), reachable, closed is not null);
        return UnitSimulationResult(new UnitProjection(client, site, state, run.ProgramCode, year, method, baseYear, series, closed,
            latestRun?.GetValueOrDefault("run_id"), lever, detail, baseline, projected, Num(afterUnit, "average_headcount")), run.Pack);
    }

    private sealed record UnitProjection(long Client, string Site, string State, string Code, long Year, string Method,
        long BaseYear, Dictionary<long, PyDict> Series, int? Closed, object? RunId, LeverRequest Lever, string Detail,
        PyDict Before, PyDict After, double AfterAverage);

    private static PyDict UnitSimulationResult(UnitProjection p, TaxCredit.Domain.Calculation.OneZeroPack pack)
    {
        PyDict? runRate = null;
        if (p.Closed is not null)
        {
            var before = RunRate(p.Series, p.State, p.Year, p.BaseYear);
            var after = RunRate(p.Series, p.State, p.Year, p.BaseYear, p.AfterAverage);
            runRate = Dict(("basis", "run_rate"), ("before_usd", before), ("after_usd", after), ("delta_usd", after - before),
                ("note", $"Run-rate estimate: TY{p.Year} priced as if it closed at its pace over the {p.Closed} closed months, against {p.Site}'s TY{p.BaseYear} base. Nothing is claimable until the year closes."));
        }
        return Dict(("scope", Dict(("client_id", p.Client), ("worksite_id", p.Site), ("state", p.State), ("program_code", p.Code), ("tax_year", p.Year), ("method", p.Method))),
            ("action", p.Lever.Action), ("magnitude", p.Lever.Magnitude),
            ("detail", p.Detail.Replace($"in {p.State}", $"at {p.Site}", StringComparison.Ordinal).Replace($"from {p.State}", $"at {p.Site}", StringComparison.Ordinal)
                .Replace($"across all {p.State} pay periods", $"across {p.Site}'s pay periods", StringComparison.Ordinal)),
            ("base_year", p.BaseYear), ("series_years", new[] { p.Series.Keys.Min(), p.Series.Keys.Max() }),
            ("eligibility_floors", Select(Floors(pack, p.Year), "min_weekly_hours", "min_weekly_wages")), ("baseline", p.Before), ("projected", p.After),
            ("delta", Delta(p.Before, p.After, "average_headcount", "net_new_vs_base", "annual_credit_usd", "series_credit_usd")),
            ("open_year", p.Closed is null ? null : Dict(("months_closed", p.Closed),
                ("note", $"TY{p.Year} is still open. Both sides are read on its {p.Closed} closed months, against {p.Site}'s TY{p.BaseYear} base: 'qualified' means on track to date, and the only credit shown is a labelled run-rate estimate — nothing is claimable until the year closes. A hire here is counted as if on payroll for those months."))),
            ("run_rate", runRate), ("run_id", p.RunId),
            ("method_note", $"Priced as the location grid prices it: {p.Site} against its own TY{p.BaseYear} base, under TY{p.Year} statute. The lever changes only this location's payroll; everyone's eligibility is re-decided by the same engine."));
    }
}
