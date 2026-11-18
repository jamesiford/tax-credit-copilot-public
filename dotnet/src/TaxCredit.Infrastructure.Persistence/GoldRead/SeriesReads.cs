namespace TaxCredit.Infrastructure.Persistence.GoldRead;

public sealed partial class GoldReader
{
    private IReadOnlyDictionary<string, object?>? MethodSummary(long clientId, int year, string method, string runId) =>
        One(clientId, Page("SELECT * FROM {gold.run_method_summary} WHERE {tenant} AND tax_year = ? " +
            "AND method = ? AND run_id = ? ORDER BY tax_year", 1), year, method, runId);

    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?> HeadcountSeries(long clientId, int taxYear, string method, string? programCode = null)
    {
        var run = LatestRun(clientId, programCode);
        if (run is null)
        {
            return new Dictionary<string, object?> { ["run"] = null, ["months"] = Array.Empty<double>(), ["annual_average"] = null, ["month_ends"] = Array.Empty<string>() };
        }
        var sums = string.Join(", ", GoldValues.Months.Select(c => $"SUM({c}) AS {c}"));
        var row = One(clientId, $"SELECT {sums}, MAX(unreachable_months) AS unreachable_months " +
            "FROM {gold.unit_month_summary} WHERE {tenant} AND tax_year = ? AND method = ? AND run_id = ?",
            taxYear, method, run["run_id"])!;
        var summary = MethodSummary(clientId, taxYear, method, GoldValues.Text(run, "run_id"));
        var unreachable = GoldValues.Text(row, "unreachable_months").Split(',').Select(p => p.Trim())
            .Where(p => p.Length > 0 && p.All(char.IsAsciiDigit)).Select(int.Parse).ToArray();
        return new Dictionary<string, object?>
        {
            ["run"] = run,
            ["months"] = GoldValues.Months.Select(c => GoldValues.Number(row, c)).ToArray(),
            ["month_ends"] = GoldValues.MonthEnds(summary),
            ["unreachable_months"] = unreachable,
            ["annual_average"] = summary?["annual_average"],
        };
    }

    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?> ClientYearSeries(long clientId, string method = "pay_period", string? programCode = null)
    {
        var run = LatestRun(clientId, programCode);
        if (run is null)
        {
            return new Dictionary<string, object?> { ["run"] = null, ["years"] = GoldValues.EmptyRows };
        }
        var summary = Many(clientId, "SELECT tax_year, annual_average, eligible_employees, employees_evaluated, contested_months " +
            "FROM {gold.run_method_summary} WHERE {tenant} AND method = ? AND run_id = ? ORDER BY tax_year", method, run["run_id"]);
        var (where, values) = UnitWhere(method, null, programCode);
        var credit = Many(clientId, $"SELECT tax_year, {Sum("annual_credit_usd")} AS annual_credit_usd, " +
            "MAX(CAST(is_base_year AS INT)) AS has_base_year, SUM(CAST(qualified AS INT)) AS qualified_units, COUNT(*) AS units " +
            "FROM {gold.unit_year_master} WHERE " + where + " GROUP BY tax_year ORDER BY tax_year", values)
            .ToDictionary(r => GoldValues.Int(r, "tax_year"));
        var years = summary.Select(row =>
        {
            credit.TryGetValue(GoldValues.Int(row, "tax_year"), out var priced);
            return new Dictionary<string, object?>
            {
                ["tax_year"] = GoldValues.Int(row, "tax_year"),
                ["annual_average"] = GoldValues.Number(row, "annual_average"),
                ["eligible_employees"] = GoldValues.Int(row, "eligible_employees"),
                ["employees_evaluated"] = GoldValues.Int(row, "employees_evaluated"),
                ["annual_credit_usd"] = priced?["annual_credit_usd"],
                ["is_base_year"] = priced is not null && GoldValues.Int(priced, "has_base_year") != 0,
                ["qualified_units"] = priced is null ? 0 : GoldValues.Int(priced, "qualified_units"),
                ["units"] = priced is null ? 0 : GoldValues.Int(priced, "units"),
            };
        }).ToArray();
        return new Dictionary<string, object?> { ["run"] = run, ["years"] = years, ["method"] = method };
    }

    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?> OnezeroMatrix(long clientId, int taxYear, string method, string? programCode = null)
    {
        var run = LatestRun(clientId, programCode);
        var summary = run is null ? null : MethodSummary(clientId, taxYear, method, GoldValues.Text(run, "run_id"));
        var result = new Dictionary<string, object?> { ["run"] = run, ["summary"] = summary, ["matrix"] = GoldValues.EmptyRows, ["units"] = GoldValues.EmptyRows };
        if (summary is null)
        {
            return result;
        }
        object?[] values = [taxYear, method, run!["run_id"]];
        result["matrix"] = Many(clientId, "SELECT employee_id, record_token, worksite_id, entity_fein, weight, " +
            string.Join(", ", GoldValues.Months) + " FROM {gold.onezero_matrix} WHERE {tenant} AND tax_year = ? " +
            "AND method = ? AND run_id = ? ORDER BY worksite_id, employee_id", values);
        var sums = string.Join(", ", GoldValues.Months.Select(c => $"SUM(m.{c}) AS {c}"));
        var total = string.Join(" + ", GoldValues.Months.Select(c => $"SUM(m.{c})"));
        result["units"] = Many(clientId, "SELECT COALESCE(NULLIF(m.worksite_id, ''), '(unattributed)') AS worksite_id, " +
            "COALESCE(NULLIF(m.entity_fein, ''), '(unattributed)') AS entity_fein, " + sums +
            $", {total} AS total, ROUND(({total}) / 12.0, 2) AS average_headcount FROM {{gold.onezero_matrix}} m " +
            "WHERE {tenant:m} AND m.tax_year = ? AND m.method = ? AND m.run_id = ? " +
            "GROUP BY COALESCE(NULLIF(m.worksite_id, ''), '(unattributed)'), COALESCE(NULLIF(m.entity_fein, ''), '(unattributed)') " +
            "ORDER BY worksite_id, entity_fein", values);
        return result;
    }
}
