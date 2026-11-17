using System.Text.Json.Nodes;

namespace TaxCredit.Application.Features.Ai.Capabilities;

/// <summary>The declared vocabulary is stable even when a tool is not offered to a model.</summary>
public sealed class CapabilityCatalog
{
    private static readonly string[] ModelExcludedTags = ["internal", "gateway-local", "code-only", "debug"];
    private readonly JsonObject[] _specifications;

    /// <summary>Uses the complete vendored Python catalogue rather than a recording's subset.</summary>
    public CapabilityCatalog() : this((JsonNode.Parse(CapabilityCatalogData.Json) as JsonArray)!
        .Select(node => (JsonObject)node!))
    {
    }

    /// <summary>Clones declarations so external mutation cannot change the invocation policy.</summary>
    public CapabilityCatalog(IEnumerable<JsonObject> specifications)
    {
        _specifications = specifications.Select(spec => (JsonObject)spec.DeepClone()).ToArray();
        if (_specifications.Select(spec => spec["name"]!.GetValue<string>()).Distinct(StringComparer.Ordinal).Count() != _specifications.Length)
        {
            throw new ArgumentException("Duplicate capability name.", nameof(specifications));
        }
    }

    /// <summary>Internal plumbing is not a caller-facing declaration.</summary>
    public JsonObject List() => new() { ["tools"] = Copy(_specifications.Where(spec => !Tagged(spec, "internal"))) };
    /// <summary>All declarations, including internal and unbuilt entries.</summary>
    public JsonArray Declared() => Copy(_specifications);
    /// <summary>Only built, non-internal tools may be offered to callers.</summary>
    public JsonArray Offered() => Copy(_specifications.Where(spec => Built(spec) && !Tagged(spec, "internal")));
    /// <summary>A model may never select commits, gateway plumbing or code-only operations.</summary>
    public JsonArray ModelOffered() => Copy(_specifications.Where(spec => Built(spec) &&
        spec["kind"]!.GetValue<string>() != "write_commit" &&
        !ModelExcludedTags.Any(tag => Tagged(spec, tag))));

    /// <summary>Debug tools stay unknown at the API boundary, regardless of gateway switches.</summary>
    public JsonObject Resolve(string name)
    {
        var spec = _specifications.FirstOrDefault(spec => spec["name"]!.GetValue<string>() == name)
            ?? throw new CapabilityException(404, "unknown_tool", $"no such tool: {name}");
        if (!Built(spec))
        {
            throw new CapabilityException(501, "not_implemented", $"{name} is declared but not built yet");
        }
        if (Tagged(spec, "gateway-local"))
        {
            throw new CapabilityException(501, "gateway_local", $"{name} is answered by the channel gateway, which holds the conversation");
        }
        return (JsonObject)spec.DeepClone();
    }

    private static bool Built(JsonObject spec) => spec["implemented"]?.GetValue<bool>() == true;
    private static bool Tagged(JsonObject spec, string tag) =>
        spec["tags"]!.AsArray().Any(node => node!.GetValue<string>() == tag);
    private static JsonArray Copy(IEnumerable<JsonObject> specs) =>
        new(specs.Select(spec => spec.DeepClone()).ToArray());
}
