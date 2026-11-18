using System.Runtime.ExceptionServices;
using TaxCredit.Infrastructure.Sources.Projection;

namespace TaxCredit.Infrastructure.Sources.Cache;

/// <summary>One cached client: the account and everything that, when changed, makes a held projection a different projection.</summary>
/// <param name="AccountId">The client.</param>
/// <param name="Identity">Process-constant projection settings (mapping transforms, pay-code policy and seed).</param>
public readonly record struct ProjectionKey(long AccountId, string Identity);

/// <summary>
/// A bounded, thread-safe LRU of finished <see cref="PayrollProjection"/>s, one per client, shared by every request.
/// </summary>
/// <remarks>
/// <para>An entry is trusted for <see cref="ProjectionCacheOptions.VersionCheck"/> after its stamp was last taken and matched. Past
/// that, or whenever the caller says <c>revalidate</c> (a calculation run), a fresh stamp is taken and compared; a mismatch drops the entry
/// and reads again. The stamp is taken <em>before</em> the rows are read, so a change racing a read costs one extra read, never a missed one.</para>
/// <para><b>What a stamp cannot see</b> is the stamp's own limitation (count/max-preserving updates, non-Payroll tables, sync lag), listed on
/// <c>SourceFingerprint.Limitations</c>. This class decides nothing about it; it only compares what it is given.</para>
/// <para>Loads are single-flight per client. A failed load, or a client over the row cap, caches nothing and is shared with the waiters that
/// joined it rather than retried by each.</para>
/// </remarks>
public sealed class ClientProjectionCache : IDisposable
{
    private readonly ProjectionCacheOptions _options;
    private readonly TimeProvider _clock;
    private readonly object _gate = new();
    private readonly Dictionary<ProjectionKey, LinkedListNode<Entry>> _entries = [];
    private readonly LinkedList<Entry> _recent = new();
    private readonly Dictionary<ProjectionKey, Flight> _flights = [];
    private long _bytes;
    private long _joins;

    /// <summary>Creates an empty cache. <paramref name="stampsMatch"/> is a test seam for the invalidation rule and defaults to equality.</summary>
    public ClientProjectionCache(ProjectionCacheOptions options, TimeProvider? clock = null,
        Func<string, string, bool>? stampsMatch = null)
    {
        ArgumentNullException.ThrowIfNull(options);
        _options = options;
        _clock = clock ?? TimeProvider.System;
        StampsMatch = stampsMatch ?? ((held, taken) => string.Equals(held, taken, StringComparison.Ordinal));
        Metrics = new ProjectionCacheMetrics(() => Count, () => EstimatedBytes);
    }

    /// <summary>Hits, misses, evictions and gauges.</summary>
    public ProjectionCacheMetrics Metrics { get; }
    private Func<string, string, bool> StampsMatch { get; }
    /// <summary>Callers that have joined an in-flight load so far; lets a test wait for a join instead of sleeping.</summary>
    internal long Joins => Interlocked.Read(ref _joins);

    /// <summary>Clients currently held.</summary>
    public int Count { get { lock (_gate) { return _entries.Count; } } }
    /// <summary>Estimated bytes currently held.</summary>
    public long EstimatedBytes { get { lock (_gate) { return _bytes; } } }

    /// <summary>Drops every entry. Loads already in flight finish, and store their result.</summary>
    public void Clear()
    {
        lock (_gate)
        {
            _entries.Clear();
            _recent.Clear();
            _bytes = 0;
        }
    }

    /// <summary>
    /// Returns the held projection when it may be trusted, otherwise reads it. <paramref name="takeStamp"/> must read the source afresh;
    /// <paramref name="load"/> must read the rows and may return <c>null</c> for an unknown client, which is not cached.
    /// </summary>
    /// <param name="key">The client and projection identity.</param>
    /// <param name="revalidate">True on the run path: the trust window is ignored and a fresh stamp is always compared.</param>
    /// <param name="takeStamp">A cheap fresh observation of the source for this client.</param>
    /// <param name="load">The full read and projection.</param>
    /// <returns>The projection, or null when the client is unknown.</returns>
    public PayrollProjection? GetOrLoad(ProjectionKey key, bool revalidate, Func<string> takeStamp, Func<PayrollProjection?> load)
    {
        ArgumentNullException.ThrowIfNull(takeStamp);
        ArgumentNullException.ThrowIfNull(load);
        while (true)
        {
            Flight? joined;
            Flight? mine = null;
            lock (_gate)
            {
                if (!revalidate && _entries.TryGetValue(key, out var node) && Trusted(node.Value))
                {
                    Touch(node);
                    Metrics.Hit();
                    return node.Value.Projection;
                }
                if (!_flights.TryGetValue(key, out joined)) { _flights[key] = mine = new Flight(); }
            }
            if (mine is not null) { return Lead(key, mine, takeStamp, load); }
            Interlocked.Increment(ref _joins);
            joined!.Wait();
            // A run never takes an answer whose stamp predates its own request: it looks again, and takes its own.
            if (revalidate) { continue; }
            Metrics.Hit();
            return joined.Result();
        }
    }

    private bool Trusted(Entry entry) => _clock.GetUtcNow() - entry.TrustedAt < _options.VersionCheck;

    private PayrollProjection? Lead(ProjectionKey key, Flight flight, Func<string> takeStamp, Func<PayrollProjection?> load)
    {
        PayrollProjection? result = null;
        try
        {
            var stamp = takeStamp();
            lock (_gate)
            {
                if (_entries.TryGetValue(key, out var node))
                {
                    Metrics.Revalidated();
                    if (StampsMatch(node.Value.Stamp, stamp))
                    {
                        node.Value.TrustedAt = _clock.GetUtcNow();
                        Touch(node);
                        Metrics.Hit();
                        return result = node.Value.Projection;
                    }
                    Remove(node);
                    Metrics.Reloaded();
                }
            }
            Metrics.Miss();
            result = load();
            if (result is not null) { Store(key, stamp, result); }
            return result;
        }
        catch (Exception error)
        {
            flight.Fail(error);
            throw;
        }
        finally
        {
            lock (_gate) { _flights.Remove(key); }
            flight.Complete(result);
        }
    }

    private void Store(ProjectionKey key, string stamp, PayrollProjection projection)
    {
        var bytes = ProjectionSizeEstimator.Estimate(projection);
        if (bytes > _options.MaxBytes) { return; }
        lock (_gate)
        {
            if (_entries.TryGetValue(key, out var existing)) { Remove(existing); }
            var node = _recent.AddFirst(new Entry(key, projection, stamp, bytes, _clock.GetUtcNow()));
            _entries[key] = node;
            _bytes += bytes;
            while ((_entries.Count > _options.MaxAccounts || _bytes > _options.MaxBytes) && _recent.Last is { } oldest && oldest != node)
            {
                Remove(oldest);
                Metrics.Evicted();
            }
        }
    }

    private void Touch(LinkedListNode<Entry> node)
    {
        _recent.Remove(node);
        _recent.AddFirst(node);
    }

    private void Remove(LinkedListNode<Entry> node)
    {
        _recent.Remove(node);
        _entries.Remove(node.Value.Key);
        _bytes -= node.Value.Bytes;
    }

    /// <inheritdoc />
    public void Dispose() => Metrics.Dispose();

    private sealed class Entry(ProjectionKey key, PayrollProjection projection, string stamp, long bytes, DateTimeOffset trustedAt)
    {
        internal ProjectionKey Key { get; } = key;
        internal PayrollProjection Projection { get; } = projection;
        internal string Stamp { get; } = stamp;
        internal long Bytes { get; } = bytes;
        internal DateTimeOffset TrustedAt { get; set; } = trustedAt;
    }

    private sealed class Flight
    {
        private readonly TaskCompletionSource _done = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private PayrollProjection? _result;
        private ExceptionDispatchInfo? _error;

        internal void Fail(Exception error) => _error = ExceptionDispatchInfo.Capture(error);
        internal void Complete(PayrollProjection? result)
        {
            _result = result;
            _done.SetResult();
        }
        internal void Wait() => _done.Task.GetAwaiter().GetResult();
        internal PayrollProjection? Result()
        {
            _error?.Throw();
            return _result;
        }
    }
}
