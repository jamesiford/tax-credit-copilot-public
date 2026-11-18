using System.Collections.ObjectModel;
using System.Text.Json.Nodes;

namespace TaxCredit.Domain.DataMap;

/// <summary>The data map is malformed, incomplete or contradicts itself; the message names the first offending key.</summary>
public sealed class DataMapException(string message) : InvalidOperationException(message);

/// <summary>One Warehouse table: its logical key (<c>ops.run_manifest</c>), actual table name and actual column names.</summary>
public sealed class WarehouseTable(string key, string schema, string logical, string physical,
    IReadOnlyDictionary<string, string> columns)
{
    /// <summary>The logical key, <c>gold.x</c> or <c>ops.x</c>.</summary>
    public string Key { get; } = key;

    /// <summary>The logical schema, <c>gold</c> or <c>ops</c>.</summary>
    public string Schema { get; } = schema;

    /// <summary>The logical table name the code speaks.</summary>
    public string Logical { get; } = logical;

    /// <summary>The actual table name in the database.</summary>
    public string Physical { get; } = physical;

    /// <summary>Logical column name to actual column name, in DDL order.</summary>
    public IReadOnlyDictionary<string, string> Columns { get; } = columns;
}

/// <summary>
/// The validated data map: the actual database, schema, table and column names behind the logical names the code speaks.
/// Built once at start-up by <see cref="DataMapLoader" />; immutable afterwards.
/// </summary>
public sealed class DataMap
{
    internal DataMap(string source, string sha256, string? sourceDatabase, string? warehouseDatabase, string sourceSchema,
        string goldSchema, string opsSchema, IReadOnlyDictionary<string, WarehouseTable> tables, JsonObject lakehouse)
    {
        Source = source;
        Sha256 = sha256;
        SourceDatabase = sourceDatabase;
        WarehouseDatabase = warehouseDatabase;
        SourceSchema = sourceSchema;
        GoldSchema = goldSchema;
        OpsSchema = opsSchema;
        Tables = new ReadOnlyDictionary<string, WarehouseTable>(new Dictionary<string, WarehouseTable>(tables, StringComparer.Ordinal));
        Lakehouse = lakehouse;
    }

    /// <summary>The embedded shipped map, parsed once. It is also the inventory every supplied file is checked against.</summary>
    public static DataMap Default { get; } = DataMapLoader.LoadEmbedded();

    /// <summary><c>embedded</c> or <c>file</c>.</summary>
    public string Source { get; }

    /// <summary>SHA-256 of the file's bytes (hex), reported by readiness; never the values.</summary>
    public string Sha256 { get; }

    /// <summary>The map's Lakehouse database name, or null to use the environment setting.</summary>
    public string? SourceDatabase { get; }

    /// <summary>The map's Warehouse database name, or null to use the environment setting.</summary>
    public string? WarehouseDatabase { get; }

    /// <summary>The actual Lakehouse schema.</summary>
    public string SourceSchema { get; }

    /// <summary>The actual Warehouse schema behind the logical <c>gold</c>.</summary>
    public string GoldSchema { get; }

    /// <summary>The actual Warehouse schema behind the logical <c>ops</c>.</summary>
    public string OpsSchema { get; }

    /// <summary>Warehouse tables by logical key (<c>ops.run_manifest</c>).</summary>
    public IReadOnlyDictionary<string, WarehouseTable> Tables { get; }

    /// <summary>The Lakehouse section in the source-mapping shape (<c>tables.*.fields</c>), for <c>SourceMapping</c>.</summary>
    public JsonObject Lakehouse { get; }

    /// <summary>The actual schema for a logical one.</summary>
    public string Schema(string logical) => logical switch
    {
        "gold" => GoldSchema,
        "ops" => OpsSchema,
        _ => throw new DataMapException($"warehouse.schemas.{logical} is not a logical schema."),
    };
}
