using System.Text.Json.Serialization;

namespace TaxCredit.Application.Ports.Auth;

/// <summary>The asserted person is distinct from the authenticated API service.</summary>
public sealed record ActingUser(
    string Oid, string? TenantId = null, string? Name = null, string? Upn = null,
    string Assurance = "channel-asserted", string? Channel = null,
    string? ConversationId = null, string? CorrelationId = null)
{
    /// <summary>Accidental diagnostics must not disclose an asserted person's identifiers.</summary>
    public override string ToString() => "ActingUser";
    /// <summary>Audit attribution follows the person, not the service.</summary>
    public string Actor => Upn ?? Oid;
    /// <summary>Only channel-asserted first-party channels may receive first-party disclosures.</summary>
    public bool IsFirstParty => Assurance == "channel-asserted" && Channel is "teams" or "m365-copilot";
}

/// <summary>Verified claims preserve their API names; no gateway identities are substituted.</summary>
public sealed record ApiPrincipal(
    string? Oid = null, string? Upn = null, string? Name = null, string? TenantId = null,
    IReadOnlyList<string>? Roles = null, IReadOnlyList<string>? Scopes = null,
    bool Authenticated = false, string PrincipalType = "user", ActingUser? ActingFor = null)
{
    /// <summary>Identity is intentionally rendered only in authenticated API responses, never implicit logging.</summary>
    public override string ToString() => "ApiPrincipal";
    /// <summary>Absence of a signed-in person is explicit.</summary>
    public static ApiPrincipal Anonymous { get; } = new();
    /// <summary>App-only service callers cannot acquire delegated rights.</summary>
    public bool IsAgent => PrincipalType == "agent";
    /// <summary>Entitlement follows the acting person; client visibility deliberately uses Oid instead.</summary>
    public string? EffectiveOid => IsAgent ? ActingFor?.Oid : Oid;
    /// <summary>Authenticated attribution never trusts the body.</summary>
    public string Actor => IsAgent ? ActingFor?.Actor ?? "anonymous" : Upn ?? Oid ?? "anonymous";
    /// <summary>The /me shape omits private context and keeps absent values null.</summary>
    public object ToIdentityBody() => new
    {
        authenticated = Authenticated,
        upn = Upn,
        oid = Oid,
        name = Name,
        roles = Roles ?? [],
        principal_type = PrincipalType,
        acting_for = ActingFor is null ? null : new
        {
            oid = ActingFor.Oid,
            name = ActingFor.Name,
            upn = ActingFor.Upn,
            assurance = ActingFor.Assurance,
            channel = ActingFor.Channel
        }
    };
    /// <summary>Anonymous local attribution may use an explicit supplied name.</summary>
    public string Attributed(string? supplied = null, string fallback = "anonymous") =>
        Authenticated ? Actor : string.IsNullOrWhiteSpace(supplied) ? fallback : supplied.Trim();
}

/// <summary>The host maps safe details into the API's JSON detail family, not ProblemDetails.</summary>
public abstract class ApiAuthException(int statusCode, string code, string detail) : Exception(detail)
{
    /// <summary>HTTP status is retained without depending on a web framework.</summary>
    public int StatusCode { get; } = statusCode;
    /// <summary>Stable machine-readable failure classification.</summary>
    public string Code { get; } = code;
    /// <summary>Only authentication failures require a bearer challenge.</summary>
    public string? Challenge => StatusCode == 401 ? "Bearer" : null;
}

/// <summary>Authentication and authorization refusals retain the host's status/code/detail contract separately from dependency failures.</summary>
public sealed class AuthRefusalException(int statusCode, string code, string detail) : ApiAuthException(statusCode, code, detail);

/// <summary>Infrastructure failure cannot become an anonymous successful request.</summary>
public sealed class AuthDependencyException(string code) : ApiAuthException(401, code, "identity verification is unavailable");

/// <summary>Signature validation and shape authorization stay separately testable.</summary>
public interface IApiTokenValidator
{
    /// <summary>Returns a verified principal or a typed 401/403; cancellation propagates.</summary>
    ValueTask<ApiPrincipal> ValidateAsync(string? token, CancellationToken cancellationToken = default);
}

/// <summary>Client rights are keyed by the API caller's oid, including app-only callers.</summary>
public interface IClientAuthorizer
{
    /// <summary>Answers for one normalized client selection.</summary>
    ValueTask<bool> IsAuthorizedAsync(ApiPrincipal principal, long clientId, CancellationToken cancellationToken = default);
}

/// <summary>Writer sources must return actual booleans, never truthy untrusted values.</summary>
public interface IWriterEntitlement
{
    /// <summary>Answers for the person, never the service principal.</summary>
    ValueTask<bool> IsWriterAsync(string userOid, CancellationToken cancellationToken = default);
}

/// <summary>Logs contain fixed source/error classifications, never messages, tokens or object ids.</summary>
public interface IAuthEvents
{
    /// <summary>A failed source denied; another independent source may still grant.</summary>
    void WriterCheckFailed(string source, string errorType);
    /// <summary>A delegated caller's acting-user header was ignored.</summary>
    void ActingHeaderIgnored();
}

/// <summary>Rate refusal payload is separate from the Retry-After header.</summary>
public sealed record RateLimitDecision(
    [property: JsonIgnore] int RetryAfterSeconds,
    [property: JsonPropertyName("code")] string Code,
    [property: JsonPropertyName("reason")] string Reason,
    [property: JsonPropertyName("remedy")] string Remedy)
{
    /// <summary>Zero seconds indicates a successful spend.</summary>
    [JsonIgnore]
    public bool Allowed => RetryAfterSeconds == 0;
}

/// <summary>Host singleton lifecycle owns the per-process buckets.</summary>
public interface IApiRateLimiter
{
    /// <summary>Counts signed-in principal object ids only, separately for each request kind; acting users do not split a service bucket.</summary>
    RateLimitDecision Check(string kind, ApiPrincipal principal);
    /// <summary>Hermetic scenario reset does not affect another service instance.</summary>
    void Reset();
}
