using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth;

/// <summary>Verify proof first; an identity with missing permissions is a distinct 403.</summary>
public sealed class EntraTokenValidator : IApiTokenValidator
{
    private readonly AuthConfiguration _configuration;
    private readonly ISigningKeyProvider _keys;
    private readonly TimeProvider _clock;

    /// <summary>Keys and UTC clock are injected; production never mints tokens.</summary>
    public EntraTokenValidator(AuthConfiguration configuration, ISigningKeyProvider keys, TimeProvider? clock = null)
    {
        configuration.Validate();
        _configuration = configuration;
        _keys = keys;
        _clock = clock ?? TimeProvider.System;
    }

    /// <inheritdoc />
    public async ValueTask<ApiPrincipal> ValidateAsync(string? token, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(token))
        {
            throw new ApiAuthException(401, "no_bearer", "no bearer token");
        }

        if (token.Length > 32_768)
        {
            throw Invalid("token_limit");
        }

        try
        {
            var parts = token.Split('.');
            if (parts.Length != 3)
            {
                throw Invalid("malformed_token");
            }

            using var header = JsonDocument.Parse(Base64Url.Decode(parts[0]));
            if (TokenShape.Text(header.RootElement, "alg") != "RS256")
            {
                throw Invalid("algorithm");
            }

            var kid = TokenShape.Text(header.RootElement, "kid") ?? throw Invalid("missing_key");
            if (kid.Length > 256)
            {
                throw Invalid("missing_key");
            }

            using var payload = JsonDocument.Parse(Base64Url.Decode(parts[1]));
            if (payload.RootElement.ValueKind != JsonValueKind.Object)
            {
                throw Invalid("malformed_token");
            }

            RejectDuplicateClaims(header.RootElement);
            RejectDuplicateClaims(payload.RootElement);
            var key = await _keys.GetKeyAsync(kid, cancellationToken).ConfigureAwait(false);
            using var rsa = RSA.Create(key);
            if (rsa.KeySize < 2048 || !rsa.VerifyData(Encoding.ASCII.GetBytes($"{parts[0]}.{parts[1]}"),
                Base64Url.Decode(parts[2]), HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1))
            {
                throw Invalid("signature");
            }

            ValidateClaims(payload.RootElement);
            return TokenShape.Extract(payload.RootElement, _configuration.TenantId);
        }
        catch (Exception ex) when (ex is JsonException or FormatException or CryptographicException or InvalidOperationException)
        {
            throw Invalid("malformed_token");
        }
    }

    private void ValidateClaims(JsonElement claims)
    {
        var exp = NumericDate(claims, "exp");
        var iat = NumericDate(claims, "iat");
        if (TokenShape.Text(claims, "iss") != _configuration.Issuer)
        {
            throw Invalid("issuer");
        }

        if (!AudienceMatches(claims))
        {
            throw Invalid("audience");
        }

        var now = _clock.GetUtcNow().ToUnixTimeSeconds();
        if (exp <= now - 60)
        {
            throw Invalid("expired");
        }

        if (iat > now + 60)
        {
            throw Invalid("issued_in_future");
        }

        if (claims.TryGetProperty("nbf", out _) && NumericDate(claims, "nbf") > now + 60)
        {
            throw Invalid("not_yet_valid");
        }
    }

    private bool AudienceMatches(JsonElement claims)
    {
        if (!claims.TryGetProperty("aud", out var aud))
        {
            return false;
        }

        if (aud.ValueKind == JsonValueKind.String)
        {
            return _configuration.Audiences.Contains(aud.GetString(), StringComparer.Ordinal);
        }

        if (aud.ValueKind != JsonValueKind.Array || aud.EnumerateArray().Any(a => a.ValueKind != JsonValueKind.String))
        {
            return false;
        }

        return aud.EnumerateArray().Any(a => _configuration.Audiences.Contains(a.GetString(), StringComparer.Ordinal));
    }

    private static long NumericDate(JsonElement claims, string key)
    {
        if (!claims.TryGetProperty(key, out var value) || value.ValueKind != JsonValueKind.Number || !value.TryGetInt64(out var date))
        {
            throw Invalid("required_claim");
        }

        return date;
    }

    private static void RejectDuplicateClaims(JsonElement claims)
    {
        if (claims.ValueKind != JsonValueKind.Object ||
            claims.EnumerateObject().GroupBy(p => p.Name, StringComparer.Ordinal).Any(g => g.Count() != 1))
        {
            throw Invalid("duplicate_claim");
        }
    }

    private static ApiAuthException Invalid(string code) => new(401, code, "invalid token");
}
