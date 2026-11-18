namespace TaxCredit.Infrastructure.Persistence.GoldRead;

public sealed partial class GoldReader
{
    private IReadOnlyDictionary<string, object?>[] PageMonths(long clientId, string method,
        IReadOnlyList<IReadOnlyDictionary<string, object?>> items)
    {
        var months = new List<IReadOnlyDictionary<string, object?>>();
        foreach (var chunk in items.Chunk(600))
        {
            var selected = string.Join(" OR ", chunk.Select(_ => "(m.worksite_id = ? AND m.tax_year = ? AND m.run_id = ?)"));
            object?[] values = [method, .. chunk.SelectMany(r => new[] { r["worksite_id"], r["tax_year"], r["run_id"] })];
            months.AddRange(Many(clientId, "SELECT s.* FROM {gold.unit_month_summary} s JOIN {gold.unit_year_master} m " +
                "ON m.client_id = s.client_id AND m.tax_year = s.tax_year AND m.method = s.method AND m.worksite_id = s.worksite_id " +
                "AND m.run_id = s.run_id WHERE {tenant:s} AND m.is_current = 1 AND m.method = ? AND (" + selected + ") " +
                "ORDER BY s.worksite_id, s.tax_year", values));
        }
        return months.OrderBy(r => GoldValues.Text(r, "worksite_id"), StringComparer.Ordinal)
            .ThenBy(r => GoldValues.Int(r, "tax_year")).ToArray();
    }
}
