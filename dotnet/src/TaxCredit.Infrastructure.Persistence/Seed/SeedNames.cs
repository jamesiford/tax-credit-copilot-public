using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence;

/// <summary>The two local-development seed tables live in the source schema; their names follow the data map's schema.</summary>
internal static class SeedNames
{
    internal static string TableKey(SqlSession session) => session.Dialect.Names.Map.SourceSchema + ".seed_table";

    internal static string RowKey(SqlSession session) => session.Dialect.Names.Map.SourceSchema + ".seed_row";

    internal static string Table(SqlSession session) => session.Dialect.Name(TableKey(session));

    internal static string Row(SqlSession session) => session.Dialect.Name(RowKey(session));

    /// <summary>The flattened SQLite names of every table the importer clears: the mapped Warehouse tables and the seed tables.</summary>
    internal static HashSet<string> Clearable(SqlSession session)
    {
        var names = session.Dialect.Names;
        var flat = names.Map.Tables.Keys.Where(k => k != "ops.schema_migration").Select(names.Flat).ToHashSet(StringComparer.Ordinal);
        flat.Add(names.Map.SourceSchema + "_seed_table");
        flat.Add(names.Map.SourceSchema + "_seed_row");
        return flat;
    }
}
