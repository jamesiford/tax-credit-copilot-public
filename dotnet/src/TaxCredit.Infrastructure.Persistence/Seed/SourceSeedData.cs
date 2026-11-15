using System.Text.Json;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence;

/// <summary>Sources consumes these raw rows and owns tenant-aware projection and resolution.</summary>
public sealed class SourceSeedData(PersistenceDatabase database) : ISeedData
{
    /// <inheritdoc />
    public IReadOnlyDictionary<string, IReadOnlyList<string>> Tables()
    {
        using var session = database.Open();
        return session.QueryExempt(SqlExemption.Seed, "SELECT table_name,columns_json FROM tcc_source.seed_table ORDER BY table_name")
            .ToDictionary(r => (string)r["table_name"]!, r => (IReadOnlyList<string>)JsonSerializer.Deserialize<string[]>((string)r["columns_json"]!)!, StringComparer.Ordinal);
    }

    /// <inheritdoc />
    public IEnumerable<string> ReadTable(string table)
    {
        if (!SeedTables.Source.ContainsKey(table))
        {
            throw new ArgumentException("Unknown source seed table.", nameof(table));
        }

        using var session = database.Open();
        foreach (var row in session.StreamStringsExempt(SqlExemption.Seed,
            "SELECT row_json FROM tcc_source.seed_row WHERE table_name=? ORDER BY ordinal", table))
        {
            yield return row;
        }
    }
}
