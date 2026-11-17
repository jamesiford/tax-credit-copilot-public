using System.Runtime.CompilerServices;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Runtime;

/// <summary>Foundry publishing/invocation belongs to the root and later waves; this seam injects that transport safely.</summary>
public sealed class InjectedProviderRuntime(string name, Func<string, bool> ready,
    Func<NarrationRequest, CancellationToken, IAsyncEnumerable<ModelEvent>> stream,
    Func<string, string?>? version = null, Func<ProviderStatus>? status = null) : IAgentRuntime
{
    /// <inheritdoc/>
    public string Name => name;
    /// <inheritdoc/>
    public bool ReadyFor(string agentName) => ready(agentName);
    /// <inheritdoc/>
    public string? VersionOf(string agentName) => version?.Invoke(agentName);
    /// <inheritdoc/>
    public ProviderStatus Status() => status?.Invoke() ?? new(Name, ProviderState.Ready);
    /// <inheritdoc/>
    public async IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await using var events = Open(request, cancellationToken);
        while (await NextAsync(events, cancellationToken).ConfigureAwait(false))
        {
            yield return events.Current;
        }
    }
    private IAsyncEnumerator<ModelEvent> Open(NarrationRequest request, CancellationToken ct)
    {
        try { return stream(request, ct).GetAsyncEnumerator(ct); }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
        catch (ModelException) { throw; }
        catch (Exception) { throw new ModelException(ModelErrorKind.Unavailable, "provider_transport_failed"); }
    }
    private static async Task<bool> NextAsync(IAsyncEnumerator<ModelEvent> events, CancellationToken ct)
    {
        try { return await events.MoveNextAsync().ConfigureAwait(false); }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
        catch (ModelException) { throw; }
        catch (Exception) { throw new ModelException(ModelErrorKind.Unavailable, "provider_transport_failed"); }
    }
}
