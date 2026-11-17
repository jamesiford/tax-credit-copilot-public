using Azure.Core;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Auth;

/// <summary>The root injects its credential; construction performs no discovery or token call.</summary>
public sealed class EntraTokenSource(TokenCredential credential) : IModelTokenSource
{
    /// <inheritdoc/>
    public async ValueTask<ModelAccessToken> AcquireAsync(string audience, CancellationToken cancellationToken)
    {
        try
        {
            var token = await credential.GetTokenAsync(
                new TokenRequestContext([CachedTokenAuth.NormalizeAudience(audience) + "/.default"]),
                cancellationToken).ConfigureAwait(false);
            return new(token.Token, audience, token.ExpiresOn);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (Exception) { throw new ModelException(ModelErrorKind.Authentication, "entra_token_failed"); }
    }
}
