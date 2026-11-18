using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Gateway.Execution;
using TaxCredit.Infrastructure.Auth;

namespace TaxCredit.Gateway.Trust;

internal sealed record ChannelCaller(ApiPrincipal Principal, ActingUser Acting, string Kind, string Via, string? AppId);

internal sealed class ChannelAuthenticator(IRuntimeConfiguration settings, ISigningKeyProvider keys, IClock clock, IIdSource ids)
{
    internal async Task<ChannelCaller> AuthenticateAsync(HttpRequest request, string? conversation = null)
    {
        var authorization = request.Headers.Authorization.ToString();
        if (!authorization.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase) || authorization.Length <= 7)
        {
            throw Failure(401, "unauthenticated", "A bearer token is required.");
        }
        using var document = await ClaimsAsync(authorization[7..].Trim(), request.HttpContext.RequestAborted).ConfigureAwait(false);
        var claims = document.RootElement;
        var scopes = Text(claims, "scp")?.Split(' ', StringSplitOptions.RemoveEmptyEntries) ?? [];
        var roles = Strings(claims, "roles");
        var app = Text(claims, "idtyp") == "app" ||
            Text(claims, "oid") is { } oid && oid == Text(claims, "sub") &&
            Text(claims, "name") is null && Text(claims, "preferred_username") is null && Text(claims, "upn") is null;
        var caller = app ? Agent(claims, request, scopes, roles, conversation) : User(claims, request, scopes, roles, conversation);
        request.HttpContext.Items["channel-correlation"] = caller.Acting.CorrelationId;
        return caller;
    }

    private async Task<JsonDocument> ClaimsAsync(string token, CancellationToken ct)
    {
        JsonDocument? payload = null;
        try
        {
            if (token.Length > 32768) { throw new FormatException(); }
            var parts = token.Split('.');
            if (parts.Length != 3) { throw new FormatException(); }
            using var header = JsonDocument.Parse(Decode(parts[0]));
            payload = JsonDocument.Parse(Decode(parts[1]));
            if (header.RootElement.ValueKind != JsonValueKind.Object || payload.RootElement.ValueKind != JsonValueKind.Object ||
                HasDuplicates(header.RootElement) || HasDuplicates(payload.RootElement) || Text(header.RootElement, "alg") != "RS256")
            { throw new FormatException(); }
            var kid = Text(header.RootElement, "kid");
            if (kid is null || kid.Length > 256) { throw new FormatException(); }
            using var rsa = RSA.Create(await keys.GetKeyAsync(kid, ct).ConfigureAwait(false));
            if (rsa.KeySize < 2048 || !rsa.VerifyData(Encoding.ASCII.GetBytes(parts[0] + "." + parts[1]),
                Decode(parts[2]), HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1)) { throw new FormatException(); }
            ValidateClaims(payload.RootElement);
            return payload;
        }
        catch (Exception error) when (error is JsonException or FormatException or CryptographicException or InvalidOperationException or ApiAuthException)
        {
            payload?.Dispose();
            if (error is AuthDependencyException) { throw Failure(503, "identity_unavailable", "Identity verification is unavailable."); }
            throw Failure(401, "unauthenticated", "The bearer token is invalid.");
        }
    }

    private void ValidateClaims(JsonElement claims)
    {
        foreach (var claim in new[] { "scp", "idtyp", "oid", "sub", "name", "preferred_username", "upn", "tid", "azp", "appid" })
        { _ = Text(claims, claim); }
        _ = Strings(claims, "roles");
        var tenant = Tenant;
        var audience = settings.Get("GATEWAY_AUDIENCE") ??
            (settings.Get("CONTRACT_HOOKS") == "1" ? "api://contract-gateway" : null);
        var bare = audience?.Replace("api://", "", StringComparison.Ordinal);
        var audiences = Strings(claims, "aud");
        var now = clock.UtcNow.ToUnixTimeSeconds();
        if (Text(claims, "iss") != $"https://login.microsoftonline.com/{tenant}/v2.0" ||
            !audiences.Any(a => a == bare || a == "api://" + bare) ||
            !claims.TryGetProperty("exp", out var exp) || !exp.TryGetInt64(out var expires) || expires <= now - 60 ||
            !claims.TryGetProperty("iat", out var iat) || !iat.TryGetInt64(out var issued) || issued > now + 60 ||
            claims.TryGetProperty("nbf", out var nbf) && (!nbf.TryGetInt64(out var notBefore) || notBefore > now + 60))
        { throw new FormatException(); }
    }

    private ChannelCaller Agent(JsonElement claims, HttpRequest request, string[] scopes, string[] roles, string? conversation)
    {
        if (scopes.Length != 0) { throw Failure(403, "mixed_token", "An app-only token cannot carry delegated scopes."); }
        var appId = (Text(claims, "azp") ?? Text(claims, "appid"))?.ToLowerInvariant();
        var allowed = (settings.Get("CHANNEL_ALLOWED_CALLER_APP_IDS") ?? "").Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
        var via = roles.Contains("Channel.Invoke", StringComparer.Ordinal) ? "role" :
            allowed.Contains(appId, StringComparer.OrdinalIgnoreCase) ? "allow-list" :
            throw Failure(403, "caller_not_allowed", "The caller lacks Channel.Invoke.");
        var tenant = GuidField(Header(request, "X-Acting-Tenant"));
        if (tenant != Tenant) { throw Failure(403, "tenant_mismatch", "The acting person belongs to another tenant."); }
        var channel = Header(request, "X-Channel");
        if (channel is not ("teams" or "m365-copilot")) { throw Failure(400, "invalid_acting_user", "A first-party channel is required."); }
        var acting = new ActingUser(GuidField(Header(request, "X-Acting-User-Oid")), tenant,
            Bounded(Header(request, "X-Acting-User-Name"), true), Assurance: "channel-asserted", Channel: channel,
            ConversationId: conversation ?? Bounded(Header(request, "X-Conversation-Id"), true), CorrelationId: Correlation(request));
        var bindings = (settings.Get("CHANNEL_CALLER_CHANNELS") ?? "").Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
        if (bindings.Length != 0 && !bindings.Any(entry =>
            entry.Split('=') is [var app, var channels] && string.Equals(app, appId, StringComparison.OrdinalIgnoreCase) &&
            channels.Split('|').Contains(channel, StringComparer.Ordinal)))
        { throw Failure(403, "channel_not_allowed", "This caller cannot assert that channel."); }
        var principal = new ApiPrincipal(Text(claims, "oid"), TenantId: Tenant, Roles: roles, Scopes: scopes,
            Authenticated: true, PrincipalType: "agent", ActingFor: acting);
        return new(principal, acting, "agent", via, appId);
    }

    private ChannelCaller User(JsonElement claims, HttpRequest request, string[] scopes, string[] roles, string? conversation)
    {
        if (!scopes.Contains("Channel.Access", StringComparer.Ordinal)) { throw Failure(403, "missing_scope", "The token lacks Channel.Access."); }
        if (roles.Contains("Channel.Invoke", StringComparer.Ordinal)) { throw Failure(403, "mixed_token", "A delegated token cannot carry an agent role."); }
        if (Text(claims, "tid")?.ToLowerInvariant() != Tenant || Text(claims, "oid") is null)
        { throw Failure(403, "tenant_mismatch", "The token does not identify a person in this tenant."); }
        var acting = new ActingUser(GuidField(Text(claims, "oid")), Tenant, Text(claims, "name"),
            Text(claims, "preferred_username") ?? Text(claims, "upn"), "delegated", "cowork",
            conversation ?? Bounded(Header(request, "X-Conversation-Id"), false), Correlation(request));
        // Keep ActingFor for channel context, while the verified person remains the caller for client policy.
        return new(new ApiPrincipal(acting.Oid, acting.Upn, acting.Name, Tenant, roles, scopes, true,
            ActingFor: acting), acting, "delegated", "scope", Text(claims, "azp"));
    }

    private string Tenant => (settings.Get("TENANT_ID") ?? settings.Get("AUTH_TENANT_ID") ??
        (settings.Get("CONTRACT_HOOKS") == "1" ? "00000000-0000-0000-0000-0000000000aa" : "")).ToLowerInvariant();
    internal static string? Header(HttpRequest request, string name) =>
        string.IsNullOrWhiteSpace(request.Headers[name]) ? null : request.Headers[name].ToString().Trim();
    private static string GuidField(string? value) => Guid.TryParseExact(value, "D", out var id) ? id.ToString() :
        throw Failure(400, "invalid_acting_user", "The identity must be a GUID.");
    private static string? Bounded(string? value, bool required) => value?.Length > 256 || required && value is null
        ? throw Failure(400, "invalid_acting_user", "An acting-user field is missing or too long.") : value;
    private string Correlation(HttpRequest request)
    {
        var supplied = Header(request, "X-Correlation-Id");
        return supplied is null ? ids.NewId().ToString("N") :
            Regex.IsMatch(supplied, @"\A[A-Za-z0-9._-]{1,64}\z", RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1))
                ? supplied : throw Failure(400, "invalid_correlation_id", "The correlation identifier is invalid.");
    }
    private static bool HasDuplicates(JsonElement value) => value.EnumerateObject().GroupBy(p => p.Name, StringComparer.Ordinal).Any(g => g.Count() != 1);
    private static string? Text(JsonElement obj, string key) => !obj.TryGetProperty(key, out var value) || value.ValueKind == JsonValueKind.Null ? null :
        value.ValueKind == JsonValueKind.String ? value.GetString() : throw new FormatException();
    private static string[] Strings(JsonElement obj, string key) => !obj.TryGetProperty(key, out var value) || value.ValueKind == JsonValueKind.Null ? [] :
        value.ValueKind == JsonValueKind.String ? [value.GetString()!] :
        value.ValueKind == JsonValueKind.Array ? value.EnumerateArray().Select(v => v.GetString() ?? throw new FormatException()).ToArray() : throw new FormatException();
    private static byte[] Decode(string value) => Convert.FromBase64String(value.Replace('-', '+').Replace('_', '/') + new string('=', (4 - value.Length % 4) % 4));
    private static ChannelFailure Failure(int status, string code, string message) => new(status, code, message);
}
