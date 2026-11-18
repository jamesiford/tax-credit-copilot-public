using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Infrastructure.Persistence.GoldRead;

public sealed partial class GoldReader
{
    private const string RiskColumns = "employee_id, record_token, weeks_worked, total_hours, total_wages, avg_weekly_hours, avg_weekly_wages, weight";
    private const string RiskWhere = " FROM {gold.employee_eligibility} WHERE {tenant} AND tax_year = ? AND method = ? AND run_id = ? AND avg_weekly_hours IS NOT NULL";

    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?> AtRisk(long clientId, int taxYear, string method, RiskOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        var run = LatestRun(clientId, options.ProgramCode);
        if (run is null)
        {
            return EmptyRisk();
        }
        object?[] values = [taxYear, method, run["run_id"]];
        var counts = One(clientId, "SELECT COUNT(*) AS evaluated, SUM(CASE WHEN eligible = 1 THEN 1 ELSE 0 END) AS eligible_count" + RiskWhere, values);
        var rows = Many(clientId, "SELECT " + RiskColumns + RiskWhere +
            " AND eligible = 1 AND (avg_weekly_hours < ? OR avg_weekly_wages < ?) ORDER BY avg_weekly_hours",
            [.. values, options.MinWeeklyHours * (1 + options.Band), options.MinWeeklyWages * (1 + options.Band)]);
        return new Dictionary<string, object?> { ["run"] = run, ["rows"] = rows, ["counts"] = counts };
    }

    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?> ProximityCandidates(long clientId, int taxYear, string method, RiskOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        var run = LatestRun(clientId, options.ProgramCode);
        if (run is null)
        {
            return EmptyRisk();
        }
        object?[] values = [taxYear, method, run["run_id"]];
        var counts = One(clientId, "SELECT COUNT(*) AS evaluated, " +
            "SUM(CASE WHEN eligible = 1 THEN 1 ELSE 0 END) AS eligible_count, " +
            "SUM(CASE WHEN eligible = 0 THEN 1 ELSE 0 END) AS ineligible_count, " +
            "SUM(CASE WHEN eligible = 0 AND avg_weekly_hours < ? AND avg_weekly_wages >= ? THEN 1 ELSE 0 END) AS hours_only, " +
            "SUM(CASE WHEN eligible = 0 AND avg_weekly_hours >= ? AND avg_weekly_wages < ? THEN 1 ELSE 0 END) AS wages_only, " +
            "SUM(CASE WHEN eligible = 0 AND avg_weekly_hours < ? AND avg_weekly_wages < ? THEN 1 ELSE 0 END) AS both" + RiskWhere,
            [options.MinWeeklyHours, options.MinWeeklyWages, options.MinWeeklyHours, options.MinWeeklyWages,
                options.MinWeeklyHours, options.MinWeeklyWages, .. values]);
        var rows = Many(clientId, "SELECT " + RiskColumns + ", eligible" + RiskWhere + " AND avg_weekly_hours >= ?",
            [.. values, options.MinWeeklyHours - options.WidestBandHours]);
        return new Dictionary<string, object?> { ["run"] = run, ["rows"] = rows, ["counts"] = counts };
    }

    private static Dictionary<string, object?> EmptyRisk() =>
        new() { ["run"] = null, ["rows"] = GoldValues.EmptyRows, ["counts"] = null };

    /// <inheritdoc />
    public IReadOnlyDictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object?>>> CohortPeriods(long clientId, int taxYear, string runId, IReadOnlyList<string> tokens)
    {
        ArgumentNullException.ThrowIfNull(tokens);
        var wanted = tokens.Where(t => !string.IsNullOrEmpty(t)).Distinct(StringComparer.Ordinal).ToArray();
        var grouped = new Dictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object?>>>(StringComparer.Ordinal);
        // Stay below SQL Server's 2100-parameter bound without changing token-group order.
        foreach (var chunk in wanted.Chunk(1000))
        {
            var marks = string.Join(", ", chunk.Select(_ => "?"));
            var rows = Many(clientId, "SELECT record_token, worksite_id, pay_period_start, pay_period_end, pay_date, hours, wages " +
                "FROM {gold.employee_period_fact} WHERE {tenant} AND tax_year = ? AND run_id = ? " +
                $"AND record_token IN ({marks}) ORDER BY record_token, pay_period_end", [taxYear, runId, .. chunk]);
            foreach (var group in rows.GroupBy(r => GoldValues.Text(r, "record_token")))
            {
                grouped[group.Key] = group.ToArray();
            }
        }
        return grouped;
    }
}
