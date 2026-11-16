using System.Text.Json;

namespace TaxCredit.Application.Ports;

/// <summary>Authentication adapters receive HTTP facts, not an ASP.NET dependency.</summary>
/// <param name="Method">The HTTP method.</param>
/// <param name="Path">The request path.</param>
/// <param name="Headers">Headers including the bearer and acting-user assertions.</param>
/// <param name="RouteValues">Identifiers declared in the path.</param>
/// <param name="Query">Query values without discarding lists.</param>
/// <param name="Body">The parsed body, when valid JSON was supplied.</param>
public sealed record ApiAccessRequest(
    string Method,
    string Path,
    IReadOnlyDictionary<string, string> Headers,
    IReadOnlyDictionary<string, string> RouteValues,
    IReadOnlyDictionary<string, IReadOnlyList<string>> Query,
    JsonElement? Body);

/// <summary>A refusal is a decision, not an exception hidden by a default fallback.</summary>
/// <param name="Allowed">Whether processing may continue.</param>
/// <param name="Status">HTTP status on refusal.</param>
/// <param name="Detail">A string or the family's structured detail.</param>
/// <param name="BearerChallenge">Whether to send WWW-Authenticate: Bearer.</param>
public sealed record ApiAccessDecision(bool Allowed, int Status = 403, object? Detail = null, bool BearerChallenge = false);

/// <summary>The host's authentication and authorization seam, replaced by the auth slice.</summary>
public interface IApiAccess
{
    /// <summary>Checks the principal, acting person, clients and route policy before dispatch.</summary>
    ValueTask<ApiAccessDecision> Check(ApiAccessRequest request, CancellationToken cancellationToken);
}
