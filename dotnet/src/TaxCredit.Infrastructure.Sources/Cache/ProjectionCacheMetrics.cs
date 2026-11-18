using System.Diagnostics.Metrics;

namespace TaxCredit.Infrastructure.Sources.Cache;

/// <summary>
/// Counters and gauges for the projection cache, on one Meter the host registers with OpenTelemetry. No instrument carries a
/// client identifier: the numbers are about the cache, never about a customer.
/// </summary>
public sealed class ProjectionCacheMetrics : IDisposable
{
    /// <summary>The Meter name to pass to <c>AddMeter</c>.</summary>
    public const string MeterName = "TaxCredit.SourceCache";
    private readonly Meter _meter = new(MeterName);
    internal Meter Meter => _meter;
    private readonly Counter<long> _hits;
    private readonly Counter<long> _misses;
    private readonly Counter<long> _evictions;
    private readonly Counter<long> _revalidations;
    private readonly Counter<long> _reloads;
    private long _hitCount, _missCount, _evictionCount, _revalidationCount, _reloadCount;

    /// <summary>Creates the instruments; the two gauges read the supplied callbacks when a listener collects.</summary>
    public ProjectionCacheMetrics(Func<long> entries, Func<long> estimatedBytes)
    {
        ArgumentNullException.ThrowIfNull(entries);
        ArgumentNullException.ThrowIfNull(estimatedBytes);
        _hits = _meter.CreateCounter<long>("tcc.source_cache.hits", "{read}", "Reads served without reading the source's rows.");
        _misses = _meter.CreateCounter<long>("tcc.source_cache.misses", "{read}", "Reads that read the source's rows.");
        _evictions = _meter.CreateCounter<long>("tcc.source_cache.evictions", "{entry}", "Entries dropped to stay inside the size or account bound.");
        _revalidations = _meter.CreateCounter<long>("tcc.source_cache.revalidations", "{check}", "Fingerprint checks taken against a held entry.");
        _reloads = _meter.CreateCounter<long>("tcc.source_cache.reloads", "{read}", "Held entries dropped because the source's stamp changed.");
        _meter.CreateObservableGauge("tcc.source_cache.entries", entries, "{entry}", "Clients currently held.");
        _meter.CreateObservableGauge("tcc.source_cache.estimated_bytes", estimatedBytes, "By", "Estimated bytes held (an estimate, not a measurement).");
    }

    /// <summary>Total reads served from a held entry or a shared in-flight load.</summary>
    public long Hits => Interlocked.Read(ref _hitCount);
    /// <summary>Total reads that read the source.</summary>
    public long Misses => Interlocked.Read(ref _missCount);
    /// <summary>Total entries evicted for size or count.</summary>
    public long Evictions => Interlocked.Read(ref _evictionCount);
    /// <summary>Total fingerprint checks against a held entry.</summary>
    public long Revalidations => Interlocked.Read(ref _revalidationCount);
    /// <summary>Total held entries replaced because the stamp changed.</summary>
    public long Reloads => Interlocked.Read(ref _reloadCount);

    internal void Hit() { Interlocked.Increment(ref _hitCount); _hits.Add(1); }
    internal void Miss() { Interlocked.Increment(ref _missCount); _misses.Add(1); }
    internal void Evicted() { Interlocked.Increment(ref _evictionCount); _evictions.Add(1); }
    internal void Revalidated() { Interlocked.Increment(ref _revalidationCount); _revalidations.Add(1); }
    internal void Reloaded() { Interlocked.Increment(ref _reloadCount); _reloads.Add(1); }

    /// <inheritdoc />
    public void Dispose() => _meter.Dispose();
}
