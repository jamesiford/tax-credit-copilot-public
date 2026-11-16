using System.Globalization;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence;

/// <summary>Evidence from one committed reset, accounting for every manifest table.</summary>
public sealed record SeedLoadResult(string Profile, IReadOnlyDictionary<string, long> TableCounts)
{
    /// <summary>All imported rows, including staged source rows.</summary>
    public long TotalRows => TableCounts.Values.Sum();
}

/// <summary>A library reset hook: stream, validate and replace the complete hermetic state atomically.</summary>
public sealed class SeedImporter
{
    private readonly PersistenceDatabase _database;
    private readonly string _seedRoot;
    private readonly string _repositoryRoot;

    /// <summary>Configures the destination and seed root; the schema root is explicit for copied test fixtures.</summary>
    public SeedImporter(PersistenceDatabase database, string seedRoot, string? repositoryRoot = null)
    {
        ArgumentNullException.ThrowIfNull(database);
        ArgumentException.ThrowIfNullOrWhiteSpace(seedRoot);
        _database = database;
        _seedRoot = Path.GetFullPath(seedRoot);
        _repositoryRoot = repositoryRoot ?? Path.GetFullPath(Path.Combine(_seedRoot, "..", ".."));
    }

    /// <summary>Restores P1 or P2 without accepting a partial reset. Artifact-byte cleanup is a separate integration requirement.</summary>
    public SeedLoadResult Load(string profile)
    {
        if (profile is not ("P1" or "P2"))
        {
            throw new ArgumentException("Unknown seed profile; expected P1 or P2.", nameof(profile));
        }

        if (_database.Dialect is not SqliteDialect)
        {
            throw new NotSupportedException("Hermetic seed reset requires the local SQLite destination.");
        }

        var schema = PersistenceSchema.Read(_repositoryRoot);
        var expected = SeedTables.Expected(profile, schema);
        var folder = Path.Combine(_seedRoot, profile);
        using var manifest = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(folder, "manifest.json")));
        var tables = manifest.RootElement.GetProperty("tables");
        if (manifest.RootElement.GetProperty("profile").GetString() != profile ||
            !tables.EnumerateObject().Select(p => p.Name).Order(StringComparer.Ordinal).SequenceEqual(expected.Keys.Order(StringComparer.Ordinal)))
        {
            throw new InvalidDataException("Seed manifest contains unexpected or missing tables.");
        }

        foreach (var table in tables.EnumerateObject())
        {
            if (!table.Value.GetProperty("columns").EnumerateArray().Select(c => c.GetString()).SequenceEqual(expected[table.Name]))
            {
                throw new InvalidDataException("Seed column contract mismatch: " + table.Name);
            }
        }

        PersistenceSchema.Initialize(_database, _repositoryRoot);
        return _database.Transact(session => Replace(session, profile, folder, tables, schema));
    }

    private static SeedLoadResult Replace(SqlSession session, string profile, string folder, JsonElement tables,
        IReadOnlyDictionary<string, IReadOnlyList<StorageColumn>> schema)
    {
        session.ExecuteExempt(SqlExemption.Seed, "CREATE TABLE IF NOT EXISTS tcc_source.seed_table (table_name TEXT PRIMARY KEY,columns_json TEXT NOT NULL) STRICT");
        session.ExecuteExempt(SqlExemption.Seed, "CREATE TABLE IF NOT EXISTS tcc_source.seed_row (table_name TEXT NOT NULL,ordinal INTEGER NOT NULL,row_json TEXT NOT NULL,PRIMARY KEY(table_name,ordinal)) STRICT");
        var names = session.QueryExempt(SqlExemption.Seed,
            "SELECT name FROM sqlite_master WHERE type='table' AND name<>'tcc_ops_schema_migration' AND (name LIKE 'tcc_ops_%' OR name LIKE 'tcc_gold_%' OR name LIKE 'tcc_source_%')");
        foreach (var row in names)
        {
            session.ExecuteExempt(SqlExemption.Seed, "DELETE FROM " + session.Dialect.Name((string)row["name"]!));
        }

        var counts = new Dictionary<string, long>(StringComparer.Ordinal);
        foreach (var table in tables.EnumerateObject())
        {
            counts.Add(table.Name, ImportTable(session, folder, table.Name, table.Value, schema));
        }

        return new SeedLoadResult(profile, counts);
    }

    private static long ImportTable(SqlSession session, string folder, string path, JsonElement metadata,
        IReadOnlyDictionary<string, IReadOnlyList<StorageColumn>> schema)
    {
        var split = path.Split('/');
        var table = split[1][..^9];
        var isSource = split[0] == "source";
        var destination = (split[0] == "gold" ? "tcc_gold." : "tcc_ops.") + table;
        var columns = metadata.GetProperty("columns").EnumerateArray().Select(c => c.GetString()!).ToArray();
        if (isSource)
        {
            session.InsertExempt(SqlExemption.Seed, "tcc_source.seed_table", ["table_name", "columns_json"],
                [new object?[] { table, JsonSerializer.Serialize(columns) }]);
        }

        using var file = File.OpenRead(Path.Combine(folder, split[0], split[1]));
        var shipped = Convert.ToHexStringLower(SHA256.HashData(file));
        if (!string.Equals(shipped, metadata.GetProperty("sha256").GetString(), StringComparison.Ordinal))
        {
            throw new InvalidDataException("Shipped seed hash mismatch: " + path);
        }

        file.Position = 0;
        using var gzip = new GZipStream(file, CompressionMode.Decompress, leaveOpen: true);
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        using var hashing = new HashingReadStream(gzip, hash);
        using var reader = new StreamReader(hashing, new UTF8Encoding(false, true), false, 65536, leaveOpen: true);
        var batch = new List<IReadOnlyList<object?>>(500);
        long count = 0;
        while (reader.ReadLine() is { } line)
        {
            using var json = JsonDocument.Parse(line);
            if (json.RootElement.ValueKind != JsonValueKind.Object ||
                !json.RootElement.EnumerateObject().Select(p => p.Name).SequenceEqual(columns) ||
                json.RootElement.EnumerateObject().Any(p => p.Value.ValueKind is JsonValueKind.Array or JsonValueKind.Object))
            {
                throw new InvalidDataException("Malformed seed row: " + path);
            }

            count++;
            batch.Add(isSource ? new object?[] { table, count, line }
                : columns.Select(column => SeedValue(json.RootElement.GetProperty(column), schema[destination].First(c => c.Name == column), split[0] == "gold")).ToArray());
            if (batch.Count == 500)
            {
                Flush(session, isSource, destination, columns, batch);
            }
        }

        Flush(session, isSource, destination, columns, batch);
        if (count != metadata.GetProperty("rows").GetInt64() ||
            !string.Equals(Convert.ToHexStringLower(hash.GetHashAndReset()), metadata.GetProperty("content_sha256").GetString(), StringComparison.Ordinal))
        {
            throw new InvalidDataException("Decompressed seed hash or row count mismatch: " + path);
        }

        return count;
    }

    private static void Flush(SqlSession session, bool source, string table, string[] columns, List<IReadOnlyList<object?>> rows)
    {
        if (rows.Count == 0)
        {
            return;
        }

        if (source)
        {
            session.InsertExempt(SqlExemption.Seed, "tcc_source.seed_row", ["table_name", "ordinal", "row_json"], rows);
        }
        else
        {
            foreach (var group in rows.GroupBy(r => (long)r[Array.IndexOf(columns, "client_id")]!))
            {
                session.Insert(group.Key, table, columns, group.ToArray());
            }
        }

        rows.Clear();
    }

    private static object? SeedValue(JsonElement value, StorageColumn column, bool gold)
    {
        object? raw = value.ValueKind switch
        {
            JsonValueKind.Null => null,
            JsonValueKind.String => value.GetString(),
            JsonValueKind.True => 1L,
            JsonValueKind.False => 0L,
            JsonValueKind.Number when column.SqlType is "INT" or "BIGINT" or "BIT" => value.GetInt64(),
            JsonValueKind.Number when column.SqlType is "VARCHAR" or "CHAR" => value.GetRawText(),
            JsonValueKind.Number => gold ? PyFloat.Repr(value.GetDouble()) : value.GetRawText(),
            _ => throw new InvalidDataException("Seed value must be scalar."),
        };
        if (raw is string text && column.SqlType == "DATE")
        {
            if (text.Length == 10)
            {
                DateOnly.ParseExact(text, "yyyy-MM-dd", CultureInfo.InvariantCulture);
            }
            else
            {
                DateTimeOffset.Parse(text, CultureInfo.InvariantCulture);
            }
        }

        return column.ConvertValue(raw, retainSeedScale: true);
    }
}
