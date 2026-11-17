using System.Globalization;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;

namespace TaxCredit.Orchestrator.Boundary;

/// <summary>The complete envelope remains available; projection belongs at the model boundary.</summary>
public sealed record GatewayReply(int Status, JsonObject Body)
{
    /// <summary>A dependency failure or gateway error never becomes an empty successful answer.</summary>
    public bool Ok => Status == 200 && !Body.ContainsKey("error");
    /// <summary>Stable gateway error codes survive the REST boundary.</summary>
    public string ErrorCode => ReadText(Body["error"] as JsonObject, "code") ??
        (Ok ? "ok" : "http_" + Status.ToString(CultureInfo.InvariantCulture));
    /// <summary>Structured upstream messages are retained; transport exception details are never inserted.</summary>
    public string ErrorMessage => ReadText(Body["error"] as JsonObject, "message") ?? "";

    /// <summary>Convert only valid capability envelopes, preserving person lanes and cloning mutable JSON.</summary>
    public CapabilityResult? ToCapabilityResult(string tool)
    {
        if (!Ok || Body["facts"] is not JsonObject facts ||
            Body["blocks"] is not (null or JsonArray) || Body["provenance"] is not (null or JsonObject))
        {
            return null;
        }
        var warnings = ReadStrings(Body["warnings"]);
        var userOnly = ReadStrings(Body["user_only_facts"]);
        if (warnings is null || userOnly is null || userOnly.Any(key => !facts.ContainsKey(key)))
        {
            return null;
        }
        return new CapabilityResult(ReadText(Body, "tool") ?? tool, (JsonObject)facts.DeepClone())
        {
            Blocks = Body["blocks"] is JsonArray blocks ? (JsonArray)blocks.DeepClone() : [],
            Provenance = Body["provenance"] is JsonObject provenance ? (JsonObject)provenance.DeepClone() : CapabilityResult.Evidence(),
            Warnings = warnings,
            UserOnlyFacts = userOnly,
        };
    }

    internal static GatewayReply Failure(string code, string message = "the channel gateway did not answer", int status = 0) =>
        new(status, new JsonObject { ["error"] = new JsonObject { ["code"] = code, ["message"] = message, ["retryable"] = status == 0 } });

    private static string? ReadText(JsonObject? value, string key) =>
        value?[key] is JsonValue field && field.TryGetValue<string>(out var text) ? text : null;

    private static string[]? ReadStrings(JsonNode? value)
    {
        if (value is null)
        {
            return [];
        }
        if (value is not JsonArray array || array.Any(node => node is not JsonValue field || !field.TryGetValue<string>(out _)))
        {
            return null;
        }
        return array.Select(node => node!.GetValue<string>()).ToArray();
    }
}
