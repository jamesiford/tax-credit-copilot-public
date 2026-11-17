using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth;

/// <summary>The host calls these phases in order; handlers own existence/audit-sensitive client checks.</summary>
public sealed class ApiTrustService(AuthConfiguration configuration, IApiTokenValidator validator,
    IClientAuthorizer clients, IAuthEvents events) : IApiTrustService
{
    /// <summary>Case-insensitive scheme extraction never accepts gateway identity headers.</summary>
    public static string? Bearer(string? authorization)
    {
        if (authorization is null)
        {
            return null;
        }

        var split = authorization.IndexOf(' ', StringComparison.Ordinal);
        return split > 0 && authorization[..split].Equals("Bearer", StringComparison.OrdinalIgnoreCase)
            && !string.IsNullOrWhiteSpace(authorization[(split + 1)..]) ? authorization[(split + 1)..].Trim() : null;
    }

    /// <summary>Public requests skip expired tokens; private requests verify then bind acting user.</summary>
    public async ValueTask<ApiPrincipal> AuthenticateAsync(string path, string? authorization,
        string? actingHeader, CancellationToken cancellationToken = default)
    {
        if (RoutePolicy.IsPublic(path) || configuration.Mode.Trim().Equals("none", StringComparison.OrdinalIgnoreCase))
        {
            return ApiPrincipal.Anonymous;
        }

        var principal = await validator.ValidateAsync(Bearer(authorization), cancellationToken).ConfigureAwait(false);
        if (principal.IsAgent)
        {
            return principal with { ActingFor = ActingUserParser.Parse(actingHeader, configuration.TenantId) };
        }

        if (!string.IsNullOrEmpty(actingHeader))
        {
            events.ActingHeaderIgnored();
        }

        return principal;
    }

    /// <summary>Header validation must already have happened, even for agent-forbidden writes (F-16).</summary>
    public async ValueTask AuthorizeRequestAsync(ApiPrincipal principal, string method, string path,
        IEnumerable<long> selections, CancellationToken cancellationToken = default)
    {
        if (RoutePolicy.IsPublic(path)) { return; }
        if (principal.IsAgent && RoutePolicy.IsAgentForbidden(method, path))
        {
            throw new AuthRefusalException(403, "agent_forbidden", "this route is not available to the channel agent");
        }

        if (RoutePolicy.IsSelfAuthorizing(path))
        {
            return;
        }

        foreach (var id in selections.Distinct().Order())
        {
            if (!await clients.IsAuthorizedAsync(principal, id, cancellationToken).ConfigureAwait(false))
            {
                throw new AuthRefusalException(403, "client_forbidden", $"not authorized for client {id}");
            }
        }
    }
}
