using System.Text.Json;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Auth;

/// <summary>OAuth client-credentials over an injected HTTP transport, with safe failure mapping.</summary>
public sealed class OAuthTokenSource : IModelTokenSource
{
    private readonly HttpClient _http;
    private readonly Uri _endpoint;
    private readonly string _clientId;
    private readonly string _secret;
    private readonly string? _scope;
    private readonly TimeProvider _clock;
    /// <summary>Validates HTTPS settings; construction has no network side effects.</summary>
    public OAuthTokenSource(HttpClient http, Uri endpoint, string clientId, string secret,
        string? scope = null, TimeProvider? clock = null)
    {
        if (endpoint.Scheme != "https" || !string.IsNullOrEmpty(endpoint.UserInfo)
            || string.IsNullOrWhiteSpace(clientId) || string.IsNullOrEmpty(secret))
        {
            throw new ModelException(ModelErrorKind.Configuration, "invalid_oauth_settings");
        }

        _http = http;
        _endpoint = endpoint;
        _clientId = clientId;
        _secret = secret;
        _scope = scope;
        _clock = clock ?? TimeProvider.System;
    }
    /// <inheritdoc/>
    public async ValueTask<ModelAccessToken> AcquireAsync(string audience, CancellationToken cancellationToken)
    {
        try { return await FetchAsync(audience, cancellationToken).ConfigureAwait(false); }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (ModelException) { throw; }
        catch (JsonException) { throw new ModelException(ModelErrorKind.Authentication, "invalid_oauth_response"); }
        catch (Exception) { throw new ModelException(ModelErrorKind.Unavailable, "oauth_transport_failed"); }
    }
    private async ValueTask<ModelAccessToken> FetchAsync(string audience, CancellationToken cancellationToken)
    {
        var form = new Dictionary<string, string>
        {
            ["grant_type"] = "client_credentials",
            ["client_id"] = _clientId,
            ["client_secret"] = _secret
        };
        if (_scope is not null)
        {
            form["scope"] = _scope;
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, _endpoint) { Content = new FormUrlEncodedContent(form) };
        using var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
        if ((int)response.StatusCode >= 400)
        {
            throw new ModelException((int)response.StatusCode is 400 or 401 or 403
                ? ModelErrorKind.Authentication : ModelErrorKind.Unavailable, "oauth_refused");
        }

        using var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        using var doc = await JsonDocument.ParseAsync(stream, cancellationToken: cancellationToken).ConfigureAwait(false);
        if (!doc.RootElement.TryGetProperty("access_token", out var token) || token.ValueKind != JsonValueKind.String
            || string.IsNullOrEmpty(token.GetString()))
        {
            throw new ModelException(ModelErrorKind.Authentication, "missing_oauth_token");
        }

        double seconds = doc.RootElement.TryGetProperty("expires_in", out var expiry) && expiry.TryGetDouble(out double value) ? value : 300;
        if (!double.IsFinite(seconds) || seconds <= 0 || seconds > 604800)
        {
            throw new ModelException(ModelErrorKind.Authentication, "invalid_oauth_expiry");
        }

        string actualAudience = doc.RootElement.TryGetProperty("aud", out var aud) && aud.ValueKind == JsonValueKind.String
            ? aud.GetString()! : audience;
        return new(token.GetString()!, actualAudience, _clock.GetUtcNow().AddSeconds(seconds));
    }
    /// <inheritdoc/>
    public override string ToString() => "OAuthTokenSource(secret=<redacted>)";
}
