using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Infrastructure.Persistence.GoldRead;

public sealed partial class GoldReader
{
    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?> EligibilityPopulation(long clientId, int taxYear, double minWeeklyHours,
        double minWeeklyWages, EligibilityOptions? options = null)
    {
        options ??= new EligibilityOptions();
        using var scope = Scope();
        var run = LatestRun(clientId, options.ProgramCode);
        var result = new Dictionary<string, object?> { ["run"] = run, ["summary"] = null, ["rows"] = GoldValues.EmptyRows, ["matching"] = 0 };
        if (run is null)
        {
            return result;
        }
        object?[] values = [taxYear, run["run_id"], .. NearParameters(minWeeklyHours, minWeeklyWages, options.Band)];
        var summary = EligibilitySummary(clientId, values, minWeeklyHours, minWeeklyWages)!;
        if (GoldValues.Int(summary, "employees_evaluated") == 0)
        {
            return result;
        }
        var filter = EligibilityFilter(options);
        var allowed = new[] { "employee_id", "status", "near_floor", "total_hours", "total_wages", "mm_weeks", "mm_hours", "pp_weeks", "pp_hours" };
        var sort = allowed.Contains(options.Sort, StringComparer.Ordinal) ? options.Sort : "employee_id";
        var direction = string.Equals(options.Order, "desc", StringComparison.OrdinalIgnoreCase) ? "DESC" : "ASC";
        var order = $" ORDER BY {sort} {direction}" + (sort == "employee_id" ? "" : ", employee_id ASC");
        result["summary"] = summary;
        result["rows"] = Many(clientId, Page(Classified() + "SELECT * FROM classified" + filter.Sql + order, options.Limit, options.Offset),
            [.. values, .. filter.Values]);
        result["matching"] = GoldValues.Int(One(clientId, Classified() + "SELECT COUNT(*) AS count_rows FROM classified" + filter.Sql,
            [.. values, .. filter.Values])!, "count_rows");
        return result;
    }

    private IReadOnlyDictionary<string, object?>? EligibilitySummary(long clientId, object?[] values, double hours, double wages) =>
        One(clientId, Classified(true) + "SELECT COUNT(*) AS employees_evaluated, " +
            "SUM(CASE WHEN mm_eligible = 1 THEN 1 ELSE 0 END) AS min_max_eligible, " +
            "SUM(CASE WHEN pp_eligible = 1 THEN 1 ELSE 0 END) AS pay_period_eligible, " +
            "SUM(CASE WHEN mm_eligible = 1 OR pp_eligible = 1 THEN 1 ELSE 0 END) AS eligible_either, SUM(near_floor) AS near_floor, " +
            "SUM(CASE WHEN status = 'both' THEN 1 ELSE 0 END) AS eligible_both, " +
            "SUM(CASE WHEN status = 'min_max_only' THEN 1 ELSE 0 END) AS min_max_only, " +
            "SUM(CASE WHEN status = 'pay_period_only' THEN 1 ELSE 0 END) AS pay_period_only, " +
            "SUM(CASE WHEN status = 'neither' THEN 1 ELSE 0 END) AS neither, SUM(verdict_drift) AS verdict_disagreements FROM classified",
            [.. values, hours, wages, hours, wages]);
}
