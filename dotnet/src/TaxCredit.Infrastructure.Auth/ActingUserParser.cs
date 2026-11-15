using System.Text;
using System.Text.Json;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth;

/// <summary>Only a trusted app-only API caller may bind this assertion.</summary>
public static class ActingUserParser
{
    /// <summary>Gateway X-Acting-* alternatives are intentionally unsupported.</summary>
    public const string HeaderName = "X-TCC-Acting-User";

    /// <summary>Reject malformed assertions rather than repairing an audit identity.</summary>
    public static ActingUser Parse(string? value, string tenantId)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw Bad("an agent request must name the user it acts for");
        }

        value = value.Trim();
        if (Encoding.UTF8.GetByteCount(value) > 2048)
        {
            throw Bad("acting-user header is too large");
        }

        try
        {
            using var doc = JsonDocument.Parse(Base64Url.Decode(value));
            var body = doc.RootElement;
            if (body.ValueKind != JsonValueKind.Object)
            {
                throw Bad("acting-user header must be a JSON object");
            }

            if (body.EnumerateObject().GroupBy(p => p.Name, StringComparer.Ordinal).Any(g => g.Count() > 1))
            {
                throw Bad("acting-user header has duplicate fields");
            }

            var tid = GuidField(body, "tid");
            if (tid != Guid.Parse(tenantId).ToString())
            {
                throw Bad("acting-user tid does not match the configured tenant");
            }

            var oid = GuidField(body, "oid");
            var assurance = Text(body, "assurance") ?? "channel-asserted";
            if (assurance is not ("channel-asserted" or "delegated"))
            {
                throw Bad("acting-user assurance is not recognised");
            }

            var channel = Text(body, "channel");
            if (channel is not (null or "teams" or "m365-copilot" or "cowork" or "api-test"))
            {
                throw Bad("acting-user channel is not recognised");
            }

            return new(oid, tid, Text(body, "name"), Text(body, "upn"), assurance, channel,
                Text(body, "conversation_id"), Text(body, "correlation_id"));
        }
        catch (Exception ex) when (ex is JsonException or FormatException or InvalidOperationException)
        {
            throw Bad("acting-user header is not valid base64url JSON");
        }
    }

    private static string GuidField(JsonElement body, string key)
    {
        if (!Guid.TryParse(Text(body, key), out var guid))
        {
            throw Bad($"acting-user {key} must be a GUID");
        }

        return guid.ToString();
    }

    private static string? Text(JsonElement body, string key)
    {
        if (!body.TryGetProperty(key, out var value) || value.ValueKind == JsonValueKind.Null)
        {
            return null;
        }

        if (value.ValueKind != JsonValueKind.String || value.GetString()!.EnumerateRunes().Count() > 256)
        {
            throw Bad($"acting-user {key} must be a string of at most 256 characters");
        }

        return string.IsNullOrWhiteSpace(value.GetString()) ? null : value.GetString()!.Trim();
    }

    private static ApiAuthException Bad(string detail) => new(400, "invalid_acting_user", detail);
}
