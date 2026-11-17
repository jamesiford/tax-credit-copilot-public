using Azure.Core;
using Azure.Identity;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.ServiceDefaults.Hosting;

/// <summary>Recreating this credential drops its private Graph token cache after a permission-change denial.</summary>
internal sealed class RuntimeGraphTokens : IAuthAccessTokenProvider
{
    private readonly object _gate = new();
    private TokenCredential _credential = new DefaultAzureCredential();

    public async ValueTask<string> GetTokenAsync(string scope, CancellationToken cancellationToken = default)
    {
        TokenCredential credential;
        lock (_gate) { credential = _credential; }
        return (await credential.GetTokenAsync(new TokenRequestContext([scope]), cancellationToken).ConfigureAwait(false)).Token;
    }

    public bool Invalidate(string scope)
    {
        lock (_gate) { _credential = new DefaultAzureCredential(); }
        return true;
    }
}

internal sealed class RuntimeAuthClients : IDisposable
{
    internal HttpClient Jwks { get; } = new();
    internal HttpClient Graph { get; } = new();
    public void Dispose() { Jwks.Dispose(); Graph.Dispose(); }
}
