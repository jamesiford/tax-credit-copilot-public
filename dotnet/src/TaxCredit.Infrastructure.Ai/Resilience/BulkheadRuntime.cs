using System.Runtime.CompilerServices;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Runtime;

namespace TaxCredit.Infrastructure.Ai.Resilience;

/// <summary>Refuses excess concurrent calls without queuing or penalizing provider health.</summary>
public sealed class BulkheadRuntime(IAgentRuntime inner, int limit, IAiTelemetry? telemetry = null) : RuntimeDecorator(inner), IDisposable
{
    private readonly SemaphoreSlim _slots = new(limit, limit);
    /// <summary>Currently admitted streams, released on cancellation or disposal.</summary>
    public int Active => limit - _slots.CurrentCount;
    /// <summary>Disposes concurrency state once all streams have been disposed.</summary>
    public void Dispose() => _slots.Dispose();
    /// <inheritdoc/>
    public override async IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (!await _slots.WaitAsync(0, cancellationToken).ConfigureAwait(false))
        {
            telemetry?.Count("ai.bulkhead_rejections", provider: Name);
            throw new ModelException(ModelErrorKind.BulkheadFull, "bulkhead_full");
        }
        try
        {
            await foreach (var item in Inner.StreamAsync(request, cancellationToken).ConfigureAwait(false))
            {
                yield return item;
            }
        }
        finally { _slots.Release(); }
    }
}
