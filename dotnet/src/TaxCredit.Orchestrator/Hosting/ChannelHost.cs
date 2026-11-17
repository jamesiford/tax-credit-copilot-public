using TaxCredit.Orchestrator.Boundary;
using TaxCredit.Orchestrator.Turns;

namespace TaxCredit.Orchestrator.Hosting;

/// <summary>Platform signals are normalized outside deterministic turns; diagnostics remain text-only and opt-in.</summary>
public sealed class ChannelHost(IdentityOptions identityOptions, TurnPipeline pipeline, ConversationStore store,
    DebugCommandHandler debug, IReadOnlyList<string>? providers = null, bool modelConfigured = false,
    bool toolsAvailable = false) : IResponseTurn
{
    /// <inheritdoc/>
    public Task<string> AnswerAsync(ResponseTurnRequest request, CancellationToken cancellationToken) =>
        AnswerAsync(request.Text, new IdentityContext(request.Headers, AgentUserId: request.AgentUserId,
            ConversationId: request.ConversationId, ConversationChainId: request.ConversationChainId,
            ResponseId: request.ResponseId), cancellationToken);

    /// <summary>Used by the SDK seam and deterministic platform-context contract tests alike.</summary>
    public async Task<string> AnswerAsync(string text, IdentityContext context, CancellationToken cancellationToken = default)
    {
        var diagnostic = await debug.TryHandleAsync(text, context,
            new DebugRuntimeState(providers, toolsAvailable, modelConfigured, pipeline.AuditFailures,
                store.Count, pipeline.LastAuditError), cancellationToken).ConfigureAwait(false);
        if (diagnostic is not null) { return diagnostic; }
        var resolved = IdentityResolver.Resolve(context, identityOptions);
        return (await pipeline.HandleAsync(text, resolved.Identity, cancellationToken).ConfigureAwait(false)).Text;
    }
}
