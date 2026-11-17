namespace TaxCredit.Application.Hosting;

/// <summary>Replay requests, reset, drain and the local worker exclude one another; database leases still arbitrate processes.</summary>
public sealed class RunWorkGate : IDisposable
{
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly Queue<Func<CancellationToken, ValueTask>> _deferred = new();

    /// <summary>Hosts hold the returned lease over the complete reset/drain or request lifetime.</summary>
    public async ValueTask<IDisposable> Enter(CancellationToken cancellationToken)
    {
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        return new Lease(_gate);
    }

    /// <summary>Future handlers schedule recalculation without depending on an HTTP completion callback.</summary>
    public void Defer(Func<CancellationToken, ValueTask> work)
    {
        ArgumentNullException.ThrowIfNull(work);
        lock (_deferred) { _deferred.Enqueue(work); }
    }

    /// <summary>Replay calls this after sending the response and before admitting the next request.</summary>
    public async ValueTask CompleteDeferred(CancellationToken cancellationToken)
    {
        while (true)
        {
            Func<CancellationToken, ValueTask>? work;
            lock (_deferred) { work = _deferred.Count == 0 ? null : _deferred.Dequeue(); }
            if (work is null) { return; }
            await work(cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>A scenario reset invalidates work scheduled in its predecessor.</summary>
    public void Reset()
    {
        lock (_deferred) { _deferred.Clear(); }
    }
    /// <inheritdoc />
    public void Dispose() => _gate.Dispose();

    private sealed class Lease(SemaphoreSlim semaphore) : IDisposable
    {
        private bool _disposed;
        public void Dispose()
        {
            if (_disposed) { return; }
            _disposed = true;
            semaphore.Release();
        }
    }
}
