using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth;

/// <summary>Successes and legitimate denials cache for a minute; failures never cache.</summary>
public sealed class EntraGroupEntitlement : IWriterEntitlement, IDisposable
{
    private readonly string _group;
    private readonly IGroupMembershipProvider _provider;
    private readonly IAuthEvents _events;
    private readonly TimeProvider _clock;
    private readonly TimeSpan _ttl;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly Dictionary<string, (long Stamp, bool Answer)> _cache = new(StringComparer.Ordinal);
    private readonly int _maxEntries;

    /// <summary>Group identity/TTL are immutable per service instance, avoiding tenant/config cache leakage.</summary>
    public EntraGroupEntitlement(string groupId, IGroupMembershipProvider provider, IAuthEvents events,
        TimeProvider? clock = null, TimeSpan? cacheDuration = null, int maxEntries = 10_000)
    {
        if (!Guid.TryParse(groupId, out var group))
        {
            throw new ArgumentException("Writer group must be a GUID.", nameof(groupId));
        }

        _group = group.ToString(); _provider = provider; _events = events; _clock = clock ?? TimeProvider.System;
        _ttl = cacheDuration ?? TimeSpan.FromSeconds(60); _maxEntries = maxEntries;
        if (_ttl < TimeSpan.Zero || maxEntries < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(cacheDuration));
        }
    }

    /// <inheritdoc />
    public async ValueTask<bool> IsWriterAsync(string userOid, CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var now = _clock.GetTimestamp();
            if (_cache.TryGetValue(userOid, out var hit) && _clock.GetElapsedTime(hit.Stamp, now) < _ttl)
            {
                return hit.Answer;
            }

            _cache.Remove(userOid);
            try
            {
                var answer = await _provider.IsMemberAsync(userOid, _group, cancellationToken).ConfigureAwait(false);
                if (_cache.Count >= _maxEntries)
                {
                    _cache.Remove(_cache.MinBy(p => p.Value.Stamp).Key);
                }

                _cache[userOid] = (_clock.GetTimestamp(), answer);
                return answer;
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
            catch (Exception ex)
            {
                _events.WriterCheckFailed("entra_group", ex.GetType().Name);
                return false;
            }
        }
        finally { _gate.Release(); }
    }

    /// <summary>Reset under the same lock as refresh prevents stale in-flight answers leaking into a new scenario.</summary>
    public void Reset()
    {
        _gate.Wait();
        try { _cache.Clear(); }
        finally { _gate.Release(); }
    }
    /// <summary>Releases synchronization at host shutdown.</summary>
    public void Dispose() => _gate.Dispose();
}
