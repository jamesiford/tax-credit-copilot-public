using System.Runtime.CompilerServices;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Runtime;

/// <summary>Agents cannot execute or offer tools; a bare chat model still exposes tool events to its caller.</summary>
public sealed class ChatModelAgentRuntime(IChatModel model, Func<ModelRole, string> modelForRole,
    string? providerName = null) : IAgentRuntime
{
    /// <inheritdoc/>
    public string Name => providerName ?? model.Name;
    /// <inheritdoc/>
    public bool ReadyFor(string agentName) => model.Status().State != ProviderState.Disabled;
    /// <inheritdoc/>
    public string? VersionOf(string agentName) => null;
    /// <inheritdoc/>
    public ProviderStatus Status() => model.Status() with { Name = Name };
    /// <inheritdoc/>
    public async IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        string selected = modelForRole(request.Spec.Role);
        double? temperature = selected.Trim().StartsWith("gpt-5", StringComparison.OrdinalIgnoreCase) ? null : request.Spec.Temperature;
        var chat = new ChatRequest(selected,
            [new ChatMessage("system", request.Spec.Instructions), new ChatMessage("user", request.Prompt)], temperature);
        await foreach (var item in model.StreamAsync(chat, cancellationToken).ConfigureAwait(false))
        {
            if (item is ToolCall)
            {
                continue;
            }

            yield return item is StreamEnd end ? end with { Provider = Name, AgentVersion = request.Spec.Version } : item;
            if (item is StreamEnd)
            {
                yield break;
            }
        }
    }
}
