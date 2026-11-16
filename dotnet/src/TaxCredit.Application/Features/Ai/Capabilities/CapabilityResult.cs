using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Numeric;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.Ai.Capabilities;

/// <summary>Exact producer facts and separately rendered blocks preserve the model/person lane boundary.</summary>
public sealed record CapabilityResult(string Tool, JsonObject Facts)
{
    /// <summary>Standing disclosure is not supplied by a narrator.</summary>
    public const string Disclaimer = "Not tax advice: these figures are computed from payroll by this software and must be reviewed by a qualified tax professional before any filing or claim.";
    /// <summary>Only these blocks can be composed into a channel response.</summary>
    public JsonArray Blocks { get; init; } = [];
    /// <summary>Missing evidence is null, not an invented run.</summary>
    public JsonObject Provenance { get; init; } = Evidence();
    /// <summary>Disclosures that cannot be hidden by choosing a prose renderer.</summary>
    public IReadOnlyList<string> Warnings { get; init; } = [];
    /// <summary>Top-level fact keys withheld from model context.</summary>
    public IReadOnlyList<string> UserOnlyFacts { get; init; } = [];

    /// <summary>The person gets the full result; a narrator must use ModelFacts instead.</summary>
    public JsonObject ToJson()
    {
        if (UserOnlyFacts.Any(key => !Facts.ContainsKey(key)))
        {
            throw new InvalidOperationException("A user-only fact key is absent.");
        }
        var wire = new JsonObject
        {
            ["tool"] = Tool,
            ["facts"] = Facts.DeepClone(),
            ["blocks"] = Blocks.DeepClone(),
            ["provenance"] = Provenance.DeepClone(),
            ["warnings"] = Strings(Warnings),
            ["disclaimer"] = Disclaimer,
        };
        if (UserOnlyFacts.Count != 0)
        {
            wire["user_only_facts"] = Strings(UserOnlyFacts.Order(StringComparer.Ordinal));
        }
        return wire;
    }

    /// <summary>Employee-derived values never become narration context.</summary>
    public JsonObject ModelFacts() => new(Facts.Where(pair => !UserOnlyFacts.Contains(pair.Key, StringComparer.Ordinal))
        .Select(pair => KeyValuePair.Create(pair.Key, pair.Value?.DeepClone())));

    /// <summary>Unknown audiences are person-only rather than an implicit grant.</summary>
    public bool HasUserLane => UserOnlyFacts.Count != 0 ||
        Blocks.OfType<JsonObject>().Any(block => block["audience"] is { } audience && audience.GetValue<string>() != "both");

    /// <summary>Every evidence field is present even for claims-only reads.</summary>
    public static JsonObject Evidence(string? runId = null, string? rulePackVersion = null,
        string? assumptionSetId = null, string? trailSha256 = null, string? source = null) => new()
        {
            ["run_id"] = runId,
            ["rule_pack_version"] = rulePackVersion,
            ["assumption_set_id"] = assumptionSetId,
            ["trail_sha256"] = trailSha256,
            ["source"] = source,
        };

    /// <summary>Stable block grammar refuses ragged tables and multi-cell bullets.</summary>
    public static JsonObject Block(string kind, string text = "", IEnumerable<IEnumerable<string>>? rows = null,
        string audience = "both")
    {
        var matrix = (rows ?? []).Select(row => row.ToArray()).ToArray();
        if (kind is not ("heading" or "paragraph" or "bullets" or "table" or "callout") ||
            audience is not ("both" or "user") ||
            kind == "table" && matrix.Select(row => row.Length).Distinct().Count() > 1 ||
            kind == "bullets" && matrix.Any(row => row.Length != 1))
        {
            throw new ArgumentException("Invalid capability block.");
        }
        var block = new JsonObject
        {
            ["kind"] = kind,
            ["text"] = text,
            ["rows"] = new JsonArray(matrix.Select(row => (JsonNode)Strings(row)).ToArray()),
        };
        if (audience != "both")
        {
            block["audience"] = audience;
        }
        return block;
    }

    internal static JsonArray Strings(IEnumerable<string> values) => new(values.Select(value => (JsonNode?)JsonValue.Create(value)).ToArray());
    internal static JsonObject Object(object value) => value is IReadOnlyDictionary<string, object?> dictionary
        ? JsonSerializer.SerializeToNode(dictionary)!.AsObject()
        : JsonNode.Parse(PyJson.Dumps(value))!.AsObject();
}

/// <summary>Canonical capability text shares the numeral guard's exact, non-rounding formatter.</summary>
public static class CapabilityFormat
{
    /// <summary>Absence is a dash; numeric values are never rounded for display.</summary>
    public static string Render(JsonNode? value, string formatter = "number")
    {
        if (value is null)
        {
            return "—";
        }
        var text = value.GetValueKind() == JsonValueKind.String ? value.GetValue<string>() : value.ToJsonString();
        return NumericFormatting.Format(text, formatter);
    }
}
