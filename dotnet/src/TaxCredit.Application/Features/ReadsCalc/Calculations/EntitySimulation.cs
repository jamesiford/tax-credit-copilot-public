using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Simulation;

namespace TaxCredit.Application.Features.ReadsCalc.Calculations;

public sealed partial class ReadsCalculationViews
{
    private PyDict SimulateOneZero(ReadArguments args)
    {
        var year = Year(args);
        var client = args.Client("client_id");
        var (state, code, file) = defaults.PricedProgram(client, args.Text("state"), args.Text("program_code"), year);
        var years = library.AuthoredYears(file);
        if (!years.Contains(year))
        {
            throw new ReadRefusalException(422, "No authored year-scoped rule pack for that projection.");
        }

        var pack = library.LoadPackOneZero(code, year) ?? throw new ReadRefusalException(400, "The program has no one_zero block.");
        var all = Rows(args, clientKey: "client_id");
        var window = source.WindowForStateYear(client, code, year);
        var rows = Headcount.RowsForStateYear(EngineRows(all), state, year, window);
        var fein = args.Text("fein");
        if (!string.IsNullOrEmpty(fein))
        {
            rows = rows.Where(r => r.EntityFein.Text == fein).ToList();
        }

        if (rows.Count == 0)
        {
            throw new ReadRefusalException(404, "No pay-period rows for that scope.");
        }

        var prior = 0.0;
        if (years.Contains(year - 1))
        {
            var priorRows = all.Where(r => string.IsNullOrEmpty(fein) || Equals(r.Get("Entity_FEIN"), fein));
            prior = Headcount.AverageHeadcount(EngineRows(priorRows), state, year - 1, library.LoadPackOneZero(code, year - 1)!,
                source.WindowForStateYear(client, code, year - 1));
        }
        var lever = Lever(args, pack, state);
        var engine = new OneZeroSimulation(library);
        var before = engine.OneZeroSnapshot(rows, year, code, pack, PyNumber.OfFloat(prior));
        var (moved, detail) = OneZeroLever.Apply(rows, lever);
        var after = engine.OneZeroSnapshot(moved, year, code, pack, PyNumber.OfFloat(prior));
        return Dict(("as_of", Today), ("scope", Dict(("state", state), ("program_code", code), ("fein", fein), ("tax_year", year), ("client_id", client))),
            ("action", lever.Action), ("magnitude", lever.Magnitude), ("detail", detail), ("base_average_headcount", prior),
            ("base_year", prior == 0 ? null : year - 1), ("eligibility_floors", Select(Floors(pack, year), "min_weekly_hours", "min_weekly_wages", "pt_band_hours", "pt_weight")),
            ("baseline", before), ("projected", after), ("delta", Delta(before, after, "average_headcount", "eligible_employee_count", "annual_credit_usd", "lifetime_credit_usd")), ("_roadmap_tag", "J2"));
    }

    private static LeverRequest Lever(ReadArguments args, OneZeroPack pack, string state, string actionDefault = "adjust_hours", double magnitudeDefault = 0)
    {
        var action = args.Text("action", actionDefault)!;
        if (action is not ("add_headcount" or "remove_headcount" or "adjust_hours" or "adjust_wages"))
        {
            throw new ReadRefusalException(422, "Invalid simulation action.");
        }

        var magnitude = args.Number("magnitude", magnitudeDefault);
        // A GET must have a finite work bound, not materialize an arbitrarily large synthetic workforce.
        if (Math.Abs(magnitude) > 10_000)
        {
            throw new ReadRefusalException(422, "Simulation magnitude exceeds the operational limit of 10000.");
        }

        var hours = args.OptionalNumber("hire_weekly_hours");
        var rate = args.OptionalNumber("hire_hourly_rate");
        if (hours is <= 0 or > 80 || rate is <= 0 or > 500)
        {
            throw new ReadRefusalException(422, "Hired role hours or rate is outside the permitted range.");
        }

        return new LeverRequest(action, magnitude, pack, state, args.Text("fein"), hours, rate);
    }

    private static PyDict Delta(PyDict before, PyDict after, params string[] keys) => keys.Aggregate(new PyDict(),
        (result, key) => result.Add(key, PyRound.Round(Num(after, key) - Num(before, key), 2)));

    private PyDict SimulatePortfolio(ReadArguments args)
    {
        var year = Year(args);
        var (state, code) = defaults.ResolveProgram(null, args.Text("state"), args.Text("program_code"), year, requireProgram: true);
        if (code is null)
        {
            throw new ReadRefusalException(404, "No program maps to that state.");
        }

        var pack = library.LoadPackOneZero(code, year) ?? throw new ReadRefusalException(404, "No authored statute for that state-year.");
        OneZeroPack? priorPack;
        try { priorPack = library.LoadPackOneZero(code, year - 1); }
        catch (PyFileNotFoundError) { priorPack = null; }
        var lever = Lever(args, pack, state, "add_headcount", 5);
        var engine = new OneZeroSimulation(library);
        var results = new List<PyDict>();
        var declined = new List<PyDict>();
        foreach (var (client, all) in source.LoadPortfolioPayPeriods().OrderBy(pair => pair.Key))
        {
            var window = source.WindowForStateYear(client, code, year);
            var rows = Headcount.RowsForStateYear(EngineRows(all), state, year, window);
            if (rows.Count == 0)
            {
                continue;
            }

            var prior = priorPack is null ? 0 : Headcount.AverageHeadcount(EngineRows(all), state, year - 1, priorPack,
                source.WindowForStateYear(client, code, year - 1));
            try
            {
                var before = engine.OneZeroSnapshot(rows, year, code, pack, PyNumber.OfFloat(prior));
                var (moved, _) = OneZeroLever.Apply(rows, lever);
                var after = engine.OneZeroSnapshot(moved, year, code, pack, PyNumber.OfFloat(prior));
                results.Add(PortfolioProjection(client, prior, before, after));
            }
            catch (Exception e) when (e is PyValueError or PyOverflowError or ArithmeticException)
            {
                declined.Add(Dict(("client_id", client), ("reason", "The requested lever cannot be applied to this client's payroll.")));
            }
        }
        return PortfolioSimulationResult(args, year, state, code, lever, priorPack, results, declined);
    }

    private static PyDict PortfolioProjection(long client, double prior, PyDict before, PyDict after)
    {
        var qualifiedBefore = Num(before, "annual_credit_usd") > 0;
        var qualifiedAfter = Num(after, "annual_credit_usd") > 0;
        return Dict(("client_id", client), ("base_average_headcount", PyRound.Round(prior, 2)),
            ("average_headcount_before", before["average_headcount"]), ("average_headcount_after", after["average_headcount"]),
            ("annual_credit_before_usd", before["annual_credit_usd"]), ("annual_credit_after_usd", after["annual_credit_usd"]),
            ("annual_credit_delta_usd", Num(after, "annual_credit_usd") - Num(before, "annual_credit_usd")),
            ("qualified_before", qualifiedBefore), ("qualified_after", qualifiedAfter), ("crosses_threshold", !qualifiedBefore && qualifiedAfter));
    }

    private static PyDict PortfolioSimulationResult(ReadArguments args, long year, string state, string code, LeverRequest lever,
        OneZeroPack? priorPack, List<PyDict> results, List<PyDict> declined)
    {
        var crossings = results.Where(row => ReadValues.Bool(row["crosses_threshold"])).ToList();
        var note = "Every client is measured under the same statute for this state and tax year, against their own frozen prior-year base. Clients who cross the statutory threshold are listed first: going from no credit to a credit is a different result from an existing credit growing, and ranking on dollars alone hides the crossings behind established earners.";
        if (priorPack is null)
        {
            note += $" NOTE: {state} has no authored statute for {year - 1}, so there is no frozen base. Every client's entire workforce is treated as net-new and these figures are upper bounds, not projections.";
        }

        var limit = args.WholeNumber("limit", 50);
        if (limit < 0)
        {
            limit = Math.Max(0, results.Count + limit);
        }

        return Dict(("state", state), ("program_code", code), ("tax_year", year), ("action", lever.Action), ("magnitude", lever.Magnitude),
            ("has_frozen_base", priorPack is not null), ("clients_evaluated", results.Count), ("clients_crossing_threshold", crossings.Count),
            ("credit_unlocked_usd", PyRound.Round(crossings.Sum(row => Num(row, "annual_credit_delta_usd")), 2)),
            ("credit_delta_total_usd", PyRound.Round(results.Sum(row => Num(row, "annual_credit_delta_usd")), 2)),
            ("clients", results.OrderByDescending(row => ReadValues.Bool(row["crosses_threshold"]))
                .ThenByDescending(row => Num(row, "annual_credit_delta_usd")).Take(limit).ToList()),
            ("declined", declined), ("method_note", note));
    }
}
