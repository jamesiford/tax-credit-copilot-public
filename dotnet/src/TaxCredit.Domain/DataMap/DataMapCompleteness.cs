using System.Text.Json.Nodes;

namespace TaxCredit.Domain.DataMap;

/// <summary>Checks a supplied map lists exactly the logical entries the shipped map lists, naming the first difference.</summary>
internal static class DataMapCompleteness
{
    internal static void Check(DataMap reference, DataMap supplied)
    {
        Same("warehouse.tables", reference.Tables.Keys, supplied.Tables.Keys);
        foreach (var (key, table) in reference.Tables)
        {
            Same($"warehouse.tables.{key}.columns", table.Columns.Keys, supplied.Tables[key].Columns.Keys);
        }

        var expected = reference.Lakehouse["tables"]!.AsObject();
        var actual = supplied.Lakehouse["tables"]!.AsObject();
        Same("lakehouse.tables", expected.Select(p => p.Key), actual.Select(p => p.Key));
        foreach (var (logical, node) in expected)
        {
            var fields = node!["fields"]!.AsObject();
            Same($"lakehouse.tables.{logical}.columns", fields.Select(p => p.Key), actual[logical]!["fields"]!.AsObject().Select(p => p.Key));
        }
    }

    private static void Same(string path, IEnumerable<string> expected, IEnumerable<string> actual)
    {
        var have = actual.ToHashSet(StringComparer.Ordinal);
        var want = expected.ToHashSet(StringComparer.Ordinal);
        var missing = want.FirstOrDefault(k => !have.Contains(k));
        if (missing is not null)
        {
            throw new DataMapException($"{path}.{missing} is missing.");
        }

        var unknown = have.FirstOrDefault(k => !want.Contains(k));
        if (unknown is not null)
        {
            throw new DataMapException($"{path}.{unknown} is not a known key.");
        }
    }
}
