using System.Text.Json;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth;

/// <summary>Shape extraction runs only after cryptographic validation.</summary>
public static class TokenShape
{
    /// <summary>Preserves oid/roles/scp without claim-name mapping or alternate app identity.</summary>
    public static ApiPrincipal Extract(JsonElement claims, string tenantId)
    {
        var oid = Text(claims, "oid");
        var tid = Text(claims, "tid");
        if (oid is null || !Guid.TryParse(tid, out var tenant) || tenant != Guid.Parse(tenantId))
        {
            throw new AuthRefusalException(401, "invalid_claims", "invalid token identity or tenant");
        }

        var upn = Text(claims, "preferred_username") ?? Text(claims, "upn");
        var name = Text(claims, "name");
        var scope = Text(claims, "scp");
        var scopes = scope?.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries) ?? [];
        var roles = Roles(claims);
        var appFlag = Text(claims, "idtyp") == "app";
        var app = appFlag || oid == Text(claims, "sub") && upn is null && name is null;
        if (app && scopes.Length > 0 || appFlag && (upn is not null || name is not null))
        {
            Deny("token mixes app-only and delegated claims");
        }

        if (app)
        {
            if (roles.Contains("TCC.User", StringComparer.Ordinal))
            {
                Deny("an app-only token must not carry the 'TCC.User' role");
            }

            if (!roles.Contains("TCC.Agent", StringComparer.Ordinal))
            {
                Deny("token lacks the 'TCC.Agent' app role");
            }
        }
        else
        {
            if (roles.Contains("TCC.Agent", StringComparer.Ordinal))
            {
                Deny("a delegated token must not carry the 'TCC.Agent' role");
            }

            if (!scopes.Contains("user_impersonation", StringComparer.Ordinal))
            {
                Deny("token lacks the 'user_impersonation' scope");
            }

            if (!roles.Contains("TCC.User", StringComparer.Ordinal))
            {
                Deny("token lacks the 'TCC.User' app role");
            }
        }
        return new(oid, upn, name, tid, Array.AsReadOnly(roles), Array.AsReadOnly(scopes), true, app ? "agent" : "user");
    }

    internal static string? Text(JsonElement obj, string key)
    {
        if (!obj.TryGetProperty(key, out var value) || value.ValueKind == JsonValueKind.Null)
        {
            return null;
        }

        if (value.ValueKind != JsonValueKind.String)
        {
            throw new AuthRefusalException(401, "invalid_claims", "invalid token claim type");
        }

        return string.IsNullOrEmpty(value.GetString()) ? null : value.GetString();
    }

    private static string[] Roles(JsonElement obj)
    {
        if (!obj.TryGetProperty("roles", out var value) || value.ValueKind == JsonValueKind.Null)
        {
            return [];
        }

        if (value.ValueKind == JsonValueKind.String)
        {
            return [value.GetString()!];
        }

        if (value.ValueKind != JsonValueKind.Array || value.EnumerateArray().Any(v => v.ValueKind != JsonValueKind.String))
        {
            throw new AuthRefusalException(401, "invalid_claims", "invalid token role type");
        }

        return value.EnumerateArray().Select(v => v.GetString()!).ToArray();
    }

    private static void Deny(string message) => throw new AuthRefusalException(403, "token_shape", message);
}
