using System.Globalization;
using System.Text.Json.Nodes;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.Ai.Briefs;

internal static class BriefValues
{
    internal static readonly IReadOnlyDictionary<string, string> BandLabels = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["exposed"] = "Exposed",
        ["on_the_line"] = "On the line",
        ["declining"] = "Declining",
        ["unclaimed_at_scale"] = "Identified",
        ["not_assessed"] = "Not assessed",
        ["settled"] = "Nothing found",
        ["unavailable"] = "Unavailable"
    };

    internal static string Text(JsonNode? value, string fallback = "") => value?.ToString() ?? fallback;
    internal static double? Number(JsonNode? value) => double.TryParse(value?.ToString(),
        NumberStyles.Float, CultureInfo.InvariantCulture, out var number) && double.IsFinite(number) ? number : null;
    internal static int Integer(JsonNode? value, int fallback = 0) => Number(value) is { } n ? checked((int)n) : fallback;
    internal static bool True(JsonNode? value) => value is JsonValue scalar && scalar.TryGetValue<bool>(out var b) && b;
    internal static JsonObject Object(JsonNode? node) => node as JsonObject ?? new JsonObject();
    internal static IEnumerable<JsonObject> Rows(JsonNode? node) => node is JsonArray array ? array.OfType<JsonObject>() : [];
    internal static string One(JsonNode? value) => Number(value) is { } n ? Fixed(n, 1) : "\u2014";
    internal static string Fixed(double value, int places) => PyRound.Round(value, places).ToString("F" + places.ToString(CultureInfo.InvariantCulture), CultureInfo.InvariantCulture);
    internal static string General(double value) => value.ToString("G", CultureInfo.InvariantCulture);
    internal static string Usd(JsonNode? value) => Number(value) is { } n ? "$" + PyRound.Round(n, 0).ToString("N0", CultureInfo.InvariantCulture) : "\u2014";
    internal static string Plural(int count, string word) => string.Create(CultureInfo.InvariantCulture, $"{count} {word}{(count == 1 ? "" : "s")}");
    internal static JsonArray Array(IEnumerable<string> values) => new(values.Select(v => (JsonNode?)JsonValue.Create(v)).ToArray());
    internal static PageBrief NotCalculated(string page, string subject, JsonObject payload)
    {
        var message = Text(payload["message"], "No calculated run holds this yet. That is not a zero.");
        return new(page, subject, message, [message], [], new JsonObject { ["calculated"] = false });
    }
}
