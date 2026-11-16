using System.Globalization;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ReadsCalc.Calculations;

public sealed partial class ReadsCalculationViews
{
    private PyDict Employee(ReadArguments args)
    {
        var year = Year(args);
        var state = args.Text("state", "GA")!.ToUpperInvariant();
        var employee = args.Text("employee_id") ?? throw new ReadRefusalException(422, "employee_id is required.");
        var pack = library.LoadPackOneZero(state, year) ?? throw new ReadRefusalException(404, "No rule pack for that state.");
        (pack, _, _) = Negotiated(state, pack);
        var rows = FiscalRows(Rows(args, true), year).Where(r => (r.Get("Worksite_ID") as string)?.StartsWith(state + "_", StringComparison.Ordinal) == true).ToList();
        var result = Run(rows, year, pack);
        var totals = result.TotalHoursAndWages.FirstOrDefault(e => e.EmployeeId == employee);
        var average = result.AllAverages.FirstOrDefault(e => e.EmployeeId == employee);
        if (totals is null && average is null)
        {
            throw new ReadRefusalException(404, "No pay-period rows for that employee in scope.");
        }

        var lines = rows.Where(r => Equals(r.Get("Employee_ID"), employee)).OrderBy(r => r.Get("Pay_Period_End") as string, StringComparer.Ordinal)
            .Select(r => Select(r.Dict, "Worksite_ID", "Entity_FEIN", "Pay_Period_Start", "Pay_Period_End", "Pay_Date", "Hours_Worked", "Gross_Wages", "Pay_Code")
                .Set("Pay_Code", r.Get("Pay_Code") ?? "Regular").Set("Worksite_Name", SiteName(r.Get("Worksite_ID") as string))).ToList();
        var months = EmployeeMonths(result, employee);
        var verdict = average is null ? ((double Weight, bool PassedHours, bool PassedWages)?)null
            : OneZeroEligibility.Classify(average.AvgWeeklyHours, average.AvgWeeklyWages, pack);
        return Dict(("employee_id", employee), ("tax_year", year), ("source_lines", lines), ("source_line_count", lines.Count),
            ("totals", Dict(("total_hours", totals?.TotalHours ?? 0), ("total_wages", totals?.TotalWages ?? 0))),
            ("weeks_worked", average?.WeeksWorked ?? 0), ("avg_weekly_hours", average?.AvgWeeklyHours), ("avg_weekly_wages", average?.AvgWeeklyWages),
            ("floor_test", Dict(("min_weekly_hours", pack.MinWeeklyHours), ("min_weekly_wages", pack.MinWeeklyWages),
                ("wage_test_applies", ReadValues.Number(pack.MinWeeklyWages) > 0),
                ("passed_hours", verdict?.PassedHours), ("passed_wages", verdict?.PassedWages), ("weight", verdict?.Weight ?? 0))),
            ("eligible", result.EligibleEmployees.Any(e => e.EmployeeId == employee)), ("months", months),
            ("months_counted", months.Count(m => Num(m, "counted") != 0)), ("headcount_contribution", PyRound.Round(months.Sum(m => Num(m, "counted")) / 12, 4)),
            ("citation", pack.Citation), ("state", state), ("review", ReadReview(employee)));
    }

    private static List<PyDict> EmployeeMonths(OneZeroResult result, string employee) =>
        result.Months.Select((month, index) =>
        {
            var allocation = result.EmployeeUnitMatrix.FirstOrDefault(r => r.EmployeeId == employee && index < r.Months.Length && ReadValues.Number(r.Months[index]) != 0);
            var row = Dict(("month_end", month.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)),
                ("counted", allocation is null ? 0.0 : ReadValues.Number(allocation.Months[index])), ("worksite_id", allocation?.WorksiteId));
            if (allocation?.WorksiteId is { } site)
            {
                row.Set("worksite_name", SiteName(site));
            }

            return row;
        }).ToList();

    private PyDict ReviewEmployee(ReadArguments args)
    {
        var employee = args.Text("employee_id") ?? throw new ReadRefusalException(422, "employee_id is required.");
        var status = args.Text("status", "validated");
        if (status is not ("validated" or "flagged" or "cleared"))
        {
            throw new ReadRefusalException(422, "Invalid review status.");
        }

        var actor = args.Text("reviewer", "Reviewer")!;
        if (status == "cleared")
        {
            lookups.Remove("employee_reviews", 0, "employee_id", employee, actor, configuration.UtcNow());
            return Dict(("ok", true), ("review", null));
        }
        var entry = Dict(("employee_id", employee), ("status", status), ("note", args.Text("note")),
            ("reviewer", actor), ("reviewed_at", Today));
        lookups.Put(new LookupEntry("employee_reviews", 0, "employee_id", employee, PyJson.Dumps(entry), actor), configuration.UtcNow());
        return Dict(("ok", true), ("review", entry));
    }

    private PyDict? ReadReview(string employee)
    {
        var row = lookups.Entries("employee_reviews", 0).LastOrDefault(e => e.KeyKind == "employee_id" && e.Key == employee);
        return row is null ? null : (PyDict)PyJson.Loads(row.ValueJson)!;
    }

    private static string? SiteName(string? site) => site is null ? null : SiteLabels.Name(site);
}
