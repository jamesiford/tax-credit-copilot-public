using System.Text.Json;
using System.Text.Json.Nodes;

namespace TaxCredit.Orchestrator.Boundary;

/// <summary>Non-sensitive runtime counts and provider names for the debug identity report.</summary>
public sealed record DebugRuntimeState(
    IReadOnlyList<string>? Providers = null, bool ToolsAvailable = false, bool ModelConfigured = false,
    int AuditFailures = 0, int Conversations = 0, string? LastAuditError = null);

/// <summary>All diagnostic headers are allowlisted; credentials, cookies and opaque partition values stay private.</summary>
public static class IdentityPresenter
{
    private static readonly string[] Watched =
    [
        "x-ms-original-subject-oid", "x-ms-original-subject-tid", "x-ms-original-subject-idtype",
        "x-ms-user-identity", "x-agent-user-id", "x-agent-foundry-call-id",
        "x-client-acting-user-oid", "x-client-acting-user-name", "x-client-tenant", "x-client-conversation-id",
    ];
    private static readonly string[] Shown =
    [
        "x-ms-original-subject-oid", "x-ms-original-subject-tid", "x-ms-original-subject-idtype",
        "x-ms-user-identity", "x-client-acting-user-oid", "x-client-acting-user-name", "x-client-tenant",
    ];
    private static readonly string[] OidSignals = ["x-ms-original-subject-oid", "x-ms-user-identity", "x-client-acting-user-oid"];
    private static readonly JsonSerializerOptions Indented = new() { WriteIndented = true };

    /// <summary>Build the Python-compatible report from explicitly allowed fields, never arbitrary context serialization.</summary>
    public static string Whoami(IdentityContext context, IdentityOptions settings, DebugRuntimeState? runtime = null)
    {
        ArgumentNullException.ThrowIfNull(settings);
        runtime ??= new DebugRuntimeState();
        var resolution = IdentityResolver.Resolve(context, settings);
        var identity = resolution.Identity;
        var resolved = identity is null
            ? new JsonObject { ["resolved"] = false, ["reason"] = resolution.Refusal!.Reason }
            : new JsonObject
            {
                ["resolved"] = true,
                ["source"] = identity.Source,
                ["oid"] = identity.Oid,
                ["tenant"] = identity.TenantId,
                ["display_name"] = identity.Name,
                ["channel"] = identity.Channel,
                ["conversation"] = identity.ConversationId,
            };
        return new JsonObject
        {
            ["agent"] = new JsonObject { ["name"] = settings.AgentName, ["version"] = settings.AgentVersion, ["channel"] = settings.Channel },
            ["identity"] = resolved,
            ["signals"] = DescribeSignals(context),
            ["sources"] = Strings(settings.Sources),
            ["conversation"] = IdentityResolver.ConversationOf(context),
            ["providers"] = Strings(runtime.Providers ?? []),
            ["tools_available"] = runtime.ToolsAvailable,
            ["model_configured"] = runtime.ModelConfigured,
            ["turns"] = new JsonObject
            {
                ["audit_failures"] = runtime.AuditFailures,
                ["last_audit_error"] = runtime.LastAuditError,
                ["conversations"] = runtime.Conversations,
            },
        }.ToJsonString(Indented);
    }

    /// <summary>Name watched signals, showing values only for the identity spike's explicit allowlist.</summary>
    public static JsonObject DescribeSignals(IdentityContext context)
    {
        var signals = IdentityResolver.SignalsOf(context);
        var values = new JsonObject();
        foreach (var name in Shown.Where(signals.ContainsKey))
        {
            values[name] = signals[name];
        }
        return new JsonObject
        {
            ["present"] = Strings(Watched.Where(signals.ContainsKey)),
            ["values"] = values,
            ["agent_user_id"] = AgentUserIdShape(signals),
        };
    }

    private static JsonObject? AgentUserIdShape(IReadOnlyDictionary<string, string> signals)
    {
        var value = signals.TryGetValue("x-agent-user-id", out var raw) ? raw.Trim() : "";
        value = value[..Math.Min(value.Length, 256)];
        if (value.Length == 0)
        {
            return null;
        }
        var guid = Guid.TryParseExact(value, "D", out _);
        var result = new JsonObject
        {
            ["kind"] = guid ? "guid" : "opaque",
            ["length"] = value.Length,
            ["equals_an_oid_signal"] = OidSignals
                .Any(name => signals.TryGetValue(name, out var oid) && string.Equals(oid.Trim(), value, StringComparison.OrdinalIgnoreCase)),
        };
        if (guid)
        {
            result["value"] = value;
        }
        return result;
    }

    private static JsonArray Strings(IEnumerable<string> values) => new(values.Select(value => (JsonNode?)JsonValue.Create(value)).ToArray());
}
