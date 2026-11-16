using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Infrastructure.Persistence.GoldRead;

public sealed partial class GoldReader
{
    private const string EligibilityStatus = "CASE WHEN mm_eligible = 1 AND pp_eligible = 1 THEN 'both' " +
        "WHEN mm_eligible = 1 THEN 'min_max_only' WHEN pp_eligible = 1 THEN 'pay_period_only' ELSE 'neither' END";
    private const string EligibilityNear = "CASE WHEN (" +
        "(mm_hours IS NOT NULL AND mm_hours < ? AND mm_hours >= ?) OR (mm_wages IS NOT NULL AND mm_wages < ? AND mm_wages >= ?) OR " +
        "(pp_hours IS NOT NULL AND pp_hours < ? AND pp_hours >= ?) OR (pp_wages IS NOT NULL AND pp_wages < ? AND pp_wages >= ?)) THEN 1 ELSE 0 END";
    private const string EligibilityDrift = "CASE WHEN (mm_hours IS NOT NULL AND mm_eligible <> " +
        "(CASE WHEN mm_hours >= ? AND mm_wages >= ? THEN 1 ELSE 0 END)) OR (pp_hours IS NOT NULL AND pp_eligible <> " +
        "(CASE WHEN pp_hours >= ? AND pp_wages >= ? THEN 1 ELSE 0 END)) THEN 1 ELSE 0 END";

    private string EligibilityPivot()
    {
        // CASE expressions lose SQLite's declared-column decimal collation; reattach it to pivoted text.
        var collate = _database.Dialect is Sql.SqliteDialect ? " COLLATE TCC_DECIMAL" : "";
        var columns = new List<string> { "employee_id", "MAX(record_token) AS record_token" };
        foreach (var (method, prefix) in new[] { ("min_max", "mm"), ("pay_period", "pp") })
        {
            foreach (var (source, target) in new[] { ("weeks_worked", "weeks"), ("avg_weekly_hours", "hours"), ("avg_weekly_wages", "wages") })
            {
                var expression = $"MAX(CASE WHEN method = '{method}' THEN {source} END)";
                columns.Add((collate.Length == 0 ? expression : $"CAST({expression} AS TEXT){collate}") + $" AS {prefix}_{target}");
            }
            columns.Add($"MAX(CASE WHEN method = '{method}' THEN CAST(eligible AS INT) END) AS {prefix}_eligible");
        }
        columns.Add(collate.Length == 0 ? "MAX(total_hours) AS total_hours" : $"CAST(MAX(total_hours) AS TEXT){collate} AS total_hours");
        columns.Add(collate.Length == 0 ? "MAX(total_wages) AS total_wages" : $"CAST(MAX(total_wages) AS TEXT){collate} AS total_wages");
        return "SELECT " + string.Join(", ", columns) + " FROM tcc_gold.employee_eligibility " +
            "WHERE {tenant} AND tax_year = ? AND run_id = ? GROUP BY employee_id";
    }

    private string Classified(bool drift = false) => "WITH pivoted AS (" + EligibilityPivot() +
        "), classified AS (SELECT *, " + EligibilityStatus + " AS status, " + EligibilityNear +
        " AS near_floor" + (drift ? ", " + EligibilityDrift + " AS verdict_drift" : "") + " FROM pivoted) ";
    private static object?[] NearParameters(double hours, double wages, double band) =>
        [hours, hours * (1 - band), wages, wages * (1 - band), hours, hours * (1 - band), wages, wages * (1 - band)];

    private (string Sql, object?[] Values) EligibilityFilter(EligibilityOptions options)
    {
        var terms = new List<string>();
        var values = new List<object?>();
        if (!string.IsNullOrEmpty(options.Status) && options.Status != "all")
        {
            terms.Add("status = ?");
            values.Add(options.Status);
        }
        if (options.NearFloor)
        {
            terms.Add("near_floor = 1");
        }
        if (!string.IsNullOrWhiteSpace(options.Q))
        {
            terms.Add("LOWER(employee_id) LIKE ? ESCAPE '\\'");
            values.Add("%" + _database.Dialect.Like(options.Q.Trim().ToLowerInvariant()) + "%");
        }
        return (terms.Count == 0 ? "" : " WHERE " + string.Join(" AND ", terms), values.ToArray());
    }
}
