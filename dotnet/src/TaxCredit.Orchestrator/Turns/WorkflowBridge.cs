using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Orchestrator.Boundary;
using TaxCredit.Orchestrator.Framework;
using TaxCredit.Orchestrator.Workflow;

namespace TaxCredit.Orchestrator.Turns;

/// <summary>Resumed SDK executors use the current verified invocation, never an identity captured at prepare.</summary>
public sealed class WorkflowBridge
{
    private readonly AsyncLocal<ActingIdentity?> _identity = new();
    private readonly WriteWorkflow _workflow;
    /// <summary>Attribution is invocation-local even though SDK definitions and workflow services are shared.</summary>
    public ActingIdentity? CurrentIdentity => _identity.Value;

    /// <summary>The catalogue supplies the prepare allowlist; commits remain unreachable from model tools.</summary>
    public WorkflowBridge(IGatewayClient gateway, ModelToolCatalog catalog, TimeProvider? clock = null,
        TimeSpan? confirmationLifetime = null)
    {
        _workflow = new WriteWorkflow(async (owner, request, ct) =>
        {
            var identity = _identity.Value ?? throw new InvalidOperationException("No verified workflow invocation.");
            if (Owner(identity) != owner) { throw new InvalidOperationException("Workflow identity mismatch."); }
            var reply = await gateway.CallToolAsync(identity, request.Tool,
                JsonNode.Parse(request.Arguments.GetRawText())!.AsObject(), request.IdempotencyKey,
                request.ConfirmationToken, ct).ConfigureAwait(false);
            return new WriteGatewayReply(reply.Status, JsonSerializer.SerializeToElement(reply.Body));
        }, catalog.Definitions.Select(tool => tool.Name).Where(name => catalog.Find(name)?["kind"]?.ToString() == "write_prepare"),
            clock: clock, confirmationLifetime: confirmationLifetime ?? TimeSpan.FromMinutes(5));
    }

    /// <summary>ExecutionContext carries attribution across the actual framework run/resume calls.</summary>
    public async Task<T> AsAsync<T>(ActingIdentity identity, Func<Task<T>> action)
    {
        var saved = _identity.Value;
        _identity.Value = identity;
        try { return await action().ConfigureAwait(false); }
        finally { _identity.Value = saved; }
    }

    /// <summary>Only the platform's exact confirmation grammar can reach the resume port.</summary>
    public Task<WriteResult> RespondAsync(ActingIdentity identity, string text, CancellationToken cancellationToken) =>
        _workflow.RespondAsync(Owner(identity), Replies.Command(text) is null ? "__new_request__" : text, cancellationToken);

    /// <summary>The prepare response has already lost its confirmation secret before it reaches composition.</summary>
    public async Task<GatewayReply> PrepareAsync(ActingIdentity identity, string name, JsonObject arguments,
        CancellationToken cancellationToken)
    {
        var result = await _workflow.PrepareAsync(Owner(identity),
            new WritePrepareRequest(name, JsonSerializer.SerializeToElement(arguments)), cancellationToken).ConfigureAwait(false);
        var reply = Reply(result);
        return result.Status == WriteStatus.Waiting || !reply.Ok ? reply :
            GatewayReply.Failure(result.Code, "The preview could not be made confirmable.");
    }

    internal static GatewayReply Reply(WriteResult result) => result.Reply is { } reply
        ? new GatewayReply(reply.StatusCode, JsonNode.Parse(reply.Body.GetRawText())!.AsObject())
        : GatewayReply.Failure(result.Code, "The change workflow did not complete.");

    private static WriteOwner Owner(ActingIdentity identity) =>
        new(identity.TenantId + ":" + identity.Oid, identity.ConversationId);
}
