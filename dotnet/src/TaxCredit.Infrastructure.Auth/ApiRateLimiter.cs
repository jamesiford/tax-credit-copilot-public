using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth;

/// <summary>Settings are validated; zero is explicit disablement, not the gateway's six-per-minute default.</summary>
public sealed record ApiRateLimitOptions(int PerMinute = 60, int MaxKeys = 10_000)
{
    /// <summary>The tuning knob defaults to sixty for absent/junk values; invalid bounds still fail startup.</summary>
    public static ApiRateLimitOptions Parse(string? value)
    {
        var options = new ApiRateLimitOptions(int.TryParse(value, System.Globalization.NumberStyles.Integer,
            System.Globalization.CultureInfo.InvariantCulture, out var parsed) ? parsed : 60);
        options.Validate();
        return options;
    }
    /// <summary>Negative and unbounded configurations are refused at startup.</summary>
    public void Validate()
    {
        if (PerMinute is < 0 or > 1_000_000 || MaxKeys is < 1 or > 1_000_000)
        {
            throw new ArgumentOutOfRangeException(nameof(PerMinute));
        }
    }
}

/// <summary>Continuous refill and spending share one lock, so concurrent requests cannot overspend.</summary>
public sealed class ApiRateLimiter : IApiRateLimiter
{
    private readonly ApiRateLimitOptions _options;
    private readonly TimeProvider _clock;
    private readonly object _gate = new();
    private readonly Dictionary<(string Kind, string Caller), Bucket> _buckets = [];
    private readonly LinkedList<(string Kind, string Caller)> _lru = [];
    private sealed record Bucket(double Tokens, long Stamp, LinkedListNode<(string Kind, string Caller)> Node);

    /// <summary>Timestamp clock is monotonic and injectable; UTC wall time cannot refill a bucket.</summary>
    public ApiRateLimiter(ApiRateLimitOptions? options = null, TimeProvider? clock = null)
    {
        _options = options ?? new(); _options.Validate(); _clock = clock ?? TimeProvider.System;
    }

    /// <inheritdoc />
    public RateLimitDecision Check(string kind, ApiPrincipal principal)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(kind);
        if (!principal.Authenticated || _options.PerMinute == 0)
        {
            return Accepted();
        }
        if (string.IsNullOrWhiteSpace(principal.Oid))
        {
            throw new AuthRefusalException(401, "invalid_caller", "a signed-in caller must have an object id");
        }
        var key = (kind, principal.Oid);
        lock (_gate)
        {
            var now = _clock.GetTimestamp();
            if (!_buckets.TryGetValue(key, out var bucket) && _buckets.Count >= _options.MaxKeys && !MakeSpace(now, out var capacityWait))
            {
                return Refused(capacityWait, "Rate-limit state capacity is busy; active caller allowances are retained.");
            }
            var tokens = bucket is null ? _options.PerMinute : Refilled(bucket, now);
            if (bucket is not null)
            {
                _lru.Remove(bucket.Node);
            }
            var allowed = tokens >= 1;
            var stamp = bucket is null ? now : Math.Max(now, bucket.Stamp);
            _buckets[key] = new(allowed ? tokens - 1 : tokens, stamp, _lru.AddLast(key));
            return allowed ? Accepted() : Refused(Delay(1 - tokens), $"Too many {kind.Replace('_', ' ')} requests from this caller.");
        }
    }

    private double Refilled(Bucket bucket, long now) => Math.Min(_options.PerMinute,
        bucket.Tokens + Math.Max(0, _clock.GetElapsedTime(bucket.Stamp, now).TotalSeconds) * _options.PerMinute / 60.0);

    private bool MakeSpace(long now, out int wait)
    {
        wait = int.MaxValue;
        for (var node = _lru.First; node is not null; node = node.Next)
        {
            var tokens = Refilled(_buckets[node.Value], now);
            // Restarting a full bucket preserves its allowance; restarting a depleted one would grant extra requests.
            if (tokens >= _options.PerMinute)
            {
                _buckets.Remove(node.Value);
                _lru.Remove(node);
                return true;
            }
            wait = Math.Min(wait, Delay(_options.PerMinute - tokens));
        }
        return false;
    }
    private int Delay(double deficit) => Math.Max(1, (int)Math.Floor(deficit / (_options.PerMinute / 60.0)) + 1);
    private static RateLimitDecision Refused(int wait, string reason) => new(wait, "rate_limited", reason,
        $"Wait {wait} seconds and try again (RATE_LIMIT_PER_MINUTE).");
    private static RateLimitDecision Accepted() => new(0, "", "", "");
    /// <summary>Monitoring exposes bounded occupancy without caller identities.</summary>
    public int BucketCount { get { lock (_gate) { return _buckets.Count; } } }
    /// <inheritdoc />
    public void Reset()
    {
        lock (_gate) { _buckets.Clear(); _lru.Clear(); }
    }
}
