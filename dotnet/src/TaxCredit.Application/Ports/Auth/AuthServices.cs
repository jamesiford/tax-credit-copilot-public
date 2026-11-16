namespace TaxCredit.Application.Ports.Auth;

/// <summary>Request trust phases are available to the host without infrastructure references in handlers.</summary>
public interface IApiTrustService
{
    /// <summary>Public bypass, bearer verification and acting-user binding, in that order.</summary>
    ValueTask<ApiPrincipal> AuthenticateAsync(string path, string? authorization, string? actingHeader,
        CancellationToken cancellationToken = default);
    /// <summary>Bound header precedes agent-forbidden metadata; selected clients are checked before dispatch.</summary>
    ValueTask AuthorizeRequestAsync(ApiPrincipal principal, string method, string path, IEnumerable<long> selections,
        CancellationToken cancellationToken = default);
}

/// <summary>Command handlers can ask the same writer question as the host's authorization stage.</summary>
public interface IWriterPolicy
{
    /// <summary>Only explicit writes compare their actor with the acting person; reads must not pretend to be writes.</summary>
    ValueTask CheckAsync(ApiPrincipal principal, string? actor, bool requiresWriter,
        CancellationToken cancellationToken = default);
}

/// <summary>The host pushes a scope synchronously before dispatch and disposes it in finally.</summary>
public interface IApiPrincipalAccessor
{
    /// <summary>Absent outside an authenticated request, never an invented user.</summary>
    ApiPrincipal? Current { get; }
    /// <summary>Restores the previous context on disposal; service instances have no shared process-global state.</summary>
    IDisposable Push(ApiPrincipal? principal);
}
