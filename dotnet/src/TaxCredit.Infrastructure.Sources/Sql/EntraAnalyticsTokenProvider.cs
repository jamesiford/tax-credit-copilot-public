using Azure.Core;
using Azure.Identity;
using TaxCredit.Application.Ports.Sources;

namespace TaxCredit.Infrastructure.Sources.Sql;

/// <summary>Credential selection stays in the host; only the database audience can be acquired by this source adapter.</summary>
public sealed class EntraAnalyticsTokenProvider(TokenCredential credential) : IAnalyticsTokenProvider
{
    /// <inheritdoc />
    public async Task<AnalyticsAccessToken> AcquireAsync(string scope, CancellationToken cancellationToken)
    {
        if (scope != AnalyticsConnectionFactory.DatabaseScope)
        {
            throw new ArgumentException("The analytics token provider accepts only the database scope.", nameof(scope));
        }
        try
        {
            var token = await credential.GetTokenAsync(new TokenRequestContext([scope]), cancellationToken).ConfigureAwait(false);
            return new AnalyticsAccessToken(token.Token, token.ExpiresOn);
        }
        catch (AuthenticationFailedException)
        {
            cancellationToken.ThrowIfCancellationRequested();
            throw new SourceUnavailable("source_token");
        }
        catch (HttpRequestException)
        {
            cancellationToken.ThrowIfCancellationRequested();
            throw new SourceUnavailable("source_token");
        }
    }
}
