using System.Collections.ObjectModel;
using System.Text.Json.Nodes;

namespace TaxCredit.Infrastructure.Sources.Mapping;

public sealed partial class SourceMapping
{
    private static ReadOnlyDictionary<string, SourceTable> ParseTables(JsonObject raw, string prefix, string casing)
    {
        var tables = new Dictionary<string, SourceTable>(StringComparer.Ordinal);
        foreach (var (logical, node) in raw)
        {
            var table = node!.AsObject();
            var physical = prefix + table["table"]!.GetValue<string>();
            physical = casing == "lower" ? physical.ToLowerInvariant() : casing == "upper" ? physical.ToUpperInvariant() : physical;
            ValidateIdentifier(physical);
            var fields = ParseFields(table["fields"]!.AsObject());
            var tenant = table["tenant_field"]?.GetValue<string>();
            if (tenant is not null && (!fields.ContainsKey(tenant) || !fields[tenant].Required))
            {
                throw new ArgumentException("A tenant key must be a required mapped field.");
            }
            tables.Add(logical, new SourceTable(logical, physical, tenant,
                table["optional_reason"] is not null, new ReadOnlyDictionary<string, SourceField>(fields)));
        }
        return new ReadOnlyDictionary<string, SourceTable>(tables);
    }

    private static Dictionary<string, SourceField> ParseFields(JsonObject raw)
    {
        var fields = new Dictionary<string, SourceField>(StringComparer.Ordinal);
        foreach (var (name, node) in raw)
        {
            var value = node!;
            var column = value["column"]!.GetValue<string>();
            var type = value["type"]!.GetValue<string>();
            ValidateIdentifier(column);
            if (!Types.Contains(type)) { throw new ArgumentException("Unsupported source type."); }
            fields.Add(name, new SourceField(column, type, value["required"]?.GetValue<bool>() ?? true,
                value["engine"]?.GetValue<bool>() ?? true));
        }
        return fields;
    }

    private static void ApplyPatch(JsonObject root, JsonObject patch)
    {
        if (patch["version"]?.GetValue<int>() is { } version && version != 1)
        {
            throw new ArgumentException("Unsupported source mapping version.");
        }
        foreach (var (key, value) in patch)
        {
            if (key != "tables") { Merge(root, key, value); continue; }
            foreach (var (logical, edit) in value!.AsObject())
            {
                var table = root["tables"]?[logical]?.AsObject()
                    ?? throw new ArgumentException("A new logical table needs code.");
                PatchTable(table, edit!.AsObject());
            }
        }
    }

    private static void PatchTable(JsonObject table, JsonObject edit)
    {
        var fields = table["fields"]!.AsObject();
        if (edit["drop_fields"] is JsonArray drops)
        {
            foreach (var drop in drops)
            {
                var name = drop!.GetValue<string>();
                var field = fields[name] ?? throw new ArgumentException("Unknown field.");
                if (field["required"]?.GetValue<bool>() != false) { throw new ArgumentException("Required fields cannot be dropped."); }
                fields.Remove(name);
            }
        }
        foreach (var (key, value) in edit)
        {
            if (key == "drop_fields") { continue; }
            if (key == "tenant_field" && !JsonNode.DeepEquals(table[key], value))
            {
                throw new ArgumentException("Tenant semantics cannot be changed by configuration.");
            }
            if (key == "fields")
            {
                foreach (var (name, fieldEdit) in value!.AsObject())
                {
                    if (!fields.ContainsKey(name)) { throw new ArgumentException("A new logical field needs code."); }
                    if (fields[name]!["required"]?.GetValue<bool>() != false && fieldEdit!["required"]?.GetValue<bool>() == false)
                    {
                        throw new ArgumentException("Required fields cannot be weakened.");
                    }
                    Merge(fields, name, fieldEdit);
                }
            }
            else { Merge(table, key, value); }
        }
    }

    private static void Merge(JsonObject target, string key, JsonNode? value)
    {
        if (value is JsonObject child && target[key] is JsonObject existing)
        {
            foreach (var (name, node) in child) { Merge(existing, name, node); }
        }
        else { target[key] = value?.DeepClone(); }
    }
}
