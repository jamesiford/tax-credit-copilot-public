using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Runtime;

/// <summary>Preserves configuration readiness and version while adding one runtime concern.</summary>
public abstract class RuntimeDecorator(IAgentRuntime inner) : IAgentRuntime
{
    /// <summary>The wrapped runtime, exposed for composition diagnostics.</summary>
    public IAgentRuntime Inner { get; } = inner;
    /// <inheritdoc/>
    public string Name => Inner.Name;
    /// <inheritdoc/>
    public bool ReadyFor(string agentName) => Inner.ReadyFor(agentName);
    /// <inheritdoc/>
    public string? VersionOf(string agentName) => Inner.VersionOf(agentName);
    /// <inheritdoc/>
    public virtual ProviderStatus Status() => Inner.Status();
    /// <inheritdoc/>
    public abstract IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request, CancellationToken cancellationToken = default);
}
