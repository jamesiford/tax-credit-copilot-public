using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Auth;

/// <summary>Explicit anonymous authentication for fake or approved gateway transports.</summary>
public sealed class NoAuth : IRequestAuthenticator
{
    /// <inheritdoc/>
    public ValueTask<IReadOnlyDictionary<string, string>> HeadersAsync(CancellationToken cancellationToken = default)
        => ValueTask.FromResult<IReadOnlyDictionary<string, string>>(new Dictionary<string, string>());
    /// <inheritdoc/>
    public void Invalidate() { }
}
/// <summary>One configurable API-key header, never exposed in diagnostics.</summary>
public sealed class ApiKeyAuth : IRequestAuthenticator
{
    private readonly string _header;
    private readonly string _value;
    /// <summary>Validates header syntax before retaining an in-memory credential.</summary>
    public ApiKeyAuth(string header, string prefix, string key)
    {
        if (string.IsNullOrWhiteSpace(header) || string.IsNullOrEmpty(key)
            || header.Any(c => !char.IsAsciiLetterOrDigit(c) && c != '-')
            || (prefix + key).Any(c => c is '\r' or '\n'))
        {
            throw new ModelException(ModelErrorKind.Configuration, "invalid_api_key_settings");
        }

        _header = header;
        _value = prefix + key;
    }
    /// <inheritdoc/>
    public ValueTask<IReadOnlyDictionary<string, string>> HeadersAsync(CancellationToken cancellationToken = default)
        => ValueTask.FromResult<IReadOnlyDictionary<string, string>>(new Dictionary<string, string> { [_header] = _value });
    /// <inheritdoc/>
    public void Invalidate() { }
    /// <inheritdoc/>
    public override string ToString() => "ApiKeyAuth(<redacted>)";
}

/// <summary>A generation check prevents a concurrent 401 from resurrecting a refresh it invalidated.</summary>
public sealed class CachedTokenAuth : IRequestAuthenticator, IDisposable
{
    private readonly IModelTokenSource _source;
    private readonly string _audience;
    private readonly TimeProvider _clock;
    private readonly SemaphoreSlim _refresh = new(1, 1);
    private readonly Lock _sync = new();
    private ModelAccessToken? _token;
    private int _generation;
    /// <summary>Creates an audience-isolated cache without acquiring a token.</summary>
    public CachedTokenAuth(IModelTokenSource source, string audience, TimeProvider? clock = null)
    {
        if (string.IsNullOrWhiteSpace(audience))
        {
            throw new ModelException(ModelErrorKind.Configuration, "missing_audience");
        }

        _source = source;
        _audience = NormalizeAudience(audience);
        _clock = clock ?? TimeProvider.System;
    }
    /// <inheritdoc/>
    public async ValueTask<IReadOnlyDictionary<string, string>> HeadersAsync(CancellationToken cancellationToken = default)
    {
        await _refresh.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            ModelAccessToken? token;
            int generation;
            lock (_sync) { token = _token; generation = _generation; }
            if (token is null || token.ExpiresAt <= _clock.GetUtcNow().AddSeconds(60))
            {
                token = await AcquireAsync(cancellationToken).ConfigureAwait(false);
                lock (_sync)
                {
                    if (_generation == generation)
                    {
                        _token = token;
                    }
                }
            }
            return new Dictionary<string, string> { ["Authorization"] = "Bearer " + token.Value };
        }
        finally { _refresh.Release(); }
    }
    private async ValueTask<ModelAccessToken> AcquireAsync(CancellationToken cancellationToken)
    {
        ModelAccessToken token;
        try { token = await _source.AcquireAsync(_audience, cancellationToken).ConfigureAwait(false); }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (ModelException) { throw; }
        catch (Exception) { throw new ModelException(ModelErrorKind.Authentication, "token_acquisition_failed"); }
        if (string.IsNullOrWhiteSpace(token.Value) || token.Value.Any(c => c is '\r' or '\n')
            || NormalizeAudience(token.Audience) != _audience || token.ExpiresAt <= _clock.GetUtcNow())
        {
            throw new ModelException(ModelErrorKind.Authentication, "invalid_access_token");
        }

        TokenAudience.Check(token.Value, _audience);
        return token;
    }
    /// <inheritdoc/>
    public void Invalidate() { lock (_sync) { _generation++; _token = null; } }
    /// <summary>Removes the Entra default-scope suffix to compare resource audiences.</summary>
    public static string NormalizeAudience(string audience) => audience.EndsWith("/.default", StringComparison.Ordinal)
        ? audience[..^9].TrimEnd('/') : audience.TrimEnd('/');
    /// <inheritdoc/>
    public override string ToString() => "CachedTokenAuth(<redacted>)";
    /// <summary>Disposes the refresh gate after all requests have completed.</summary>
    public void Dispose() => _refresh.Dispose();
}
