using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using static TaxCredit.Application.Features.ReadsCalc.ReadValues;

namespace TaxCredit.Application.Features.ReadsCalc.Stored;

/// <summary>Opaque handles resolve against a tenant's stored run, never against a reminted global population.</summary>
public sealed class StoredEmployees(IGoldReadPort gold, ReadStatutes resolver, RestOfYearReading rest,
    IRuntimeConfiguration configuration)
{
    /// <summary>The compact v2 employee reading preserves both recorded verdicts and the selected unit method.</summary>
    public object Detail(ReadArguments args)
    {
        ArgumentNullException.ThrowIfNull(args);
        var client = args.Client("client_id") ?? throw new ReadRefusalException(422, "client_id is required.");
        var year = args.OptionalInt("year") ?? throw new ReadRefusalException(422, "year is required.");
        var token = args.Text("record_token")!;
        using var scope = gold.Scope();
        var run = gold.LatestRun(client);
        var output = Envelope(run, gold.RunInFlight(client));
        output["client_id"] = client;
        output["state"] = args.Text("state");
        output["tax_year"] = year;
        output["record_token"] = token;
        if (run is null)
        {
            output["eligibility"] = Array.Empty<object>();
            output["units"] = Array.Empty<object>();
            return output;
        }
        var verdicts = gold.Employee(token, client, year, Text(run["run_id"]));
        if (verdicts.Count == 0)
        {
            throw new ReadRefusalException(404, "The handle is not in this client's live run.");
        }
        output["employee_id"] = verdicts[0]["employee_id"];
        output["eligibility"] = verdicts;
        output["units"] = gold.EmployeeUnits(token, client, year, Text(run["run_id"]), args.Text("method", "min_max")!);
        return output;
    }

    /// <summary>The employee walk explicitly names evidence the accepted Gold rows cannot provide.</summary>
    public object Drill(ReadArguments args)
    {
        ArgumentNullException.ThrowIfNull(args);
        var client = args.Client() ?? throw new ReadRefusalException(404, "A client is required to resolve the handle.");
        var year = args.WholeNumber("tax_year");
        var token = args.Text("record_token")!;
        var statute = resolver.ResolveStatute(client, args.Text("state"), year, args.Text("program_code"), true);
        var read = gold.EmployeeDrill(client, year, token, statute.ProgramCode);
        var verdicts = Rows(read, "verdicts");
        if (read["run"] is null || verdicts.Count == 0)
        {
            throw new ReadRefusalException(404, "No employee in this client-program-year matches the handle.");
        }
        var mm = verdicts.LastOrDefault(row => Text(row["method"]) == "min_max");
        var pp = verdicts.LastOrDefault(row => Text(row["method"]) == "pay_period");
        var totals = mm ?? pp!;
        var periods = Rows(read, "periods");
        var months = read.GetValueOrDefault("month_ends") ?? Array.Empty<object>();
        var checkpoint = new DateOnly(year, 8, 31);
        var restReading = periods.Count > 0 && checkpoint < statute.Window.End
            ? (object)Proximity.RestOfYear(periods.Select(Engine).ToArray(), statute.Floors, checkpoint, statute.Window.End)
            : Map(("state", "closed"), ("note", "The year is closed."));
        double? delta = mm is not null && pp is not null ? PyRound.Round(Number(pp["weeks_worked"]) - Number(mm["weeks_worked"]), 2) : null;
        return Map(("basis", "per_client"), ("record_token", token), ("employee_id", Text(verdicts[0]["employee_id"])),
            ("account_id", client), ("state", statute.State), ("program_code", statute.ProgramCode), ("tax_year", year),
            ("run", Map(("program_code", statute.ProgramCode), ("tax_year", year), ("fiscal_begin", Iso(statute.Window.Begin)),
                ("fiscal_end", Iso(statute.Window.End)), ("data_source", configuration.Get("DATA_SOURCE") ?? "csv"),
                ("months", months), ("run_id", Child(read, "run")!["run_id"]))),
            ("thresholds", Map(("minimum_average_weekly_hours", PythonString(statute.Floors.MinWeeklyHours)),
                ("minimum_average_weekly_wages_usd", PythonString(statute.Floors.MinWeeklyWages)))),
            ("raw_source_rows", periods.Select(SourceRow).ToArray()), ("rest_of_year", restReading), ("where", rest.Where(periods, client, year)),
            ("step1", Map(("totals", Map(("total_hours", StringNumber(totals.GetValueOrDefault("total_hours"))),
                    ("total_wages", StringNumber(totals.GetValueOrDefault("total_wages"))))),
                ("min_max", Verdict(mm, statute.Floors)), ("pay_period", Verdict(pp, statute.Floors)),
                ("denominator_invariant", Map(("pay_period_minus_min_max_weeks", delta), ("pay_period_gt_min_max", delta > 0),
                    ("over_review_tolerance", delta is { } difference && Math.Abs(difference) > 1.5),
                    ("pay_period_over_52_weeks", pp is not null && Number(pp["weeks_worked"]) > 52))))),
            ("onezero", Map(("months", months), ("min_max", Segments(Rows(read, "segments"), "min_max")),
                ("pay_period", Segments(Rows(read, "segments"), "pay_period")), ("overlap_flags", Array.Empty<object>()))),
            ("exceptions", Map(("step1", Array.Empty<object>()), ("onezero", Array.Empty<object>()))), ("not_available", Unavailable));
    }

    private static Dictionary<string, object?>? Verdict(IReadOnlyDictionary<string, object?>? row, StatutoryFloors floors)
    {
        if (row is null)
        {
            return null;
        }
        var hours = Number(row["avg_weekly_hours"]);
        var wages = Number(row["avg_weekly_wages"]);
        var weeks = Number(row["weeks_worked"]);
        var passedHours = hours >= Number(floors.MinWeeklyHours);
        var passedWages = wages >= Number(floors.MinWeeklyWages);
        return Map(("denominator_weeks", weeks), ("avg_weekly_hours", hours), ("avg_weekly_wages", wages),
            ("rounded_avg_weekly_hours", hours), ("rounded_avg_weekly_wages", wages), ("passed_hours", passedHours),
            ("passed_wages", passedWages), ("eligible", passedHours && passedWages),
            ("denominator_detail", Map(("weeks_worked", weeks), ("total_hours", Number(row.GetValueOrDefault("total_hours"))),
                ("total_wages", Number(row.GetValueOrDefault("total_wages"))))));
    }

    private static object SourceRow(IReadOnlyDictionary<string, object?> row, int index) =>
        Map(("source_file", ""), ("source_row", index), ("job_title", row.GetValueOrDefault("job_title") ?? ""),
            ("unit_id", row.GetValueOrDefault("worksite_id") ?? ""), ("fein", row.GetValueOrDefault("entity_fein") ?? ""),
            ("pay_period_start", Text(row.GetValueOrDefault("pay_period_start"))), ("pay_period_end", Text(row.GetValueOrDefault("pay_period_end"))),
            ("pay_date", Text(row.GetValueOrDefault("pay_date"))), ("pay_frequency_code", Text(row.GetValueOrDefault("pay_frequency_code"))),
            ("hours", StringNumber(row.GetValueOrDefault("hours"))), ("wages", StringNumber(row.GetValueOrDefault("wages"))),
            ("selection_decision", "included"));

    private static object[] Segments(List<IReadOnlyDictionary<string, object?>> rows, string method) =>
        rows.Select((row, index) => (row, index)).Where(item => Text(item.row.GetValueOrDefault("method")) == method)
            .Select(item => (object)Map(("segment_id", $"{item.row.GetValueOrDefault("worksite_id")}-{item.row.GetValueOrDefault("first_pps")}-{item.index}"),
                ("unit_id", item.row.GetValueOrDefault("worksite_id")), ("fein", item.row.GetValueOrDefault("entity_fein") ?? ""),
                ("period_start", Text(item.row.GetValueOrDefault("first_pps"))), ("period_end", Text(item.row.GetValueOrDefault("last_ppe"))),
                ("source_refs", Array.Empty<object>()), ("months", StoredMatrix.Months(item.row)), ("raw_months", StoredMatrix.Months(item.row)))).ToArray();

    private static string StringNumber(object? value) => value is null || Number(value) == 0 ? "0" : PythonString(value);

    private static readonly string[] Unavailable =
    [
        "Access reconciliation — there is one partner comparison and it is for the certified reference client.",
        "Source file and row lineage — lakehouse payroll has no such coordinate.",
        "Assumption-set and calculation hashes — those identify the certified artifact, and minting new ones here would prove nothing.",
        "Per-employee contested months — the matrix is deduped before it is stored, so the contest leaves no trace in the rows it produced.",
        "Pay periods the fiscal window EXCLUDED — the run writes only the rows it consumed, so a paycheck that fell outside the window is not held here.",
    ];
}
