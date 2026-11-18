using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace TaxCredit.Domain.DataMap;

/// <summary>
/// Reads and validates a complete data map. A supplied file is complete, not a patch: it must list exactly the logical
/// entries the embedded shipped map lists, or loading fails naming the first missing or unknown key.
/// </summary>
public static partial class DataMapLoader
{
    private const string ResourceName = "data-map.json";

    /// <summary>Loads the shipped map embedded in this assembly (generated from <c>docs/data/data-map.json</c>).</summary>
    public static DataMap LoadEmbedded()
    {
        using var stream = typeof(DataMapLoader).Assembly.GetManifestResourceStream(ResourceName)
            ?? throw new DataMapException("The embedded data map is missing from the assembly.");
        using var buffer = new MemoryStream();
        stream.CopyTo(buffer);
        return Parse(buffer.ToArray(), "embedded", null);
    }

    /// <summary>Loads a supplied map file and checks it is complete against the embedded inventory.</summary>
    public static DataMap LoadFile(string path)
    {
        byte[] bytes;
        try
        {
            bytes = File.ReadAllBytes(path);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            throw new DataMapException($"The data map file '{path}' cannot be read: {ex.Message}");
        }

        return Parse(bytes, "file", DataMap.Default);
    }

    /// <summary>Loads the file named by <c>DATA_MAP_FILE</c>, or the embedded map when the value is null or empty.</summary>
    public static DataMap Load(string? path) => string.IsNullOrWhiteSpace(path) ? DataMap.Default : LoadFile(path.Trim());

    internal static DataMap Parse(byte[] bytes, string source, DataMap? reference)
    {
        JsonObject root;
        try
        {
            root = JsonNode.Parse(bytes, null, new JsonDocumentOptions { CommentHandling = JsonCommentHandling.Skip })?.AsObject()
                ?? throw new DataMapException("The data map is empty.");
        }
        catch (JsonException ex)
        {
            throw new DataMapException($"The data map is not valid JSON: {ex.Message}");
        }

        Known(root, "", "version", "lakehouse", "warehouse");
        if (Node(root, "version", "") is not JsonValue { } v || !v.TryGetValue<int>(out var version) || version != 1)
        {
            throw new DataMapException("version must be 1.");
        }

        var lake = Obj(root, "lakehouse", "");
        var warehouse = Obj(root, "warehouse", "");
        Known(lake, "lakehouse", "database", "schema", "case_insensitive_columns", "naming", "transforms", "tables");
        Known(warehouse, "warehouse", "database", "schemas", "tables");
        var schemas = Obj(warehouse, "schemas", "warehouse");
        Known(schemas, "warehouse.schemas", "gold", "ops");
        var gold = Ident(schemas, "gold", "warehouse.schemas");
        var ops = Ident(schemas, "ops", "warehouse.schemas");
        if (string.Equals(gold, ops, StringComparison.OrdinalIgnoreCase))
        {
            throw new DataMapException("warehouse.schemas.gold and warehouse.schemas.ops must differ.");
        }

        var tables = WarehouseTables(Obj(warehouse, "tables", "warehouse"));
        var lakehouse = LakehouseShape(lake);
        var data = new DataMap(source, Convert.ToHexStringLower(SHA256.HashData(bytes)), DatabaseName(lake), DatabaseName(warehouse),
            Ident(lake, "schema", "lakehouse"), gold, ops, tables, lakehouse);
        if (reference is not null)
        {
            DataMapCompleteness.Check(reference, data);
        }

        return data;
    }

    private static string? DatabaseName(JsonObject section)
    {
        var db = Obj(section, "database", "");
        Known(db, "database", "logical", "name");
        return db["name"] is null ? null : Ident(db, "name", "database");
    }

    private static Dictionary<string, WarehouseTable> WarehouseTables(JsonObject tables)
    {
        var result = new Dictionary<string, WarehouseTable>(StringComparer.Ordinal);
        var physical = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var (key, node) in Entries(tables))
        {
            var path = $"warehouse.tables.{key}";
            var t = node as JsonObject ?? throw new DataMapException($"{path} must be an object.");
            Known(t, path, "schema", "table", "columns");
            var schema = Str(t, "schema", path);
            var dot = key.IndexOf('.', StringComparison.Ordinal);
            if (dot < 0 || key[..dot] != schema || schema is not ("gold" or "ops"))
            {
                throw new DataMapException($"{path}: the key must be '<gold|ops>.<table>' and match its schema.");
            }

            var table = Ident(t, "table", path);
            if (physical.TryGetValue(schema + "." + table, out var other))
            {
                throw new DataMapException($"{path}: table '{table}' is already mapped from {other}.");
            }

            physical[schema + "." + table] = key;
            var columns = new Dictionary<string, string>(StringComparer.Ordinal);
            var seen = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var (logical, cNode) in Entries(Obj(t, "columns", path)))
            {
                var cPath = $"{path}.columns.{logical}";
                var c = cNode as JsonObject ?? throw new DataMapException($"{cPath} must be an object.");
                Known(c, cPath, "column", "type");
                var column = Ident(c, "column", cPath);
                if (seen.TryGetValue(column, out var dup))
                {
                    throw new DataMapException($"{cPath}: column '{column}' is already mapped from {dup}.");
                }

                seen[column] = logical;
                columns[logical] = column;
            }

            result[key] = new WarehouseTable(key, schema, key[(dot + 1)..], table, columns);
        }

        return result;
    }

    private static JsonObject LakehouseShape(JsonObject lake)
    {
        var naming = Obj(lake, "naming", "lakehouse");
        Known(naming, "lakehouse.naming", "table_prefix", "table_case");
        var transforms = Obj(lake, "transforms", "lakehouse");
        Known(transforms, "lakehouse.transforms", "worksite_location", "null_pay_date");
        var tables = new JsonObject();
        var physical = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var (logical, node) in Entries(Obj(lake, "tables", "lakehouse")))
        {
            var path = $"lakehouse.tables.{logical}";
            var t = node as JsonObject ?? throw new DataMapException($"{path} must be an object.");
            Known(t, path, ["table", "dataset_attr", "columns"], ["tenant_field", "partition_by", "optional_reason"]);
            var name = Ident(t, "table", path);
            if (physical.TryGetValue(name, out var other))
            {
                throw new DataMapException($"{path}: table '{name}' is already mapped from {other}.");
            }

            physical[name] = logical;
            var entry = new JsonObject();
            foreach (var (k, v) in t.Where(p => p.Key != "columns" && !p.Key.StartsWith('_')))
            {
                entry[k] = v?.DeepClone();
            }

            var fields = new JsonObject();
            var seen = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var (field, cNode) in Entries(Obj(t, "columns", path)))
            {
                var cPath = $"{path}.columns.{field}";
                var c = cNode as JsonObject ?? throw new DataMapException($"{cPath} must be an object.");
                Known(c, cPath, "column", "type", "required", "engine");
                var column = Ident(c, "column", cPath);
                if (seen.TryGetValue(column, out var dup))
                {
                    throw new DataMapException($"{cPath}: column '{column}' is already mapped from {dup}.");
                }

                seen[column] = field;
                var spec = new JsonObject { ["column"] = column, ["type"] = Str(c, "type", cPath) };
                foreach (var flag in new[] { "required", "engine" })
                {
                    spec[flag] = c[flag] is JsonValue f && f.TryGetValue<bool>(out var b) ? b
                        : throw new DataMapException($"{cPath}.{flag} must be true or false.");
                }

                fields[field] = spec;
            }

            entry["table"] = name;
            entry["fields"] = fields;
            tables[logical] = entry;
        }

        return new JsonObject
        {
            ["version"] = 1,
            ["case_insensitive_columns"] = lake["case_insensitive_columns"] is JsonValue ci && ci.TryGetValue<bool>(out var b2) ? b2
                : throw new DataMapException("lakehouse.case_insensitive_columns must be true or false."),
            ["naming"] = new JsonObject { ["table_prefix"] = Prefix(naming), ["table_case"] = Str(naming, "table_case", "lakehouse.naming") },
            ["transforms"] = new JsonObject
            {
                ["worksite_location"] = Str(transforms, "worksite_location", "lakehouse.transforms"),
                ["null_pay_date"] = Str(transforms, "null_pay_date", "lakehouse.transforms"),
            },
            ["tables"] = tables,
        };
    }

    private static string Prefix(JsonObject naming)
    {
        var prefix = Str(naming, "table_prefix", "lakehouse.naming");
        return prefix.Length == 0 || PrefixPattern().IsMatch(prefix) ? prefix
            : throw new DataMapException("lakehouse.naming.table_prefix is not a plain identifier prefix.");
    }

    internal static IEnumerable<KeyValuePair<string, JsonNode?>> Entries(JsonObject o) => o.Where(p => !p.Key.StartsWith('_'));

    private static void Known(JsonObject o, string path, params string[] required) => Known(o, path, required, []);

    private static void Known(JsonObject o, string path, string[] required, string[] optional)
    {
        foreach (var key in o.Select(p => p.Key).Where(k => !k.StartsWith('_') && !required.Contains(k) && !optional.Contains(k)))
        {
            throw new DataMapException($"{Join(path, key)} is not a known key.");
        }

        foreach (var key in required.Where(k => !o.ContainsKey(k)))
        {
            throw new DataMapException($"{Join(path, key)} is missing.");
        }
    }

    private static JsonNode Node(JsonObject o, string key, string path) =>
        o[key] ?? throw new DataMapException($"{Join(path, key)} is missing.");

    private static JsonObject Obj(JsonObject o, string key, string path) =>
        Node(o, key, path) as JsonObject ?? throw new DataMapException($"{Join(path, key)} must be an object.");

    private static string Str(JsonObject o, string key, string path) =>
        Node(o, key, path) is JsonValue v && v.TryGetValue<string>(out var s) ? s
            : throw new DataMapException($"{Join(path, key)} must be a string.");

    private static string Ident(JsonObject o, string key, string path)
    {
        var value = Node(o, key, path) is JsonValue v && v.TryGetValue<string>(out var s) ? s
            : throw new DataMapException($"{Join(path, key)} must be a name (an unmatched entry still has a null value).");
        return IdentifierPattern().IsMatch(value) ? value
            : throw new DataMapException($"{Join(path, key)} '{value}' is not a plain identifier (no quotes or brackets).");
    }

    private static string Join(string path, string key) => path.Length == 0 ? key : path + "." + key;

    [GeneratedRegex("^[A-Za-z_][A-Za-z0-9_\\-]{0,127}$", RegexOptions.CultureInvariant)]
    private static partial Regex IdentifierPattern();

    [GeneratedRegex("^[A-Za-z0-9_\\-]{1,64}$", RegexOptions.CultureInvariant)]
    private static partial Regex PrefixPattern();
}
