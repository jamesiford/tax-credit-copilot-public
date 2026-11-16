using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth;

/// <summary>Instance-local safe events retain only classifications, never exception payloads or identities.</summary>
public sealed class AuthEvents : IAuthEvents
{
    private readonly System.Collections.Concurrent.ConcurrentDictionary<string, long> _counts = new(StringComparer.Ordinal);
    private readonly Action<string, string>? _failureSink;
    private readonly Action? _ignoredSink;
    /// <summary>The host maps callbacks to its logger/telemetry without sensitive dimensions.</summary>
    public AuthEvents(Action<string, string>? failureSink = null, Action? ignoredSink = null)
    {
        _failureSink = failureSink;
        _ignoredSink = ignoredSink;
    }
    /// <inheritdoc />
    public void WriterCheckFailed(string source, string errorType)
    {
        _counts.AddOrUpdate(source, 1, (_, count) => count + 1);
        Notify(() => _failureSink?.Invoke(source, errorType));
    }
    /// <inheritdoc />
    public void ActingHeaderIgnored() => Notify(() => _ignoredSink?.Invoke());
    private static void Notify(Action callback)
    {
        // Logging failure must not hide independent grants or honour an ignored acting-user header.
        try { callback(); }
        catch (Exception) { }
    }
    /// <summary>Monitoring distinguishes a broken entitlement source from normal refusals.</summary>
    public IReadOnlyDictionary<string, long> DenialCounts => new Dictionary<string, long>(_counts, StringComparer.Ordinal);
    /// <summary>Reset counters between hermetic scenarios.</summary>
    public void Reset() => _counts.Clear();
}

/// <summary>Wrap repository sources so outages deny and do not hide independent grants.</summary>
public sealed class DenyOnFailure(IWriterEntitlement source, string name, IAuthEvents events) : IWriterEntitlement
{
    /// <inheritdoc />
    public async ValueTask<bool> IsWriterAsync(string userOid, CancellationToken cancellationToken = default)
    {
        try { return await source.IsWriterAsync(userOid, cancellationToken).ConfigureAwait(false); }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (Exception ex)
        {
            events.WriterCheckFailed(name, ex.GetType().Name);
            return false;
        }
    }
}

/// <summary>Only an actual boolean provider result can grant; malformed object replies fail closed.</summary>
public sealed class StrictWriterSource(Func<string, CancellationToken, ValueTask<object?>> read) : IWriterEntitlement
{
    /// <inheritdoc />
    public async ValueTask<bool> IsWriterAsync(string userOid, CancellationToken cancellationToken = default)
    {
        var answer = await read(userOid, cancellationToken).ConfigureAwait(false);
        return answer is bool value ? value : throw new InvalidOperationException("Writer source returned a non-boolean.");
    }
}

/// <summary>Checks cheap sources first, with an independent failure boundary for each.</summary>
public sealed class EitherEntitlement : IWriterEntitlement
{
    private readonly IWriterEntitlement[] _sources;
    /// <summary>Names are configuration constants, not user-provided labels.</summary>
    public EitherEntitlement(IEnumerable<(string Name, IWriterEntitlement Source)> sources, IAuthEvents events) =>
        _sources = sources.Select(s => (IWriterEntitlement)new DenyOnFailure(s.Source, s.Name, events)).ToArray();
    /// <inheritdoc />
    public async ValueTask<bool> IsWriterAsync(string userOid, CancellationToken cancellationToken = default)
    {
        foreach (var source in _sources)
        {
            if (await source.IsWriterAsync(userOid, cancellationToken).ConfigureAwait(false))
            {
                return true;
            }
        }

        return false;
    }
}

/// <summary>Writer authorization is a command-stage obligation, not an alternate route identity.</summary>
public sealed class WriterPolicy(IWriterEntitlement entitlement, bool enforceForUsers = false) : IWriterPolicy
{
    /// <summary>Open commands must be explicitly decided by endpoint owners; reads must not be passed as writes (F-15).</summary>
    public async ValueTask CheckAsync(ApiPrincipal principal, string? actor, bool requiresWriter,
        CancellationToken cancellationToken = default)
    {
        if (!requiresWriter)
        {
            return;
        }

        if (principal.IsAgent)
        {
            if (principal.ActingFor is null)
            {
                throw new AuthRefusalException(403, "missing_acting_user", "an agent write must name the user it acts for");
            }

            if (actor != principal.ActingFor.Actor)
            {
                throw new AuthRefusalException(403, "author_mismatch", "the command's author is not the user the agent acts for");
            }
        }
        else if (!enforceForUsers)
        {
            return;
        }

        if (principal.EffectiveOid is not { } oid ||
            !await entitlement.IsWriterAsync(oid, cancellationToken).ConfigureAwait(false))
        {
            throw new AuthRefusalException(403, "writer_forbidden", "this user is not entitled to make changes");
        }
    }
}
