using System.Runtime.CompilerServices;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Runtime;

namespace TaxCredit.Infrastructure.Ai.Resilience;

/// <summary>Times out silence rather than healthy long-running streams.</summary>
public sealed class TimeoutRuntime(IAgentRuntime inner, TimeSpan gap, TimeProvider? clock = null) : RuntimeDecorator(inner)
{
    /// <inheritdoc/>
    public override async IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        using var stop = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        await using var events = Inner.StreamAsync(request, stop.Token).GetAsyncEnumerator(stop.Token);
        while (await MoveAsync(events, stop, cancellationToken).ConfigureAwait(false))
        {
            yield return events.Current;
        }
    }
    private async Task<bool> MoveAsync(IAsyncEnumerator<ModelEvent> events, CancellationTokenSource stop, CancellationToken ct)
    {
        var pending = events.MoveNextAsync().AsTask();
        try { return await pending.WaitAsync(gap, clock ?? TimeProvider.System, ct).ConfigureAwait(false); }
        catch (TimeoutException)
        {
            stop.Cancel();
            try { await pending.ConfigureAwait(false); } catch (Exception) { }
            throw new ModelException(ModelErrorKind.Timeout, "event_gap_timeout");
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            stop.Cancel();
            try { await pending.ConfigureAwait(false); } catch (Exception) { }
            throw;
        }
    }
}
