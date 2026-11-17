using System.Globalization;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai;
using TaxCredit.Infrastructure.Ai.Resilience;
using TaxCredit.Infrastructure.Ai.Safety;
using TaxCredit.Orchestrator.Boundary;
using TaxCredit.Orchestrator.Turns;

namespace TaxCredit.Orchestrator.Hosting;

/// <summary>Configuration fails at startup without echoing endpoint, person or secret values.</summary>
public sealed class RuntimeSettings
{
    private readonly IConfiguration _configuration;
    /// <summary>No credentials are acquired while validating executable configuration.</summary>
    public RuntimeSettings(IConfiguration configuration)
    {
        _configuration = configuration;
        Identity = IdentityOptions.FromEnvironment(new Dictionary<string, string?>
        {
            ["TENANT_ID"] = Required("TENANT_ID"),
            ["CHANNEL_NAME"] = Text("CHANNEL_NAME", "teams"),
            ["CHANNEL_IDENTITY_SOURCES"] = Text("CHANNEL_IDENTITY_SOURCES", "original-subject,platform,agent-user-id"),
            ["CHANNEL_DEBUG_WHOAMI"] = Text("CHANNEL_DEBUG_WHOAMI"),
            ["FOUNDRY_AGENT_NAME"] = Text("FOUNDRY_AGENT_NAME", "tcc-channel-orchestrator"),
            ["FOUNDRY_AGENT_VERSION"] = Text("FOUNDRY_AGENT_VERSION", "0"),
        });
        Gateway = new Boundary.GatewaySettings(Https("CHANNEL_GATEWAY_URL"), Required("CHANNEL_GATEWAY_AUDIENCE"),
            TimeSpan.FromSeconds(Integer("CHANNEL_REQUEST_TIMEOUT_SECONDS", 40, 5, 300)));
        Turns = new TurnOptions(Integer("CHANNEL_MAX_TOOL_CALLS", 8, 1, 20), Identity.AgentName, Identity.AgentVersion)
        {
            TurnTimeout = TimeSpan.FromSeconds(Integer("CHANNEL_TURN_TIMEOUT_SECONDS", 90, 10, 600)),
            OutputAllowedHosts = Text("AI_OUTPUT_ALLOWED_HOSTS").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries),
        };
        StateLifetime = TimeSpan.FromSeconds(Integer("CHANNEL_STATE_TTL_SECONDS", 3600, 60, 86400));
        ConfirmationLifetime = TimeSpan.FromSeconds(Integer("CHANNEL_CONFIRM_TTL_SECONDS", 300, 30, 3600));
        Chains = Enum.GetValues<ModelRole>().ToDictionary(role => role, role => (IReadOnlyList<string>)Chain(
            Text("AI_PROVIDER_CHAIN__" + role.ToString().ToUpperInvariant(), Text("AI_PROVIDER_CHAIN", "foundry"))));
        Providers = Chains.Values.SelectMany(chain => chain).Distinct(StringComparer.Ordinal).ToArray();
        if (Providers.Any(name => name is not ("foundry" or "gateway")))
        {
            throw new InvalidOperationException("The hosted orchestrator supports only foundry or gateway chat providers.");
        }
        Ai = new AiRuntimeOptions
        {
            Egress = Text("AI_EGRESS_POLICY", "allow_all") switch
            {
                "allow_all" => EgressPolicy.AllowAll,
                "aggregates_only" => EgressPolicy.AggregatesOnly,
                "block" => EgressPolicy.BlockExternal,
                _ => throw new InvalidOperationException("AI_EGRESS_POLICY is invalid."),
            },
            GlobalDailyTokens = OptionalLong("AI_TOKEN_BUDGET_DAILY"),
            PrincipalDailyTokens = OptionalLong("AI_TOKEN_BUDGET_PER_PRINCIPAL_DAILY"),
            Resilience = new ResilienceSettings(Integer("AI_RETRY_MAX_ATTEMPTS", 3, 1, 10),
                Integer("AI_BULKHEAD_MAX_CONCURRENT", 8, 1, 1000), Integer("AI_BREAKER_FAILURE_THRESHOLD", 5, 1, 1000),
                EventGap: Seconds("AI_CALL_TIMEOUT_SECONDS", 30), Deadline: Seconds("AI_TOTAL_DEADLINE_SECONDS", 45),
                ResetAfter: Seconds("AI_BREAKER_RESET_SECONDS", 30), RetryBase: Seconds("AI_RETRY_BASE_SECONDS", 0.5, allowZero: true))
            {
                MaxDelay = Seconds("AI_RETRY_MAX_SECONDS", 8, allowZero: true),
            },
        };
        Ai.Resilience.Validate();
        foreach (var control in new[] { "AI_INJECTION_GUARD", "AI_OUTPUT_POLICY" })
        {
            if (!Text(control, "on").Equals("on", StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException(control + " must remain on in this hosted runtime.");
            }
        }
        KnowledgeEnabled = Flag("KNOWLEDGE_ENABLED");
        KnowledgeProvider = Text("KNOWLEDGE_PROVIDER", "none").ToLowerInvariant();
        KnowledgeTop = Integer("KNOWLEDGE_TOP", 3, 1, 10);
        if (KnowledgeProvider is not ("none" or "fake" or "foundry-iq") ||
            KnowledgeEnabled && KnowledgeProvider != "fake")
        {
            throw new InvalidOperationException("Enabled knowledge requires KNOWLEDGE_PROVIDER=fake; Foundry IQ is not implemented.");
        }
    }

    /// <summary>Reader trust-source policy.</summary>
    public IdentityOptions Identity { get; }
    /// <summary>Service-authenticated calculation gateway.</summary>
    public Boundary.GatewaySettings Gateway { get; }
    /// <summary>Per-turn read limits and agent attribution.</summary>
    public TurnOptions Turns { get; }
    /// <summary>Idle conversation selection retention.</summary>
    public TimeSpan StateLifetime { get; }
    /// <summary>The framework checkpoint cannot outlive this confirmation deadline.</summary>
    public TimeSpan ConfirmationLifetime { get; }
    /// <summary>Role overrides take precedence over the shared chain.</summary>
    public IReadOnlyDictionary<ModelRole, IReadOnlyList<string>> Chains { get; }
    /// <summary>Every named provider must be configured; none gets a secret default.</summary>
    public IReadOnlyList<string> Providers { get; }
    /// <summary>W1 remains the guard/budget/retry owner.</summary>
    public AiRuntimeOptions Ai { get; }
    /// <summary>Reference retrieval remains opt-in and separate from calculated facts.</summary>
    public bool KnowledgeEnabled { get; }
    /// <summary>Only the explicitly synthetic stand-in is implemented, as in the source.</summary>
    public string KnowledgeProvider { get; }
    /// <summary>A bounded retrieval cannot become an unbounded prompt.</summary>
    public int KnowledgeTop { get; }

    internal string Text(string name, string fallback = "") =>
        string.IsNullOrWhiteSpace(_configuration[name]) ? fallback : _configuration[name]!.Trim();
    internal string Raw(string name, string fallback = "") => _configuration[name] ?? fallback;
    internal string Required(string name) => Text(name) is { Length: > 0 } value ? value :
        throw new InvalidOperationException(name + " is required.");
    internal Uri Https(string name)
    {
        if (!Uri.TryCreate(Required(name), UriKind.Absolute, out var value) || value.Scheme != "https" ||
            value.UserInfo.Length != 0 || value.Query.Length != 0 || value.Fragment.Length != 0)
        {
            throw new InvalidOperationException(name + " must be an HTTPS URL without credentials or query values.");
        }
        return value;
    }
    internal bool Flag(string name, bool fallback = false) => Text(name).ToLowerInvariant() switch
    {
        "" => fallback,
        "1" or "true" or "yes" or "on" => true,
        "0" or "false" or "no" or "off" => false,
        _ => throw new InvalidOperationException(name + " must be true or false."),
    };
    internal string Deployment(ModelRole role, string provider) => Text(
        $"AI_MODEL_{role.ToString().ToUpperInvariant()}__{provider.ToUpperInvariant()}",
        Text("AI_MODEL_" + role.ToString().ToUpperInvariant(), provider == "foundry" ?
            Text("FOUNDRY_MODEL", Text("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini")) : "")) is { Length: > 0 } value
        ? value : throw new InvalidOperationException("A model is required for every configured provider and role.");

    private int Integer(string name, int fallback, int low, int high)
    {
        var text = Text(name);
        if (text.Length == 0) { return fallback; }
        if (!int.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out var value) || value < low || value > high)
        {
            throw new InvalidOperationException(name + " is outside its supported whole-number range.");
        }
        return value;
    }
    internal TimeSpan Seconds(string name, double fallback, bool allowZero = false)
    {
        var text = Text(name);
        if (text.Length == 0) { return TimeSpan.FromSeconds(fallback); }
        if (!double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out var value) ||
            !double.IsFinite(value) || value < 0 || !allowZero && value == 0 || value > 3600)
        {
            throw new InvalidOperationException(name + " is outside its supported seconds range.");
        }
        return TimeSpan.FromSeconds(value);
    }
    private long? OptionalLong(string name) => Text(name) is { Length: > 0 } text
        ? long.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out var value) && value >= 0 ? value :
            throw new InvalidOperationException(name + " must be a nonnegative token count.") : null;
    private static string[] Chain(string text) => text.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries)
        .Select(name => name.ToLowerInvariant()).ToArray() is { Length: > 0 } names ? names :
        throw new InvalidOperationException("A provider chain cannot be empty.");

    /// <inheritdoc/>
    public override string ToString() => "RuntimeSettings(values=<redacted>)";
}
