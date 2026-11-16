using System.Text.Json;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Auth;

/// <summary>Checks resource binding, not signature trust; token acquisition sources remain trusted root adapters.</summary>
internal static class TokenAudience
{
    public static void Check(string token, string expected)
    {
        string[] parts = token.Split('.');
        if (parts.Length != 3)
        {
            return;
        }
        try
        {
            string encoded = parts[1].Replace('-', '+').Replace('_', '/');
            encoded = encoded.PadRight(encoded.Length + (4 - encoded.Length % 4) % 4, '=');
            using var doc = JsonDocument.Parse(Convert.FromBase64String(encoded));
            var aud = doc.RootElement.GetProperty("aud");
            bool matches = aud.ValueKind == JsonValueKind.String
                ? CachedTokenAuth.NormalizeAudience(aud.GetString()!) == expected
                : aud.ValueKind == JsonValueKind.Array && aud.EnumerateArray().Any(a =>
                    a.ValueKind == JsonValueKind.String && CachedTokenAuth.NormalizeAudience(a.GetString()!) == expected);
            if (!matches)
            {
                throw new ModelException(ModelErrorKind.Authentication, "token_audience_mismatch");
            }
        }
        catch (ModelException) { throw; }
        catch (Exception) { throw new ModelException(ModelErrorKind.Authentication, "malformed_access_token"); }
    }
}
