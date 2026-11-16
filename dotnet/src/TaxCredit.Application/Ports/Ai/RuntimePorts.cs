namespace TaxCredit.Application.Ports.Ai;

/// <summary>One provider's injected way of narrating a trusted definition.</summary>
public interface IAgentRuntime
{
    /// <summary>The registered provider label.</summary>
    string Name { get; }
    /// <summary>Configuration readiness, not breaker health.</summary>
    bool ReadyFor(string agentName);
    /// <summary>The published/injected definition version if known.</summary>
    string? VersionOf(string agentName);
    /// <summary>Safe health status.</summary>
    ProviderStatus Status();
    /// <summary>Streams unframed events; cancellation stops upstream work.</summary>
    IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request, CancellationToken cancellationToken = default);
}
/// <summary>A bare chat model that returns but never executes tools.</summary>
public interface IChatModel
{
    /// <summary>The registered provider name.</summary>
    string Name { get; }
    /// <summary>Safe readiness state.</summary>
    ProviderStatus Status();
    /// <summary>Streams one model request.</summary>
    IAsyncEnumerable<ModelEvent> StreamAsync(ChatRequest request, CancellationToken cancellationToken = default);
}
/// <summary>Injectable request authentication, independent of model dialect.</summary>
public interface IRequestAuthenticator
{
    /// <summary>Obtains credentials only when a guarded request is admitted.</summary>
    ValueTask<IReadOnlyDictionary<string, string>> HeadersAsync(CancellationToken cancellationToken = default);
    /// <summary>Invalidates cached credentials after upstream 401.</summary>
    void Invalidate();
}
/// <summary>Opaque credentials with audience and expiry metadata.</summary>
public sealed class ModelAccessToken(string value, string audience, DateTimeOffset expiresAt)
{
    /// <summary>The secret value, never logged.</summary>
    public string Value { get; } = value;
    /// <summary>The resource audience the token was acquired for.</summary>
    public string Audience { get; } = audience;
    /// <summary>UTC expiry supplied by the credential adapter.</summary>
    public DateTimeOffset ExpiresAt { get; } = expiresAt;
    /// <inheritdoc/>
    public override string ToString() => "ModelAccessToken(<redacted>)";
}
/// <summary>The root chooses the credential mechanism.</summary>
public interface IModelTokenSource
{
    /// <summary>Acquires for exactly one configured audience.</summary>
    ValueTask<ModelAccessToken> AcquireAsync(string audience, CancellationToken cancellationToken);
}
/// <summary>An egress verdict containing only controlled rule names.</summary>
public sealed record GuardDecision(bool Allowed, IReadOnlyList<string> Rules);
/// <summary>Runs before transport/authentication work.</summary>
public interface IModelGuard
{
    /// <summary>Checks an assembled request for a particular provider.</summary>
    GuardDecision Evaluate(NarrationRequest request, string provider);
}
/// <summary>An atomic pending budget charge, released if no physical attempt starts.</summary>
public interface ITokenReservation : IDisposable
{
    /// <summary>Settles exactly once with reported or estimated usage.</summary>
    void RecordAttempt(ModelUsage usage);
}
/// <summary>Concurrent per-process UTC-day guard rail, not an invoice.</summary>
public interface ITokenBudget
{
    /// <summary>Reserves before invoking the provider.</summary>
    ITokenReservation Reserve(string principal, int estimatedTokens);
    /// <summary>Settled tokens overall or for one principal.</summary>
    long Used(string? principal = null);
    /// <summary>Clears state between isolated harness scenarios.</summary>
    void Reset();
}
/// <summary>Registered low-cardinality call labels, never prompt or principal.</summary>
public sealed record AiCallInfo(ModelRole Role, string Provider, string Agent, string? Model = null);
/// <summary>Call shape/outcome for telemetry, with no text content.</summary>
public sealed record AiCallResult(string Outcome, ModelUsage? Usage = null, string? ErrorType = null,
    StreamEnd? End = null, int PromptChars = 0, int OutputChars = 0);
/// <summary>One call's observation, finished exactly once.</summary>
public interface IAiCallSpan
{
    /// <summary>Records an outcome without exception messages.</summary>
    void Finish(AiCallResult result);
}
/// <summary>Injectable observations; exporter ownership stays with the host.</summary>
public interface IAiTelemetry
{
    /// <summary>Starts one outermost request observation.</summary>
    IAiCallSpan StartCall(AiCallInfo info);
    /// <summary>Counts a controlled metric with safe labels.</summary>
    void Count(string metric, long value = 1, string? provider = null, string? scope = null);
}
