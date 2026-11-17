namespace TaxCredit.Orchestrator.Boundary;

/// <summary>The platform's invocation-local original-subject assertion, mapped by the SDK adapter.</summary>
public sealed record PlatformOriginalSubject(string? Oid = null, string? Tid = null, string? IdType = null);

/// <summary>Neutral Responses context keeps transport SDKs outside identity resolution.</summary>
public sealed record IdentityContext(
    IReadOnlyDictionary<string, string>? ClientHeaders = null,
    PlatformOriginalSubject? OriginalSubject = null,
    string? AgentUserId = null,
    string? ConversationId = null,
    string? ConversationChainId = null,
    string? ResponseId = null);

/// <summary>Every mutable conversation resource must use both fields, not just a response chain.</summary>
public readonly record struct PersonConversationKey(string Oid, string ConversationId);

/// <summary>A verified configured assertion; only the resolver may mint an acting identity.</summary>
public sealed record ActingIdentity
{
    internal ActingIdentity(string oid, string name, string tenantId, string channel,
        string conversationId, string correlationId, string source)
    {
        Oid = oid;
        Name = name;
        TenantId = tenantId;
        Channel = channel;
        ConversationId = conversationId;
        CorrelationId = correlationId;
        Source = source;
    }

    /// <summary>Normalized Entra person object identifier, never the application's identifier.</summary>
    public string Oid { get; }
    /// <summary>The supplied display label or an explicit unknown-name label.</summary>
    public string Name { get; }
    /// <summary>Normalized deployment tenant.</summary>
    public string TenantId { get; }
    /// <summary>The configured Microsoft 365 channel.</summary>
    public string Channel { get; }
    /// <summary>The explicit conversation or response-chain fallback.</summary>
    public string ConversationId { get; }
    /// <summary>A bounded, header-safe response correlation identifier.</summary>
    public string CorrelationId { get; }
    /// <summary>The configured assertion source which resolved this person.</summary>
    public string Source { get; }
    /// <summary>Sharing a response chain never shares state between people.</summary>
    public PersonConversationKey Key => new(Oid, ConversationId);

    /// <summary>Gateway assertions differ from the backend API's X-TCC-Acting-User header.</summary>
    public IReadOnlyDictionary<string, string> GatewayHeaders() => new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["X-Acting-User-Oid"] = Oid,
        ["X-Acting-User-Name"] = Name,
        ["X-Acting-Tenant"] = TenantId,
        ["X-Channel"] = Channel,
        ["X-Conversation-Id"] = ConversationId,
        ["X-Correlation-Id"] = CorrelationId,
    };
}

/// <summary>A refusal is data; it authorizes neither a model request nor a gateway call.</summary>
public sealed record IdentityRefusal(string Reason)
{
    /// <summary>Public wording used by the recorded anonymous-identity case.</summary>
    public const string RefusalMessage = "I can't tell who you are in this conversation, so I won't run anything. " +
        "Every answer and every change here is recorded against a named person.";
    /// <summary>The reader sees no sensitive assertion or transport details.</summary>
    public string Message => RefusalMessage;
}

/// <summary>The only successful resolution carries a minted identity, never a default user.</summary>
public sealed record IdentityResolution
{
    internal IdentityResolution(ActingIdentity identity) => Identity = identity;
    internal IdentityResolution(IdentityRefusal refusal) => Refusal = refusal;
    /// <summary>Present only after source, person, tenant and conversation checks succeed.</summary>
    public ActingIdentity? Identity { get; }
    /// <summary>Present when the turn must not run tools or a model.</summary>
    public IdentityRefusal? Refusal { get; }
    /// <summary>Convenience for host refusal handling.</summary>
    public bool IsResolved => Identity is not null;
}
