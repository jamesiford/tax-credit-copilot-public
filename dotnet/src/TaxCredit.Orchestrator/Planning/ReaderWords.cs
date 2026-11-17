using System.Globalization;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace TaxCredit.Orchestrator.Planning;

/// <summary>Reader-owned arguments are settled before schema validation, never guessed by a model.</summary>
public static partial class ReaderWords
{
    private static readonly string[] NumberWords =
        ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];

    /// <summary>Out-of-range historical dates are not statutory tax years.</summary>
    public static IReadOnlyList<int> Years(string text) => YearPattern().Matches(text)
        .Select(match => int.Parse(match.Groups[1].Value, CultureInfo.InvariantCulture)).Distinct().ToArray();

    /// <summary>Only reader-supplied scenario values may enter a what-if.</summary>
    public static IReadOnlySet<double> Numbers(string text)
    {
        var result = NumberPattern().Matches(text).Select(match => double.Parse(match.Value, CultureInfo.InvariantCulture)).ToHashSet();
        for (var index = 0; index < NumberWords.Length; index++)
        {
            if (Regex.IsMatch(text, $@"\b{NumberWords[index]}\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant,
                TimeSpan.FromSeconds(1)))
            {
                result.Add(index + 1);
            }
        }
        return result;
    }

    /// <summary>Returns the clarification kind, leaving only safe settled arguments behind.</summary>
    public static string? Settle(JsonObject spec, JsonObject arguments, string question, int? conversationYear)
    {
        var schema = spec["schema"]!.AsObject();
        var properties = schema["properties"]!.AsObject();
        var explicitYear = spec["kind"]!.GetValue<string>() == "write_prepare";
        var said = Years(question);
        foreach (var key in properties.Select(pair => pair.Key).Where(key => key is "year" or "tax_year" or "base_year"))
        {
            var prior = explicitYear || key == "base_year" ? null : conversationYear;
            var proposed = Integer(arguments[key]);
            var chosen = proposed is { } value && (said.Contains(value) || prior == value) ? proposed :
                said.Count == 1 ? said[0] : prior;
            arguments.Remove(key);
            if (chosen is { } year) { arguments[key] = year; }
            else if (spec["needs_year"]!.GetValue<bool>() || schema["required"]!.AsArray().Any(node => node?.ToString() == key))
            {
                return "year";
            }
        }
        if (properties.ContainsKey("tax_years")) { SettleYears(arguments, said, conversationYear); }
        if (spec["name"]!.GetValue<string>() == "client_eligibility")
        {
            var pay = PayPeriodPattern().IsMatch(question);
            var min = MinMaxPattern().IsMatch(question);
            arguments["method"] = pay && !min ? "pay_period" : min && !pay ? "min_max" : "both";
        }
        else if (properties.ContainsKey("method") && arguments["method"] is { } method &&
            (method is not JsonValue scalar || !scalar.TryGetValue<string>(out _)))
        {
            arguments.Remove("method");
        }
        foreach (var key in new[] { "magnitude", "hire_weekly_hours", "hire_hourly_rate" })
        {
            if (arguments[key] is { } node &&
                (!double.TryParse(node.ToJsonString(), NumberStyles.Float, CultureInfo.InvariantCulture, out var value) ||
                 !Numbers(question).Contains(value)))
            {
                arguments.Remove(key);
            }
        }
        return properties.ContainsKey("magnitude") && !arguments.ContainsKey("magnitude") ? "detail" : null;
    }

    private static void SettleYears(JsonObject arguments, IReadOnlyList<int> said, int? prior)
    {
        var proposed = arguments["tax_years"];
        arguments.Remove("tax_years");
        bool Allowed(JsonNode? node) => Integer(node) is { } year && (said.Contains(year) || prior == year);
        if (proposed is JsonObject range && Allowed(range["from"]) && Allowed(range["to"]))
        {
            arguments["tax_years"] = range.DeepClone();
            return;
        }
        var kept = proposed is JsonArray list ? list.Where(Allowed).Select(node => Integer(node)!.Value).ToArray() : [];
        if (kept.Length != 0 || said.Count != 0)
        {
            arguments["tax_years"] = new JsonArray((kept.Length != 0 ? kept : said)
                .Select(year => (JsonNode?)JsonValue.Create(year)).ToArray());
        }
    }

    internal static int? Integer(JsonNode? node) => node is JsonValue value &&
        value.TryGetValue<System.Text.Json.JsonElement>(out var element) &&
        element.ValueKind == System.Text.Json.JsonValueKind.Number && element.TryGetInt32(out var number) ? number :
        node is JsonValue scalar && scalar.TryGetValue<int>(out var direct) ? direct : null;

    [GeneratedRegex(@"\b(?:ty\s?)?((?:19|20)\d\d)\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex YearPattern();
    [GeneratedRegex(@"(?<![\w.\-])\d+(?:\.\d+)?(?![\w])", RegexOptions.CultureInvariant)]
    private static partial Regex NumberPattern();
    [GeneratedRegex(@"pay[\s-]?period", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex PayPeriodPattern();
    [GeneratedRegex(@"min[\s-]?max", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex MinMaxPattern();
}
