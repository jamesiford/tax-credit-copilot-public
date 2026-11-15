using System.Globalization;
using System.Text.Json;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Infrastructure.Persistence.GoldRead;

public sealed partial class GoldDataQuery
{
    private (string Sql, object?[] Values) Where(GoldQuerySpec spec, GoldQueryDataset dataset)
    {
        var sql = "";
        var values = new List<object?>();
        if (dataset.Currency == "is_current")
        {
            sql += " AND t.is_current = 1";
        }
        else if (dataset.Currency == "live_run")
        {
            sql += " AND t.run_id = (" + _database.Dialect.Page(
                "SELECT m.run_id FROM tcc_ops.run_manifest m WHERE {tenant:m} AND m.run_status = 'success' " +
                "AND m.superseded_by_run_id IS NULL AND m.run_completed_at IS NOT NULL ORDER BY m.run_started_at DESC", 1, 0) + ")";
        }
        if (spec.TaxYears.Count > 0)
        {
            sql += " AND t.tax_year IN (" + string.Join(", ", spec.TaxYears.Select(_ => "?")) + ")";
            values.AddRange(spec.TaxYears.Cast<object?>());
        }
        if (dataset.HasMethod && spec.Method is "min_max" or "pay_period")
        {
            sql += " AND t.method = ?";
            values.Add(spec.Method);
        }
        foreach (var filter in spec.Filters)
        {
            var built = Predicate(dataset, filter);
            sql += " AND " + built.Sql;
            values.AddRange(built.Values);
        }
        return (sql, values.ToArray());
    }

    private (string Sql, object?[] Values) Predicate(GoldQueryDataset dataset, GoldQueryFilter filter)
    {
        var column = Resolve(dataset, filter.Column);
        if (!column.Operators.Contains(filter.Operator, StringComparer.Ordinal))
        {
            throw Refuse("invalid_operator", "That catalogue column does not support this operator.");
        }
        var expression = "t." + column.Name;
        if (filter.Operator is "in" or "between")
        {
            var items = filter.Value is JsonElement { ValueKind: JsonValueKind.Array } json ? json.EnumerateArray().Cast<object?>().ToArray() :
                filter.Value is System.Collections.IEnumerable list and not string ? list.Cast<object?>().ToArray() : [];
            if (items.Length is < 1 or > 50 || (filter.Operator == "between" && items.Length != 2))
            {
                throw Refuse("value_type_mismatch", "A bounded list is required for in; between requires two values.");
            }
            var values = items.Select(v => FilterValue(column, v)).ToArray();
            return (filter.Operator == "between" ? $"{expression} BETWEEN ? AND ?" :
                expression + " IN (" + string.Join(", ", items.Select(_ => "?")) + ")", values);
        }
        var value = FilterValue(column, filter.Value);
        if (filter.Operator == "contains")
        {
            return ($"LOWER({expression}) LIKE ? ESCAPE '\\'", ["%" + _database.Dialect.Like(((string)value!).ToLowerInvariant()) + "%"]);
        }
        var op = filter.Operator switch { "eq" => "=", "gte" => ">=", "lte" => "<=", _ => throw Refuse("invalid_operator", "Unsupported operator.") };
        return ($"{expression} {op} ?", [value]);
    }

    private static object? FilterValue(GoldQueryColumn column, object? value)
    {
        if (value is JsonElement json)
        {
            value = json.ValueKind switch
            {
                JsonValueKind.String => json.GetString(),
                JsonValueKind.Number => json.GetRawText(),
                JsonValueKind.True => true,
                JsonValueKind.False => false,
                _ => null,
            };
        }
        if (value is null)
        {
            throw Refuse("value_type_mismatch", "Null is not a supported filter value.");
        }
        var text = Convert.ToString(value, CultureInfo.InvariantCulture) ?? "";
        if (column.Type == "bool")
        {
            return value is bool flag ? flag ? 1 : 0 : throw Refuse("value_type_mismatch", "A boolean filter value is required.");
        }
        if (column.Type is "decimal" or "int")
        {
            if (value is bool || !PyFloat.TryParse(text, out var number) || !double.IsFinite(number) ||
                (column.Type == "int" && (number != Math.Truncate(number) || number < long.MinValue || number >= 9223372036854775808.0)))
            {
                throw Refuse("value_type_mismatch", "A finite numeric filter value is required.");
            }
            return column.Type == "int" ? checked((long)number) : PyDecimal.Parse(text);
        }
        if (value is not string || text.Length is < 1 or > 100)
        {
            throw Refuse("value_type_mismatch", "A bounded text filter value is required.");
        }
        if (column.Type == "date")
        {
            return DateOnly.TryParseExact(text, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var day) ?
                day : throw Refuse("value_type_mismatch", "An ISO date is required.");
        }
        if (column.Type == "datetime")
        {
            return DateTime.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out var time) ?
                time : throw Refuse("value_type_mismatch", "An ISO date/time is required.");
        }
        return text;
    }
}
