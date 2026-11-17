using Azure.Core;

namespace TaxCredit.Orchestrator.Boundary;

/// <summary>Service authentication is separate from the verified acting person's assertions.</summary>
public interface IServiceTokenProvider
{
    /// <summary>Obtain a service token for this call, never an inbound person's bearer token.</summary>
    ValueTask<string> GetTokenAsync(CancellationToken cancellationToken = default);
}

/// <summary>Uses the shared Azure credential abstraction; the credential owns token caching.</summary>
public sealed class AzureCredentialTokenProvider : IServiceTokenProvider
{
    private readonly TokenCredential credential;
    private readonly TokenRequestContext request;

    /// <summary>Composition supplies DefaultAzureCredential or an injectable synthetic credential.</summary>
    public AzureCredentialTokenProvider(TokenCredential credential, string scope)
    {
        ArgumentNullException.ThrowIfNull(credential);
        ArgumentException.ThrowIfNullOrWhiteSpace(scope);
        this.credential = credential;
        request = new TokenRequestContext([scope]);
    }

    /// <inheritdoc />
    public async ValueTask<string> GetTokenAsync(CancellationToken cancellationToken = default)
    {
        var token = await credential.GetTokenAsync(request, cancellationToken).ConfigureAwait(false);
        return token.Token;
    }
}
