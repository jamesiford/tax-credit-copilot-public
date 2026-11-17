using System.Runtime.CompilerServices;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Runtime;

/// <summary>Tries configured providers before output; never splices two providers' answers.</summary>
public sealed class ProviderChain(IReadOnlyList<IAgentRuntime> providers) : IAgentRuntime
{
    /// <inheritdoc/>
    public string Name => "chain";
    /// <inheritdoc/>
    public bool ReadyFor(string agentName) => providers.Any(p => p.ReadyFor(agentName));
    /// <inheritdoc/>
    public string? VersionOf(string agentName) => providers.Select(p => p.VersionOf(agentName)).FirstOrDefault(v => v is not null);
    /// <inheritdoc/>
    public ProviderStatus Status() => new(Name, providers.Any(p => p.Status().State == ProviderState.Ready)
        ? ProviderState.Ready : ProviderState.Unavailable);
    /// <inheritdoc/>
    public async IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var hops = new List<string>();
        foreach (var provider in providers)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (!provider.ReadyFor(request.Spec.Name))
            {
                continue;
            }

            hops.Add(provider.Name);
            bool produced = false;
            StreamEnd? end = null;
            await using var events = provider.StreamAsync(request, cancellationToken).GetAsyncEnumerator(cancellationToken);
            bool failed = false;
            while (true)
            {
                var (Moved, Failed) = await NextAsync(events, produced).ConfigureAwait(false);
                failed = Failed;
                if (!Moved)
                {
                    break;
                }

                if (events.Current is StreamEnd terminal) { end = terminal; continue; }
                produced |= events.Current is TextDelta { Text.Length: > 0 } or ToolCall;
                yield return events.Current;
            }
            if (failed)
            {
                continue;
            }

            yield return new StreamEnd(provider.Name, end?.Model, end?.AgentVersion ?? provider.VersionOf(request.Spec.Name),
                [.. hops], end?.FinishReason);
            yield break;
        }
        throw new ModelException(ModelErrorKind.NarrationUnavailable, "no_provider_answered", hops: [.. hops]);
    }
    private static async Task<(bool Moved, bool Failed)> NextAsync(IAsyncEnumerator<ModelEvent> events, bool produced)
    {
        try { return (await events.MoveNextAsync().ConfigureAwait(false), false); }
        catch (ModelException error) when (!produced && error.Kind is not (ModelErrorKind.BudgetExceeded or ModelErrorKind.InjectionBlocked))
        { return (false, true); }
    }
}
