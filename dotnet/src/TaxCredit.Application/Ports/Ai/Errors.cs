namespace TaxCredit.Application.Ports.Ai;

/// <summary>Controlled classifications used for retry, fallback and host translation.</summary>
public enum ModelErrorKind
{
    /// <summary>Invalid local settings.</summary>
    Configuration,
    /// <summary>Credentials were unavailable or refused.</summary>
    Authentication,
    /// <summary>The provider rejected the request.</summary>
    BadRequest,
    /// <summary>A transient transport or service failure.</summary>
    Unavailable,
    /// <summary>An event gap or total deadline elapsed.</summary>
    Timeout,
    /// <summary>Upstream throttling.</summary>
    RateLimited,
    /// <summary>Local egress policy refused the brief.</summary>
    EgressRefused,
    /// <summary>Injection screening refused reader instructions.</summary>
    InjectionBlocked,
    /// <summary>A UTC-day token allowance was spent.</summary>
    BudgetExceeded,
    /// <summary>Local concurrency shedding, not a health failure.</summary>
    BulkheadFull,
    /// <summary>The provider breaker is open.</summary>
    CircuitOpen,
    /// <summary>No chain member could answer.</summary>
    NarrationUnavailable
}

/// <summary>Only controlled rule codes cross the error boundary; upstream bodies and exceptions never do.</summary>
/// <remarks>Constructs an error using controlled codes, never upstream text.</remarks>
public sealed class ModelException(ModelErrorKind kind, string code, TimeSpan? retryAfter = null,
    IReadOnlyList<string>? rules = null, IReadOnlyList<string>? hops = null) : Exception($"Model access refused ({kind}).")
{
    /// <summary>The failure category.</summary>
    public ModelErrorKind Kind { get; } = kind;
    /// <summary>A controlled diagnostic rule code.</summary>
    public string Code { get; } = code;
    /// <summary>The optional upstream backoff delay.</summary>
    public TimeSpan? RetryAfter { get; } = retryAfter;
    /// <summary>Safety rules, never matched text.</summary>
    public IReadOnlyList<string> Rules { get; } = rules ?? [];
    /// <summary>Attempted providers, in order.</summary>
    public IReadOnlyList<string> Hops { get; } = hops ?? [];
    /// <summary>Whether a retry before output could succeed.</summary>
    public bool Retryable => Kind is ModelErrorKind.Unavailable or ModelErrorKind.Timeout or ModelErrorKind.RateLimited;
    /// <summary>Whether this counts against provider health.</summary>
    public bool ProviderFailure => Kind is ModelErrorKind.Authentication or ModelErrorKind.Unavailable
        or ModelErrorKind.Timeout or ModelErrorKind.RateLimited;
}
