using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Briefs;
using TaxCredit.Application.Features.ReadsCalc;

namespace TaxCredit.Application.Features.Ai.Capabilities.Bindings;

internal static class CapabilityBindingValues
{
    internal static JsonObject Object(object value) => CanonicalPageReads.Object(value);
    internal static JsonElement Body(JsonObject value) => JsonSerializer.SerializeToElement(value);
    internal static string? Text(JsonObject value, string key) => value[key]?.GetValue<string>();
    internal static long Client(JsonObject value) => CapabilityJson.Integer(value["client_id"]!);
    internal static int Year(JsonObject value) => checked((int)CapabilityJson.Integer(value["tax_year"]!));
    internal static JsonObject? Select(JsonObject? value, params string[] keys) => value is null ? null :
        new JsonObject(keys.Select(key => KeyValuePair.Create(key, value[key]?.DeepClone())));
    internal static JsonObject Preview(JsonObject? before, JsonObject after) => new() { ["before"] = before, ["after"] = after };
    internal static CapabilityException NotCalculated(string message) => new(409, "not_calculated", message);

    internal static ReadArguments Arguments(JsonObject value)
    {
        var fields = value.ToDictionary(pair => pair.Key, pair => pair.Value?.ToString(), StringComparer.Ordinal);
        fields["account_id"] = value["client_id"]?.ToString();
        fields["year"] = value["tax_year"]?.ToString();
        return new ReadArguments(fields, Body(value));
    }
}
