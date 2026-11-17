using System.Text.Json;
using TaxCredit.Application.Features.Ai.Streams;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Runtime;

namespace TaxCredit.Infrastructure.Ai.Agents;

/// <summary>Uses the validated roster without replacing W1's root-owned definitions or provider graph.</summary>
public sealed class AgentNarrator(AgentRoster roster, ModelRouter router) : IAiNarrator
{
    private readonly NarrationService _narration = new(roster.Specs, router);

    /// <inheritdoc/>
    public bool Available(IEnumerable<string> agents) => _narration.Available(agents);

    /// <inheritdoc/>
    public IAsyncEnumerable<ModelEvent> StreamAsync(string agent, string prompt, string principal,
        JsonElement trustedFacts, CancellationToken cancellationToken = default) =>
        _narration.StreamAsync(agent, prompt, principal, trustedFacts, cancellationToken);
}
