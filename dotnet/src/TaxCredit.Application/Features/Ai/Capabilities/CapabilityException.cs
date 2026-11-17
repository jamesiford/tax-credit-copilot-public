using System.Text.Json.Nodes;

namespace TaxCredit.Application.Features.Ai.Capabilities;

/// <summary>Safe transport-independent refusal; unknown exception messages never cross this boundary.</summary>
public sealed class CapabilityException(int statusCode, string code, string message, bool retryable = false,
    JsonObject? extra = null, Exception? innerException = null) : Exception(message, innerException)
{
    /// <summary>HTTP status without a dependency on an HTTP framework.</summary>
    public int StatusCode { get; } = statusCode;
    /// <summary>Stable machine-readable category.</summary>
    public string Code { get; } = code;
    /// <summary>Whether a later identical request may succeed.</summary>
    public bool Retryable { get; } = retryable;
    /// <summary>The capability error envelope, distinct from request-binding detail arrays.</summary>
    public JsonObject Detail => Body();

    /// <summary>Only controlled text and caller-actionable metadata cross the boundary.</summary>
    public JsonObject Body()
    {
        var error = new JsonObject { ["code"] = Code, ["message"] = Message, ["retryable"] = Retryable };
        foreach (var entry in extra ?? [])
        {
            error[entry.Key] = entry.Value?.DeepClone();
        }
        return new JsonObject { ["error"] = error };
    }

    /// <summary>A schema refusal never dispatches a tool.</summary>
    public static CapabilityException Invalid(string message) => new(422, "invalid_arguments", message);
    /// <summary>Names a concrete production integration gap instead of answering from a fixture.</summary>
    public static CapabilityException Missing(string owner, string service) => new(503, "dependency_unavailable",
        "The application service required by this capability is unavailable.", extra: new JsonObject
        {
            ["dependency"] = service,
            ["owner"] = owner,
        });
}
