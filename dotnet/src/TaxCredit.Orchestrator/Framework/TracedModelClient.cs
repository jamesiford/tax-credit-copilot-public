using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.AI;
using TaxCredit.Orchestrator.Planning;

namespace TaxCredit.Orchestrator.Framework;

/// <summary>Every planner records actual model requests as digests, never retained prompts or rejected prose.</summary>
internal sealed class TracedModelClient(IChatClient inner, PlannedTurn turn) : DelegatingChatClient(inner)
{
    public override async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var snapshot = messages.ToArray();
        var previous = turn.PromptSha256 ?? "";
        var payload = ModelRequestText.Build(snapshot, options);
        turn.PromptSha256 = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(previous + "\n" + payload)));
        turn.ModelCalled = true;
        var response = await base.GetResponseAsync(snapshot, options, cancellationToken).ConfigureAwait(false);
        turn.Model = response.ModelId;
        return response;
    }

    [System.Diagnostics.CodeAnalysis.SuppressMessage("Usage", "CA2215",
        Justification = "The process owns the provider client; per-turn trace disposal must not dispose it.")]
    protected override void Dispose(bool disposing) { }
}
