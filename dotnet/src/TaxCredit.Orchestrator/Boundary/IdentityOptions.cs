namespace TaxCredit.Orchestrator.Boundary;

/// <summary>Identity trust configuration is independent of model and planner configuration.</summary>
public sealed record IdentityOptions
{
    private static readonly string[] KnownSources = ["original-subject", "platform", "client-headers", "agent-user-id"];

    /// <summary>Only these configured assertions may identify a person; caller headers require opt-in.</summary>
    public IReadOnlyList<string> Sources { get; }
    /// <summary>The deployment tenant is never inferred from an opaque platform identifier.</summary>
    public string TenantId { get; }
    /// <summary>The originating Microsoft 365 surface recorded by the gateway.</summary>
    public string Channel { get; }
    /// <summary>Diagnostics are deliberately disabled unless explicitly enabled.</summary>
    public bool DebugWhoami { get; }
    /// <summary>The published agent identity, not the acting person's identity.</summary>
    public string AgentName { get; }
    /// <summary>The published agent version.</summary>
    public string AgentVersion { get; }

    /// <summary>Reject broken trust configuration at startup rather than defaulting a person.</summary>
    public IdentityOptions(string tenantId, string channel = "teams", IEnumerable<string>? sources = null,
        bool debugWhoami = false, string agentName = "tcc-channel-orchestrator", string agentVersion = "0")
    {
        if (!Guid.TryParseExact(tenantId, "D", out var tenant))
        {
            throw new ArgumentException("TENANT_ID must be a GUID.", nameof(tenantId));
        }
        if (channel is not ("teams" or "m365-copilot"))
        {
            throw new ArgumentException("CHANNEL_NAME must be teams or m365-copilot.", nameof(channel));
        }
        var chosen = (sources ?? ["original-subject", "platform", "agent-user-id"])
            .Select(source => source.Trim().ToLowerInvariant()).Where(source => source.Length != 0).ToArray();
        if (chosen.Length == 0 || chosen.Any(source => !KnownSources.Contains(source, StringComparer.Ordinal)))
        {
            throw new ArgumentException("CHANNEL_IDENTITY_SOURCES contains no sources or an unknown source.", nameof(sources));
        }
        TenantId = tenant.ToString("D");
        Channel = channel;
        Sources = Array.AsReadOnly(chosen);
        DebugWhoami = debugWhoami;
        AgentName = agentName;
        AgentVersion = agentVersion;
    }

    /// <summary>Read the Python-compatible identity environment without loading a model configuration.</summary>
    public static IdentityOptions FromEnvironment(IReadOnlyDictionary<string, string?> environment)
    {
        ArgumentNullException.ThrowIfNull(environment);
        string Text(string key, string fallback = "") =>
            environment.TryGetValue(key, out var value) && !string.IsNullOrWhiteSpace(value) ? value.Trim() : fallback;
        var sources = Text("CHANNEL_IDENTITY_SOURCES", "original-subject,platform,agent-user-id").Split(',');
        return new IdentityOptions(Text("TENANT_ID"), Text("CHANNEL_NAME", "teams"), sources,
            Text("CHANNEL_DEBUG_WHOAMI").ToLowerInvariant() is "1" or "true" or "yes" or "on",
            Text("FOUNDRY_AGENT_NAME", "tcc-channel-orchestrator"), Text("FOUNDRY_AGENT_VERSION", "0"));
    }
}
