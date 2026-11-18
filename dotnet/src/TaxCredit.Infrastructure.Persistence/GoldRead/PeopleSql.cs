using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Filters;

namespace TaxCredit.Infrastructure.Persistence.GoldRead;

public sealed partial class GoldReader
{
    private (string Sql, object?[] Values) PeopleStatement(string site, int year, string method, string run,
        UnitDrillOptions options, bool near, bool count = false)
    {
        var employee = near ? "e.employee_id" : "m.employee_id";
        var columns = new Dictionary<string, FilterColumn>(StringComparer.Ordinal)
        {
            ["employee_id"] = new(employee, "text"),
            ["avg_weekly_hours"] = new("e.avg_weekly_hours", "numeric"),
            ["avg_weekly_wages"] = new("e.avg_weekly_wages", "numeric"),
            ["weeks_worked"] = new("e.weeks_worked", "numeric"),
            ["total_hours"] = new("e.total_hours", "numeric"),
        };
        if (!near)
        {
            columns["weight"] = new("m.weight", "numeric");
        }
        var filters = CompilePeopleFilter(near ? options.NearFilters : options.EmployeeFilters, columns);
        var (sql, values) = near ? NearStatement(site, year, method, run, options.NearMinHours) :
            CountedStatement(site, year, method, run, options.Month);
        sql += filters.Sql;
        values.AddRange(filters.Values);
        if (count)
        {
            return ("SELECT COUNT(*) AS count_rows FROM (" + sql + ") cohort", values.ToArray());
        }
        var key = (options.Sort ?? "").Trim();
        var allowed = key is "employee_id" or "avg_weekly_hours" or "avg_weekly_wages" ||
            (near && key is "weeks_worked" or "total_hours");
        var sort = allowed ? columns[key].SqlExpression : "e.avg_weekly_hours";
        var order = string.Equals(options.Order?.Trim(), "asc", StringComparison.OrdinalIgnoreCase) ? "ASC" : "DESC";
        sql += $" ORDER BY {sort} {order}" + (sort == employee ? "" : ", " + employee);
        return (options.Limit is > 0 ? Page(sql, options.Limit.Value) : sql, values.ToArray());
    }

    private (string Sql, IReadOnlyList<object?> Values) CompilePeopleFilter(string? wire, Dictionary<string, FilterColumn> columns)
    {
        var compiled = GridFilter.Compile(wire, columns);
        var values = compiled.Values.Select(v =>
        {
            if (v is not string text)
            {
                return (object?)v;
            }
            // Domain emits SQL Server bracket escaping; the provider uses one explicit ESCAPE convention.
            var literal = text[1..^1].Replace("[[]", "[", StringComparison.Ordinal)
                .Replace("[%]", "%", StringComparison.Ordinal).Replace("[_]", "_", StringComparison.Ordinal);
            return "%" + _database.Dialect.Like(literal) + "%";
        }).ToArray();
        return (compiled.Sql.Replace(" LIKE ?", " LIKE ? ESCAPE '\\'", StringComparison.Ordinal), values);
    }

    private static (string Sql, List<object?> Values) CountedStatement(string site, int year, string method, string run, int? month)
    {
        if (month is not null)
        {
            ArgumentOutOfRangeException.ThrowIfLessThan(month.Value, 1);
            ArgumentOutOfRangeException.ThrowIfGreaterThan(month.Value, 12);
        }
        var selected = "m.employee_id, m.record_token, m.worksite_id, m.entity_fein, m.first_pps, m.last_ppe, m.weight, " +
            string.Join(", ", GoldValues.Months.Select(c => "m." + c)) +
            ", e.avg_weekly_hours, e.avg_weekly_wages, e.weeks_worked, e.total_hours, e.total_wages, e.first_start, e.last_end ";
        var sql = "SELECT " + selected + "FROM {gold.onezero_matrix} m LEFT JOIN {gold.employee_eligibility} e " +
            "ON e.record_token = m.record_token AND e.client_id = m.client_id AND e.tax_year = m.tax_year " +
            "AND e.method = m.method AND e.run_id = m.run_id WHERE {tenant:m} AND m.worksite_id = ? " +
            "AND m.tax_year = ? AND m.method = ? AND m.run_id = ?";
        if (month is not null)
        {
            sql += $" AND m.month_{month:00} > 0";
        }
        return (sql, [site, year, method, run]);
    }

    private static (string Sql, List<object?> Values) NearStatement(string site, int year, string method, string run, double? minHours)
    {
        var sql = "SELECT DISTINCT e.employee_id, e.record_token, e.avg_weekly_hours, e.avg_weekly_wages, " +
            "e.weeks_worked, e.total_hours, e.total_wages, e.first_start, e.last_end FROM {gold.employee_eligibility} e " +
            "JOIN {gold.employee_period_fact} p ON p.record_token = e.record_token AND p.client_id = e.client_id " +
            "AND p.tax_year = e.tax_year WHERE {tenant:e} AND e.tax_year = ? AND e.method = ? " +
            "AND e.run_id = ? AND e.eligible = 0 AND p.worksite_id = ?";
        var values = new List<object?> { year, method, run, site };
        if (minHours is not null)
        {
            sql += " AND e.avg_weekly_hours >= ?";
            values.Add(minHours);
        }
        return (sql, values);
    }
}
