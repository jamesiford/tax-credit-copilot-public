using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Infrastructure.Persistence.GoldRead;

public sealed partial class GoldReader
{
    /// <inheritdoc />
    public IReadOnlyList<IReadOnlyDictionary<string, object?>> UnitEmployees(long clientId, string worksiteId, int taxYear, string method, string runId, int? month = null)
    {
        var (sql, values) = PeopleStatement(worksiteId, taxYear, method, runId, new UnitDrillOptions { Month = month }, false);
        return Many(clientId, sql, values);
    }

    /// <inheritdoc />
    public IReadOnlyList<IReadOnlyDictionary<string, object?>> UnitNearThreshold(long clientId, string worksiteId, int taxYear, string method, string runId)
    {
        var (sql, values) = PeopleStatement(worksiteId, taxYear, method, runId, new UnitDrillOptions(), true);
        return Many(clientId, sql, values);
    }

    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?> UnitDrill(long clientId, string worksiteId, int taxYear, string method, UnitDrillOptions? options = null)
    {
        options ??= new UnitDrillOptions();
        using var scope = Scope();
        var run = LatestRun(clientId, options.ProgramCode);
        var inFlight = RunInFlight(clientId);
        var unit = Unit(clientId, worksiteId, taxYear, method, options.ProgramCode);
        var (where, parameters) = UnitWhere(method, taxYear, options.ProgramCode);
        var count = One(clientId, "SELECT COUNT(*) AS count_rows FROM {gold.unit_year_master} WHERE " + where, parameters)!;
        var held = GoldValues.Int(count, "count_rows") > 0;
        if (run is null || !held)
        {
            return new Dictionary<string, object?>
            {
                ["run"] = held ? run : null,
                ["in_flight"] = inFlight,
                ["unit"] = null,
                ["employees"] = GoldValues.EmptyRows,
                ["months"] = null,
                ["near_threshold"] = GoldValues.EmptyRows,
                ["employees_total"] = 0,
                ["near_total"] = 0,
                ["year_held"] = held,
            };
        }
        var runId = GoldValues.Text(run, "run_id");
        var countedSql = PeopleStatement(worksiteId, taxYear, method, runId, options, false);
        var nearSql = PeopleStatement(worksiteId, taxYear, method, runId, options, true);
        var employees = Many(clientId, countedSql.Sql, countedSql.Values);
        var near = Many(clientId, nearSql.Sql, nearSql.Values);
        return new Dictionary<string, object?>
        {
            ["run"] = run,
            ["in_flight"] = inFlight,
            ["unit"] = unit,
            ["employees"] = employees,
            ["months"] = UnitMonths(clientId, worksiteId, taxYear, method, runId),
            ["near_threshold"] = near,
            ["employees_total"] = PeopleTotal(clientId, worksiteId, taxYear, method, runId, options, false, employees.Count),
            ["near_total"] = PeopleTotal(clientId, worksiteId, taxYear, method, runId, options, true, near.Count),
            ["year_held"] = true,
        };
    }

    private int PeopleTotal(long clientId, string site, int year, string method, string run, UnitDrillOptions options, bool near, int displayed)
    {
        if (string.IsNullOrEmpty(near ? options.NearFilters : options.EmployeeFilters))
        {
            return displayed;
        }
        var (sql, values) = PeopleStatement(site, year, method, run,
            options with { EmployeeFilters = null, NearFilters = null }, near, true);
        return GoldValues.Int(One(clientId, sql, values)!, "count_rows");
    }

    /// <inheritdoc />
    public IReadOnlyList<IReadOnlyDictionary<string, object?>> Employee(string recordToken, long clientId, int taxYear, string runId) =>
        Many(clientId, "SELECT * FROM {gold.employee_eligibility} WHERE {tenant} AND record_token = ? " +
            "AND tax_year = ? AND run_id = ? ORDER BY method", recordToken, taxYear, runId);

    /// <inheritdoc />
    public IReadOnlyList<IReadOnlyDictionary<string, object?>> EmployeeUnits(string recordToken, long clientId, int taxYear, string runId, string method) =>
        Many(clientId, "SELECT worksite_id, entity_fein, first_pps, last_ppe, weight, " +
            string.Join(", ", GoldValues.Months) + " FROM {gold.onezero_matrix} WHERE {tenant} AND record_token = ? " +
            "AND tax_year = ? AND run_id = ? AND method = ? ORDER BY worksite_id", recordToken, taxYear, runId, method);

    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?> EmployeeDrill(long clientId, int taxYear, string recordToken, string? programCode = null)
    {
        using var scope = Scope();
        var run = LatestRun(clientId, programCode);
        if (run is null)
        {
            return new Dictionary<string, object?> { ["run"] = null, ["verdicts"] = GoldValues.EmptyRows, ["segments"] = GoldValues.EmptyRows, ["periods"] = GoldValues.EmptyRows };
        }
        object?[] values = [taxYear, run["run_id"], recordToken];
        var verdicts = Many(clientId, "SELECT method, employee_id, weeks_worked, total_hours, total_wages, avg_weekly_hours, " +
            "avg_weekly_wages, eligible, weight, days, first_start, last_end FROM {gold.employee_eligibility} " +
            "WHERE {tenant} AND tax_year = ? AND run_id = ? AND record_token = ?", values);
        var segments = Many(clientId, "SELECT method, worksite_id, entity_fein, first_pps, last_ppe, weight, " +
            string.Join(", ", GoldValues.Months) + " FROM {gold.onezero_matrix} " +
            "WHERE {tenant} AND tax_year = ? AND run_id = ? AND record_token = ? ORDER BY method, worksite_id, first_pps", values);
        var periods = Many(clientId, "SELECT worksite_id, entity_fein, job_title, pay_period_start, pay_period_end, pay_date, " +
            "pay_frequency_code, hours, wages, pay_code, selection_decision FROM {gold.employee_period_fact} " +
            "WHERE {tenant} AND tax_year = ? AND run_id = ? AND record_token = ? ORDER BY pay_period_end", values);
        return new Dictionary<string, object?>
        {
            ["run"] = run,
            ["verdicts"] = verdicts,
            ["segments"] = segments,
            ["periods"] = periods,
            ["month_ends"] = GoldValues.MonthEnds(MethodSummary(clientId, taxYear, "min_max", GoldValues.Text(run, "run_id"))),
        };
    }
}
