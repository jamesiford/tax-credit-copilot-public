using System.Security.Cryptography;
using System.Text.Json;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth;

/// <summary>Injected keys keep tests hermetic and never require private key material in production.</summary>
public interface ISigningKeyProvider
{
    /// <summary>A missing signing key is a typed authentication failure.</summary>
    ValueTask<RSAParameters> GetKeyAsync(string keyId, CancellationToken cancellationToken = default);
    /// <summary>Reset cached metadata between hermetic scenarios.</summary>
    void Reset();
}

/// <summary>Retrieval is separate from cache/rotation decisions.</summary>
public interface IJwksTransport
{
    /// <summary>Returns bounded public JWKS bytes from the configured tenant.</summary>
    ValueTask<ReadOnlyMemory<byte>> FetchAsync(CancellationToken cancellationToken = default);
}

/// <summary>Uses only the configured Entra URI, with a deadline and bounded response.</summary>
public sealed class HttpJwksTransport(HttpClient client, AuthConfiguration configuration) : IJwksTransport
{
    /// <inheritdoc />
    public async ValueTask<ReadOnlyMemory<byte>> FetchAsync(CancellationToken cancellationToken = default)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(5));
        try
        {
            using var response = await client.GetAsync(configuration.JwksUri, HttpCompletionOption.ResponseHeadersRead, deadline.Token).ConfigureAwait(false);
            response.EnsureSuccessStatusCode();
            await using var stream = await response.Content.ReadAsStreamAsync(deadline.Token).ConfigureAwait(false);
            using var buffer = new MemoryStream();
            var bytes = new byte[8192];
            int read;
            while ((read = await stream.ReadAsync(bytes, deadline.Token).ConfigureAwait(false)) > 0)
            {
                if (buffer.Length + read > 1_048_576)
                {
                    throw new AuthDependencyException("jwks_response_limit");
                }

                buffer.Write(bytes, 0, read);
            }
            return buffer.ToArray();
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new AuthDependencyException("jwks_timeout");
        }
        catch (HttpRequestException)
        {
            throw new AuthDependencyException("jwks_unavailable");
        }
        catch (IOException)
        {
            throw new AuthDependencyException("jwks_unavailable");
        }
    }
}

/// <summary>Coalesced bounded refresh prevents arbitrary kids from becoming unbounded egress.</summary>
public sealed class CachedJwksProvider : ISigningKeyProvider, IDisposable
{
    private readonly IJwksTransport _transport;
    private readonly TimeProvider _clock;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private Dictionary<string, RSAParameters> _keys = new(StringComparer.Ordinal);
    private long? _fetched;
    private long? _attempted;
    private bool _lastFailed;

    /// <summary>Cache is instance-owned; defaults mirror Python's one-hour key-set lifetime.</summary>
    public CachedJwksProvider(IJwksTransport transport, TimeProvider? clock = null)
    {
        _transport = transport;
        _clock = clock ?? TimeProvider.System;
    }

    /// <inheritdoc />
    public async ValueTask<RSAParameters> GetKeyAsync(string keyId, CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var now = _clock.GetTimestamp();
            var fresh = _fetched.HasValue && _clock.GetElapsedTime(_fetched.Value, now) < TimeSpan.FromHours(1);
            if (fresh && _keys.TryGetValue(keyId, out var cached))
            {
                return Clone(cached);
            }

            if (_attempted.HasValue && _clock.GetElapsedTime(_attempted.Value, now) < TimeSpan.FromSeconds(5))
            {
                throw _lastFailed ? new AuthDependencyException("jwks_refresh_failed") : new ApiAuthException(401, "unknown_key", "invalid token signing key");
            }

            _attempted = now;
            try
            {
                var bytes = await _transport.FetchAsync(cancellationToken).ConfigureAwait(false);
                _keys = Parse(bytes);
                _fetched = _clock.GetTimestamp();
                _lastFailed = false;
            }
            catch (OperationCanceledException) { _attempted = null; throw; }
            catch (Exception ex) when (ex is JsonException or FormatException or CryptographicException or ApiAuthException or HttpRequestException or IOException or TimeoutException or KeyNotFoundException or InvalidOperationException)
            {
                _lastFailed = true;
                throw new AuthDependencyException("jwks_refresh_failed");
            }
            return _keys.TryGetValue(keyId, out var key) ? Clone(key) : throw new ApiAuthException(401, "unknown_key", "invalid token signing key");
        }
        finally { _gate.Release(); }
    }

    private static Dictionary<string, RSAParameters> Parse(ReadOnlyMemory<byte> bytes)
    {
        using var json = JsonDocument.Parse(bytes);
        var keys = json.RootElement.GetProperty("keys");
        if (keys.ValueKind != JsonValueKind.Array || keys.GetArrayLength() > 100)
        {
            throw new JsonException("Invalid key set.");
        }

        var result = new Dictionary<string, RSAParameters>(StringComparer.Ordinal);
        foreach (var key in keys.EnumerateArray())
        {
            if (TokenShape.Text(key, "kty") != "RSA" || TokenShape.Text(key, "use") is { } use && use != "sig"
                || TokenShape.Text(key, "alg") is { } alg && alg != "RS256")
            {
                continue;
            }

            var kid = TokenShape.Text(key, "kid") ?? throw new JsonException("Missing kid.");
            if (kid.Length > 256) { throw new JsonException("Key identifier exceeds bound."); }
            var parameters = new RSAParameters
            {
                Modulus = Base64Url.Decode(TokenShape.Text(key, "n") ?? ""),
                Exponent = Base64Url.Decode(TokenShape.Text(key, "e") ?? "")
            };
            if (parameters.Modulus.Length is < 256 or > 1024 || parameters.Exponent.Length is < 1 or > 8)
            {
                throw new JsonException("RSA parameters exceed bounds.");
            }
            using var rsa = RSA.Create(parameters);
            if (rsa.KeySize < 2048 || !result.TryAdd(kid, parameters))
            {
                throw new JsonException("Invalid RSA key.");
            }
        }
        if (result.Count == 0)
        {
            throw new JsonException("Empty RSA key set.");
        }

        return result;
    }

    private static RSAParameters Clone(RSAParameters key) => new()
    {
        Modulus = key.Modulus?.ToArray(),
        Exponent = key.Exponent?.ToArray()
    };

    /// <inheritdoc />
    public void Reset()
    {
        _gate.Wait();
        try { _keys.Clear(); _fetched = null; _attempted = null; _lastFailed = false; }
        finally { _gate.Release(); }
    }

    /// <summary>Releases cache synchronization when the host shuts down.</summary>
    public void Dispose() => _gate.Dispose();
}
