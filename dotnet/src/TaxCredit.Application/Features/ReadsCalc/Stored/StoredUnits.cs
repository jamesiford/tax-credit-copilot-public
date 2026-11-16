using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Filters;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;
using static TaxCredit.Application.Features.ReadsCalc.ReadValues;

namespace TaxCredit.Application.Features.ReadsCalc.Stored;

/// <summary>The location grid and its two independent cohorts read accepted Gold only.</summary>
public sealed class StoredUnits(IGoldReadPort gold, RuleLibrary library, ProgramDefaults defaults,
    ClientRunResolver resolver, RestOfYearReading rest)
{
    private static readonly string[] LeverFields = ["additional_weekly_hours", "projected_weekly_hours", "exceeds_plausible_week", "failure_mode", "hourly_rate_to_qualify"];
    /// <summary>Returns the three stored grains, exact SQL totals and a current-run envelope.</summary>
    public object Page(ReadArguments args)
    {
        ArgumentNullException.ThrowIfNull(args);
        var client = args.Client("client_id")!.Value;
        var state = args.Text("state");
        var year = args.OptionalInt("year");
        var method = args.Method();
        var limit = args.WholeNumber("limit", 25);
        var offset = args.WholeNumber("offset");
        var program = args.Text("program_code") ?? (state is null ? null : defaults.ProgramCodeForState(state));
        using var scope = gold.Scope();
        var page = gold.UnitPage(client, method, year, program, limit, offset);
        var run = Child(page, "run");
        var output = Envelope(run, Child(page, "in_flight"));
        Add(output, ("client_id", client), ("state", state), ("year", year), ("method", method), ("limit", limit), ("offset", offset));
        foreach (var key in new[] { "items", "total", "months", "installments", "unit_totals" })
        {
            output[key] = page[key];
        }
        var items = Rows(page, "items");
        output["units"] = items.Select(row => Text(row["worksite_id"])).Distinct().Order(StringComparer.Ordinal).Select(SiteLabels.Dimension).ToArray();
        output["years"] = items.Select(row => Count(row["tax_year"])).Distinct().Order().ToArray();
        return output;
    }

    /// <summary>Narrows and sorts in the warehouse before paging, with honest unfiltered counts.</summary>
    public object Detail(ReadArguments args)
    {
        ArgumentNullException.ThrowIfNull(args);
        var client = args.Client("client_id")!.Value;
        var year = args.WholeNumber("year");
        var method = args.Method();
        var options = DrillOptions(args);
        using var scope = gold.Scope();
        var drill = gold.UnitDrill(client, args.Text("unit_id")!, year, method, options);
        var run = Child(drill, "run");
        var unit = Child(drill, "unit");
        var held = Bool(drill.GetValueOrDefault("year_held", unit is not null));
        var output = Envelope(run, Child(drill, "in_flight"), held);
        Add(output, ("client_id", client), ("state", args.Text("state")), ("year", year), ("method", method),
            ("month_filter", Map(("month_index", options.Month))), ("filters_applied", Applied(options.EmployeeFilters, false)),
            ("near_filters_applied", Applied(options.NearFilters, true)));
        if (run is null || !held)
        {
            Add(output, ("unit", null), ("employees", Array.Empty<object>()), ("near_threshold", Array.Empty<object>()),
                ("thresholds", Thresholds(null, year)), ("total", 0), ("total_unfiltered", 0), ("near_total_unfiltered", 0));
            return output;
        }
        if (unit is null)
        {
            throw new ReadRefusalException(404, "The unit is not in this client's live run.");
        }
        var near = Levers(Rows(drill, "near_threshold"), Text(run["program_code"]), year);
        if (near.Count > 0)
        {
            var statute = resolver.ResolveStatute(client, args.Text("state"), year);
            var checkpoint = new DateOnly(year, 8, 31);
            if (checkpoint < statute.Window.End)
            {
                rest.Attach(near, client, year, Text(run["run_id"]), statute, checkpoint);
            }
        }
        var employees = Rows(drill, "employees");
        Add(output, ("unit", unit), ("months", drill["months"]), ("employees", employees), ("near_threshold", near),
            ("thresholds", Thresholds(Text(run["program_code"]), year)), ("total", employees.Count),
            ("total_unfiltered", options.Limit is null ? drill.GetValueOrDefault("employees_total", employees.Count)
                : gold.UnitEmployees(client, args.Text("unit_id")!, year, method, Text(run["run_id"]), options.Month).Count),
            ("near_total_unfiltered", options.Limit is null ? drill.GetValueOrDefault("near_total", near.Count)
                : gold.UnitNearThreshold(client, args.Text("unit_id")!, year, method, Text(run["run_id"]))
                    .Count(row => options.NearMinHours is null || Number(row.GetValueOrDefault("avg_weekly_hours")) >= options.NearMinHours)));
        return output;
    }

    private List<Dictionary<string, object?>> Levers(List<IReadOnlyDictionary<string, object?>> rows, string program, int year)
    {
        var floors = library.ResolveStatutoryFloors(program, year);
        return rows.Select(row =>
        {
            var output = Copy(row);
            var input = Engine(row).Set("Employee_ID", row.GetValueOrDefault("employee_id"));
            var lever = Proximity.AssessEmployee(input, floors);
            foreach (var key in LeverFields)
            {
                output[key] = lever[key];
            }
            return output;
        }).ToList();
    }

    private Dictionary<string, object?> Thresholds(string? program, int year)
    {
        if (program is null)
        {
            return Map(("min_weekly_hours", null), ("min_weekly_wages", null), ("resolved", false));
        }
        var floors = library.ResolveStatutoryFloors(program, year);
        return Map(("min_weekly_hours", Number(floors.MinWeeklyHours)),
            ("min_weekly_wages", Number(floors.MinWeeklyWages)), ("resolved", true));
    }

    private static UnitDrillOptions DrillOptions(ReadArguments args)
    {
        var month = args.OptionalInt("month");
        var sort = args.Text("sort", "avg_weekly_hours")!;
        var order = args.Text("order", "desc")!.ToLowerInvariant();
        if (month is < 1 or > 12 || order is not ("asc" or "desc")
            || sort is not ("avg_weekly_hours" or "avg_weekly_wages" or "employee_id" or "weeks_worked" or "total_hours"))
        {
            throw new ReadRefusalException(422, "Invalid month or cohort ordering.");
        }
        return new UnitDrillOptions
        {
            Month = month,
            Sort = sort,
            Order = order,
            NearMinHours = args.OptionalNumber("near_min_hours"),
            Limit = args.OptionalInt("limit"),
            EmployeeFilters = args.Text("filter"),
            NearFilters = args.Text("near_filter")
        };
    }

    private static PyDict Applied(string? wire, bool near)
    {
        var columns = new Dictionary<string, FilterColumn>(StringComparer.Ordinal)
        {
            ["employee_id"] = new("employee_id", "text"),
            ["avg_weekly_hours"] = new("avg_weekly_hours", "numeric"),
            ["avg_weekly_wages"] = new("avg_weekly_wages", "numeric"),
            ["weeks_worked"] = new("weeks_worked", "numeric"),
            ["total_hours"] = new("total_hours", "numeric"),
        };
        if (!near)
        {
            columns["weight"] = new("weight", "numeric");
        }
        return GridFilter.Compile(wire, columns).Applied;
    }

    private static void Add(Dictionary<string, object?> output, params (string Key, object? Value)[] items)
    {
        foreach (var item in items)
        {
            output[item.Key] = item.Value;
        }
    }
}
