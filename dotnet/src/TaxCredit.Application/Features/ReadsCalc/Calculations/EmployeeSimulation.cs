using System.Globalization;
using System.Text.Json;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Application.Features.ReadsCalc.Calculations;

public sealed partial class ReadsCalculationViews
{
    private sealed record EmployeeChange(string Token, double Hours, double Raise);
    private sealed record EmployeeScenario(long Client, long Year, string State, string Method, DateOnly Checkpoint, ClientRun Run,
        IReadOnlyList<EmployeeChange> Changes, Dictionary<string, string> Tokens, Dictionary<string, PyDict> Applied,
        OneZeroResult Before, OneZeroResult After, IReadOnlyList<IReadOnlyDictionary<string, object?>> Grid);

    private PyDict SimulateEmployee(ReadArguments args)
    {
        var client = args.Client("client_id") ?? throw new ReadRefusalException(422, "client_id is required.");
        var year = Year(args);
        var method = args.Method();
        var changes = EmployeeChanges(args.Body);
        var state = defaults.RunState(client, year, args.Text("state", "GA"), args.Text("program_code"));
        var run = resolver.ResolveClientRun(client, state, year, programCode: args.Text("program_code"), requireProgram: true);
        var checkpoint = args.Date("as_of", new DateOnly((int)year, 8, 31));
        if (checkpoint >= run.Window.End)
        {
            throw new ReadRefusalException(404, "The year is closed — once it is, it is written in stone.");
        }

        var wanted = changes.Select(change => change.Token).ToHashSet(StringComparer.Ordinal);
        var tokens = run.Rows.Select(row => (string)row.Get("Employee_ID")!).Distinct(StringComparer.Ordinal)
            .Select(employee => (Employee: employee, Token: RecordTokens.RecordToken(client, run.ProgramCode, year, employee)))
            .Where(item => wanted.Contains(item.Token)).ToDictionary(item => item.Token, item => item.Employee, StringComparer.Ordinal);
        if (tokens.Count != wanted.Count)
        {
            throw new ReadRefusalException(404, "Some stacked records match no employee in this client-year.");
        }

        var moved = run.Rows;
        var applied = new Dictionary<string, PyDict>(StringComparer.Ordinal);
        foreach (var change in changes)
        {
            var (rows, detail) = EmployeeRestOfYear.Apply(moved, tokens[change.Token], checkpoint, change.Hours, run.Window.End, change.Raise);
            moved = rows;
            applied[change.Token] = detail;
        }
        var before = RunClient(run, EngineRows(run.Rows), method);
        var after = RunClient(run, EngineRows(moved), method);
        using var scope = gold.Scope();
        var grid = gold.UnitYears(client, method, limit: 5000).Items;
        return EmployeeSimulationResult(new EmployeeScenario(client, year, state, method, checkpoint, run, changes, tokens, applied, before, after, grid));
    }

    private static List<EmployeeChange> EmployeeChanges(JsonElement? body)
    {
        if (body is not { } json || !json.TryGetProperty("employees", out var employees) || employees.ValueKind != JsonValueKind.Array)
        {
            throw new ReadRefusalException(422, "An employee stack is required.");
        }

        var changes = employees.EnumerateArray().Select(value =>
        {
            var args = new ReadArguments(new Dictionary<string, string?>(), value);
            return new EmployeeChange(args.Text("record_token") ?? "", args.Number("additional_weekly_hours"), args.Number("hourly_raise"));
        }).ToList();
        if (changes.Count is < 1 or > 25)
        {
            throw new ReadRefusalException(422, "Between one and 25 employees may be stacked.");
        }

        if (changes.Any(change => change.Token.Length is < 1 or > 64 || change.Hours is < 0 or > 40 || change.Raise is < 0 or > 100))
        {
            throw new ReadRefusalException(422, "An employee change is outside the permitted range.");
        }

        if (changes.Select(change => change.Token).Distinct(StringComparer.Ordinal).Count() != changes.Count)
        {
            throw new ReadRefusalException(422, "An employee appears twice in the stack.");
        }

        return changes;
    }

    private static Dictionary<string, Dictionary<string, double>> HoursAt(EmployeeScenario scenario)
    {
        var stacked = scenario.Tokens.Values.ToHashSet(StringComparer.Ordinal);
        var result = new Dictionary<string, Dictionary<string, double>>(StringComparer.Ordinal);
        foreach (var row in scenario.Run.Rows)
        {
            var employee = (string)row.Get("Employee_ID")!;
            if (!stacked.Contains(employee))
            {
                continue;
            }

            if (!result.TryGetValue(employee, out var sites))
            {
                result[employee] = sites = new Dictionary<string, double>(StringComparer.Ordinal);
            }

            var site = (string)row.Get("Worksite_ID")!;
            sites[site] = sites.GetValueOrDefault(site) + ReadValues.Number(row.Get("Hours_Worked"));
        }
        return result;
    }

    private static PyDict EmployeeSimulationResult(EmployeeScenario scenario)
    {
        var hoursAt = HoursAt(scenario);
        var gridRows = new Dictionary<string, PyDict?>(StringComparer.Ordinal);
        var locations = EmployeeLocations(scenario, hoursAt, gridRows);
        var employees = scenario.Changes.Select(change =>
        {
            var employee = scenario.Tokens[change.Token];
            var sites = hoursAt.GetValueOrDefault(employee) ?? [];
            var primary = sites.Count == 0 ? null : sites.MaxBy(pair => pair.Value).Key;
            return SelectDesignation(primary is null ? null : gridRows.GetValueOrDefault(primary))
                .Set("record_token", change.Token).Set("employee_id", employee).Set("worksite_id", primary).Set("worksites", sites.Keys.Order(StringComparer.Ordinal).ToList())
                .Set("additional_weekly_hours", change.Hours).Set("hourly_raise", change.Raise).Set("applied", scenario.Applied[change.Token])
                .Set("before", Verdict(scenario.Before, employee)).Set("after", Verdict(scenario.After, employee));
        }).ToList();
        return EmployeeSimulationEnvelope(scenario, locations, employees);
    }

    private static List<PyDict> EmployeeLocations(EmployeeScenario scenario, Dictionary<string, Dictionary<string, double>> hoursAt,
        Dictionary<string, PyDict?> gridRows)
    {
        var locations = new List<PyDict>();
        foreach (var site in hoursAt.Values.SelectMany(sites => sites.Keys).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal))
        {
            var series = LocationSeries(scenario.Grid, site);
            var grid = series.GetValueOrDefault(scenario.Year);
            gridRows[site] = grid;
            if (grid is null || BaseYear(series) == scenario.Year)
            {
                continue;
            }

            var baseYear = BaseYear(series);
            var closed = OpenMonths(grid);
            var before = UnitReading(scenario.Before, site, closed);
            var after = UnitReading(scenario.After, site, closed);
            if (before is null || Math.Abs(Num(before, "average_headcount") - Num(grid, "average_headcount")) > 0.011)
            {
                throw new ReadRefusalException(404, "Payroll no longer reproduces the run that wrote the grid. Re-run the calculation before projecting.");
            }

            var was = PriceLocation(series, scenario.State, scenario.Year, baseYear);
            var now = PriceLocation(series, scenario.State, scenario.Year, baseYear, after is null ? 0 : Num(after, "average_headcount"));
            PyDict? runRate = null;
            if (closed is not null)
            {
                var rateBefore = RunRate(series, scenario.State, scenario.Year, baseYear);
                var rateAfter = RunRate(series, scenario.State, scenario.Year, baseYear, Num(now.Reading, "average_headcount"));
                runRate = Dict(("before_usd", rateBefore), ("after_usd", rateAfter), ("delta_usd", rateAfter - rateBefore));
            }
            locations.Add(SelectDesignation(grid).Set("worksite_id", site).Set("base_year", baseYear).Set("in_progress", closed is not null)
                .Set("threshold", was.Reading["threshold"]).Set("employees", hoursAt.Where(pair => pair.Value.ContainsKey(site)).Select(pair => pair.Key).Order(StringComparer.Ordinal).ToList())
                .Set("before", EmployeeLocationReading(was.Reading)).Set("after", EmployeeLocationReading(now.Reading)).Set("run_rate", runRate));
        }
        return locations;
    }

    private static PyDict SelectDesignation(PyDict? grid) => Dict(("designation", grid is null ? null : Text(grid, "designation")),
        ("tier", grid is not null && grid.TryGetValue("tier", out var tier) ? tier : null),
        ("tier_source", grid is null ? "unassigned" : Text(grid, "tier_source") ?? (Text(grid, "designation") is null ? "unassigned" : "prototype")));

    private static PyDict Verdict(OneZeroResult result, string employee)
    {
        var average = result.AllAverages.FirstOrDefault(row => row.EmployeeId == employee);
        return Dict(("eligible", result.EligibleEmployees.Any(row => row.EmployeeId == employee)),
            ("avg_weekly_hours", average is null ? null : PyRound.Round(average.AvgWeeklyHours, 2)),
            ("avg_weekly_wages", average is null ? null : PyRound.Round(average.AvgWeeklyWages, 2)));
    }

    private static PyDict EmployeeLocationReading(PyDict reading) =>
        Dict(("average_headcount", PyRound.Round(Num(reading, "average_headcount"), 2)),
            ("net_new_vs_base", PyRound.Round(Num(reading, "net_new"), 2)), ("jobs_margin", SignedMargin(reading)),
            ("qualified", reading["qualified"]), ("annual_credit_usd", PyRound.RoundToInteger(Num(reading, "annual_credit_usd"))));

    private static PyDict EmployeeSimulationEnvelope(EmployeeScenario s, List<PyDict> locations, List<PyDict> employees)
    {
        var before = PyRound.RoundToInteger(s.Grid.Where(row => ReadValues.Number(row["tax_year"]) == s.Year).Sum(row => ReadValues.Number(row.GetValueOrDefault("annual_credit_usd"))));
        var delta = locations.Sum(row => Num((PyDict)row["after"]!, "annual_credit_usd") - Num((PyDict)row["before"]!, "annual_credit_usd"));
        var openLocations = locations.Where(row => row["run_rate"] is not null).ToList();
        var projected = s.Applied.Values.Sum(row => Num(row, "periods_projected"));
        return Dict(("scope", Dict(("client_id", s.Client), ("state", s.State), ("tax_year", s.Year), ("method", s.Method), ("as_of", s.Checkpoint.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)))),
            ("employees", employees), ("locations", locations),
            ("summary", Dict(("employees", employees.Count), ("became_eligible", employees.Count(row => !ReadValues.Bool(((PyDict)row["before"]!)["eligible"]) && ReadValues.Bool(((PyDict)row["after"]!)["eligible"]))),
                ("lost_eligibility", employees.Count(row => ReadValues.Bool(((PyDict)row["before"]!)["eligible"]) && !ReadValues.Bool(((PyDict)row["after"]!)["eligible"]))),
                ("locations_moved", locations.Count(row => !Equals(((PyDict)row["after"]!)["qualified"], ((PyDict)row["before"]!)["qualified"]))))),
            ("client", Dict(("annual_credit_usd_before", before), ("annual_credit_usd_after", (double)before + delta), ("annual_credit_usd_delta", delta),
                ("run_rate", EmployeeRunRate(s.Year, openLocations)))),
            ("eligibility_floors", Select(Floors(s.Run.Pack, s.Year), "min_weekly_hours", "min_weekly_wages")),
            ("method_note", EmployeeMethodNote(s, employees.Count, projected > 0)));
    }

    private static PyDict? EmployeeRunRate(long year, List<PyDict> locations) => locations.Count == 0 ? null :
        Dict(("basis", "run_rate"), ("delta_usd", locations.Sum(row => Num((PyDict)row["run_rate"]!, "delta_usd"))),
            ("before_usd", locations.Sum(row => Num((PyDict)row["run_rate"]!, "before_usd"))),
            ("after_usd", locations.Sum(row => Num((PyDict)row["run_rate"]!, "after_usd"))), ("locations", locations.Count),
            ("note", $"Run-rate estimate: each location's TY{year} priced as if the year closed at its pace over the closed months, against its own base. Nothing is claimable until the year closes."));

    private static string EmployeeMethodNote(EmployeeScenario s, int count, bool projected)
    {
        var checkpoint = s.Checkpoint.ToString("dd MMM", CultureInfo.InvariantCulture);
        var note = $"From {checkpoint} to the end of the fiscal year each stacked employee works their pace to date plus the extra hours, at their own rate plus the raise; periods already closed are left as paid. All {count} changes are applied together and the certified engine re-decides everyone once, so two people who could not move a location alone are seen moving it together. Each location is priced against its own base year, as the grid prices it.";
        return projected ? note + $" TY{s.Year} is still open: the periods after {checkpoint} are projected on each employee's own cadence, and each location is read on its closed months. The credit gained is a run-rate estimate: each location priced as if the year closed at that pace." : note;
    }
}
