using System.Text.Json;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Application.Features.Ai.Streams;

/// <summary>Feature-owned narration uses the guarded W1 provider chain, never an SDK.</summary>
public interface IAiNarrator
{
    /// <summary>All named agents must be usable before model narration is offered.</summary>
    bool Available(IEnumerable<string> agents);

    /// <summary>Trusted facts are separate from reader-authored text and never contain employee rows.</summary>
    IAsyncEnumerable<ModelEvent> StreamAsync(string agent, string prompt, string principal,
        JsonElement trustedFacts, CancellationToken cancellationToken = default);
}
