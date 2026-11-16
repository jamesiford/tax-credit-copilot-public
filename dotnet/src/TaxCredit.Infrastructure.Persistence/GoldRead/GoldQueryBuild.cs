using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.GoldRead;

public sealed partial class GoldDataQuery
{
    private sealed record Built(string Sql, object?[] Values, IReadOnlyList<GoldQueryColumn> Columns);

    private Built Build(GoldQuerySpec spec, GoldQueryDataset dataset)
    {
        var selected = spec.Select.Select(n => Resolve(dataset, n)).ToList();
        if (selected.Select(c => c.Name).Distinct(StringComparer.Ordinal).Count() != selected.Count)
        {
            throw Refuse("duplicate_label", "Selected columns must be unique.");
        }
        if (dataset.HasMethod && selected.All(c => c.Name != "method"))
        {
            selected.Insert(0, Resolve(dataset, "method"));
        }
        var group = spec.GroupBy.Select(n => Resolve(dataset, n)).ToList();
        if (group.Select(c => c.Name).Distinct(StringComparer.Ordinal).Count() != group.Count)
        {
            throw Refuse("invalid_grouping", "Grouping columns must be unique.");
        }
        if (spec.Measures.Count > 0)
        {
            if (dataset.HasMethod && group.All(c => c.Name != "method"))
            {
                group.Insert(0, Resolve(dataset, "method"));
            }
            if (selected.Any(c => group.All(g => g.Name != c.Name)))
            {
                throw Refuse("invalid_grouping", "Every selected column must be grouped when measures are requested.");
            }
        }
        else if (group.Count > 0)
        {
            throw Refuse("invalid_grouping", "Grouping needs a measure.");
        }
        var columns = selected.ToList();
        var projections = selected.Select(c => "t." + c.Name + " AS " + c.Name).ToList();
        foreach (var measure in spec.Measures)
        {
            var (sql, column) = Aggregate(dataset, measure);
            if (columns.Any(c => c.Name == column.Name))
            {
                throw Refuse("duplicate_label", "Result labels must be unique.");
            }
            columns.Add(column);
            projections.Add(sql + (column.Unit == "USD" && _database.Dialect is SqliteDialect ? " COLLATE TCC_DECIMAL" : "") + " AS " + column.Name);
        }
        var where = Where(spec, dataset);
        var table = dataset.Name == "run_manifest" ? "tcc_ops.run_manifest" : "tcc_gold." + dataset.Name;
        var sqlText = "SELECT " + string.Join(", ", projections) + " FROM " + table + " t WHERE {tenant:t}" + where.Sql;
        if (group.Count > 0)
        {
            sqlText += " GROUP BY " + string.Join(", ", group.Select(c => "t." + c.Name));
        }
        sqlText += " ORDER BY " + Ordering(spec, columns, selected);
        return new Built(_database.Dialect.Page(sqlText, spec.Limit + 1, 0), where.Values, columns);
    }

    private (string Sql, GoldQueryColumn Column) Aggregate(GoldQueryDataset dataset, GoldQueryMeasure measure)
    {
        var alias = measure.Alias ?? (measure.Column == "*" ? "row_count" : measure.Aggregation + "_" + measure.Column);
        if (!Identifier().IsMatch(alias))
        {
            throw Refuse("malformed_spec", "Aggregate labels must be plain identifiers.");
        }
        if (measure.Column == "*")
        {
            if (measure.Aggregation != "count")
            {
                throw Refuse("invalid_aggregation", "Only count may aggregate all rows.");
            }
            return ("COUNT(*)", new GoldQueryColumn(alias, "int", "measure", "public_aggregate", [], []));
        }
        var column = Resolve(dataset, measure.Column);
        if (!column.Aggregations.Contains(measure.Aggregation, StringComparer.Ordinal))
        {
            throw Refuse("invalid_aggregation", "That column does not support this aggregate.");
        }
        var expression = "t." + column.Name;
        var sql = measure.Aggregation switch
        {
            "count_distinct" => $"COUNT(DISTINCT {expression})",
            "sum" when column.Unit == "USD" && _database.Dialect is SqliteDialect =>
                $"CASE WHEN COUNT({expression}) = 0 THEN NULL ELSE tcc_decimal_sum({expression}) END",
            "sum" when column.Type == "bool" => $"SUM(CAST({expression} AS INT))",
            "avg" => $"AVG(CAST({expression} AS {(column.Unit == "USD" ? "DECIMAL(19,4)" : "FLOAT")}))",
            _ => measure.Aggregation.ToUpperInvariant() + "(" + expression + ")",
        };
        var counts = measure.Aggregation is "count" or "count_distinct" || column.Type == "bool";
        return (sql, column with
        {
            Name = alias,
            Type = counts ? "int" : column.Type,
            Role = "measure",
            Sensitivity = "public_aggregate",
            Unit = counts ? null : column.Unit
        });
    }

    private static string Ordering(GoldQuerySpec spec, List<GoldQueryColumn> columns, IReadOnlyList<GoldQueryColumn> selected)
    {
        var order = new List<string>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var item in spec.OrderBy)
        {
            if (!columns.Any(c => c.Name == item.Column) || item.Direction is not "asc" and not "desc")
            {
                throw Refuse("invalid_order", "Order only selected columns or aggregate labels, ascending or descending.");
            }
            order.Add(item.Column + " " + item.Direction.ToUpperInvariant());
            seen.Add(item.Column);
        }
        order.AddRange(selected.Where(c => seen.Add(c.Name)).Select(c => c.Name + " ASC"));
        return order.Count > 0 ? string.Join(", ", order) : columns[0].Name + " ASC";
    }
}
