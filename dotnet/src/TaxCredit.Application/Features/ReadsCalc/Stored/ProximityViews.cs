using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Forecast;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;
using static TaxCredit.Application.Features.ReadsCalc.ReadValues;

namespace TaxCredit.Application.Features.ReadsCalc.Stored;

/// <summary>Reads stored verdicts and measuring months; only the newly requested projection computes.</summary>
public sealed class ProximityViews(IGoldReadPort gold, ClientRunResolver resolver, RestOfYearReading rest,
    RuleLibrary library, IClock clock)
{
    private static readonly string[] NearFields = ["band_weekly_hours", "within_band", "ineligible", "evaluated", "failure_modes", "cohort", "floors"];
    /// <summary>A bounded necessary-condition fetch retains whole-population counts.</summary>
    public object Cohort(ReadArguments args)
    {
        ArgumentNullException.ThrowIfNull(args);
        var client = args.Client();
        var year = args.WholeNumber("tax_year");
        var method = args.Method();
        var within = args.Number("within", 5);
        if (within < 0)
        {
            throw new ReadRefusalException(422, "within cannot be negative.");
        }
        var statute = resolver.ResolveStatute(client, args.Text("state"), year, args.Text("program_code"), true);
        if (client is null)
        {
            throw new ReadRefusalException(404, "Select a client to read the cohort from its accepted run.");
        }
        var population = gold.ProximityCandidates(client.Value, year, method, new RiskOptions(
            Number(statute.Floors.MinWeeklyHours), Number(statute.Floors.MinWeeklyWages),
            WidestBandHours: Math.Max(within, Proximity.BandCurveHours.Max()), ProgramCode: statute.ProgramCode));
        var output = Map(("state", statute.State), ("program_code", statute.ProgramCode), ("tax_year", year),
            ("method", method), ("account_id", client), ("run", population["run"]));
        var counts = Child(population, "counts");
        if (population["run"] is null || counts is null || Count(counts.GetValueOrDefault("evaluated")) == 0)
        {
            output["calculation_state"] = "not_calculated";
            output["cohort"] = Array.Empty<object>();
            output["bands"] = Array.Empty<object>();
            return output;
        }
        var averages = Rows(population, "rows").Select(Average).ToArray();
        var whole = new PyDict().Add("evaluated", (long)Count(counts["evaluated"]))
            .Add("eligible", (long)Count(counts["eligible_count"])).Add("ineligible", (long)Count(counts["ineligible_count"]))
            .Add("failure_modes", new PyDict().Add("hours_only", (long)Count(counts["hours_only"]))
                .Add("wages_only", (long)Count(counts["wages_only"])).Add("both", (long)Count(counts["both"])));
        var result = Proximity.NearMissCohort(averages, statute.Floors, PyNumber.OfFloat(within), args.WholeNumber("limit", 100), population: whole);
        foreach (var item in result)
        {
            output[item.Key] = item.Value;
        }
        output["calculation_state"] = "calculated";
        output["fiscal_window"] = Map(("begin", Iso(statute.Window.Begin)), ("end", Iso(statute.Window.End)));
        output["bands"] = Proximity.BandCurve(averages, statute.Floors);
        var disagreements = Count(result["verdict_disagreements"]);
        var hasBand = statute.Pack.PtBandHours is not null && statute.Pack.PtWeight is { } weight && Number(weight) != 0;
        output["statute_matches_run"] = Map(("matches", disagreements == 0 || hasBand), ("verdict_disagreements", disagreements),
            ("programme_has_part_time_band", hasBand), ("resolved_rule_pack_source", statute.Floors.AsDict()["source"]));
        if (args.Flag("rest_of_year"))
        {
            var checkpoint = args.Date("as_of", new DateOnly(year, 8, 31));
            var rows = ((IEnumerable<object?>)result["cohort"]!).Cast<PyDict>().Select(row => Copy(
                (IReadOnlyDictionary<string, object?>)Transport(row)!)).ToArray();
            if (rows.Length > 0)
            {
                output["rest_of_year_as_of"] = Iso(checkpoint);
                rest.Attach(rows, client.Value, year, Text(Child(population, "run")!["run_id"]), statute, checkpoint, method);
                output["cohort"] = rows;
            }
        }
        return output;
    }

    /// <summary>Projects from the recorded monthly denominator and includes the same actionable cohort.</summary>
    public object Progress(ReadArguments args)
    {
        ArgumentNullException.ThrowIfNull(args);
        var client = args.Client() ?? throw new ReadRefusalException(404, "Select a client to read its progress.");
        var year = args.WholeNumber("tax_year");
        var state = args.Text("state", "GA")!.ToUpperInvariant();
        var checkpoint = args.Date("as_of", new DateOnly(year, 8, 31));
        var current = gold.HeadcountSeries(client, year, "pay_period");
        var prior = gold.HeadcountSeries(client, year - 1, "pay_period");
        var months = Sequence(current, "months").Select(Number).ToArray();
        if (current["run"] is null || !months.Any(m => m != 0))
        {
            throw new ReadRefusalException(404, "No calculated run holds this client-state-year.");
        }
        var ends = Sequence(current, "month_ends").Select(value => DateOnly.ParseExact(Text(value)[..10], "yyyy-MM-dd",
            System.Globalization.CultureInfo.InvariantCulture)).ToArray();
        var elapsed = ends.Length == 0 ? 1 : Math.Clamp(ends.Count(day => day <= checkpoint), 1, ends.Length);
        var unreachable = Sequence(current, "unreachable_months").Select(Count).ToHashSet();
        var today = DateOnly.FromDateTime(clock.UtcNow.UtcDateTime);
        while (ends.Length > 0 && ends[^1] > today && elapsed > 1 && unreachable.Contains(elapsed - 1))
        {
            elapsed--;
        }
        var ytd = PyRound.Round(PySum.Sum(months.Take(elapsed).ToList()) / elapsed, 2);
        var hasPrior = Sequence(prior, "months").Any(value => Number(value) != 0);
        var average = hasPrior ? Number(prior["annual_average"]) : 0;
        var projection = new ForecastProjection(library).ProjectStateYearEnd(state, year, [], [], checkpoint,
            new ForecastOptions(MonthsElapsed: elapsed, YtdAverageHeadcount: ytd, PriorAverageHeadcount: average))
            ?? throw new ReadRefusalException(404, "No authored statute for this state-year.");
        var output = (Dictionary<string, object?>)Transport(projection)!;
        var meaningful = hasPrior && Number(output["prior_year_average_headcount"]) > 0;
        output["account_id"] = client;
        output["has_prior_year_payroll"] = hasPrior;
        output["base_is_meaningful"] = meaningful;
        output["base_caveat"] = meaningful ? null : $"No {state} payroll held for TY{year - 1}, so the base is zero and every employee counts as net-new. The net-new figure is an upper bound, not a position.";
        var cohort = (IReadOnlyDictionary<string, object?>)Cohort(new ReadArguments(new Dictionary<string, string?>(StringComparer.Ordinal)
        {
            ["account_id"] = Text(client),
            ["tax_year"] = Text(year),
            ["state"] = state,
            ["within"] = Text(args.Number("within", 5)),
            ["limit"] = "10",
            ["rest_of_year"] = "true",
            ["as_of"] = Iso(checkpoint),
        }));
        output["near_the_line"] = cohort.ContainsKey("band_weekly_hours")
            ? NearFields
                .ToDictionary(key => key, key => cohort[key], StringComparer.Ordinal) : null;
        output["is_estimate"] = true;
        output["denominator_note"] = $"Average headcount over {elapsed} closed month(s), not 12. Projected to year end at the current run-rate with no seasonality applied.";
        return output;
    }

    private static PyDict Average(IReadOnlyDictionary<string, object?> row)
    {
        var output = new PyDict().Add("Employee_ID", row["employee_id"]).Add("record_token", row["record_token"]);
        foreach (var key in new[] { "weeks_worked", "total_hours", "total_wages", "avg_weekly_hours", "avg_weekly_wages" })
        {
            output.Add(key, Number(row[key]));
        }
        return output.Add("eligible", Bool(row["eligible"]));
    }

    private static IEnumerable<object?> Sequence(IReadOnlyDictionary<string, object?> source, string key) =>
        source.GetValueOrDefault(key) is System.Collections.IEnumerable rows ? rows.Cast<object?>() : [];
}
