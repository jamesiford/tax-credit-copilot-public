using System.Text.Json.Nodes;

namespace TaxCredit.Orchestrator.Boundary;

/// <summary>The only outbound tool/audit boundary carries a verified person per invocation.</summary>
public interface IGatewayClient
{
    /// <summary>Call a tool without retrying mutations or exposing confirmation tokens to a model.</summary>
    Task<GatewayReply> CallToolAsync(ActingIdentity identity, string tool, JsonObject arguments,
        string? idempotencyKey = null, string? confirmationToken = null, CancellationToken cancellationToken = default);

    /// <summary>Attribute narration audit to the same person, conversation and correlation as its tools.</summary>
    Task<GatewayReply> ReportNarrationAsync(ActingIdentity identity, JsonObject report, CancellationToken cancellationToken = default);
}
