using Azure.Core;
using Azure.Identity;

namespace TaxCredit.Infrastructure.Ai.Artifacts;

internal sealed class BlobTokenCredential(TokenCredential credential, string audience) : TokenCredential
{
    public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken) =>
        credential.GetToken(CanonicalContext(requestContext), cancellationToken);

    public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken) =>
        credential.GetTokenAsync(CanonicalContext(requestContext), cancellationToken);

    private TokenRequestContext CanonicalContext(TokenRequestContext context)
    {
        const string suffix = "/.default";
        if (context.Scopes.Length != 1 || !context.Scopes[0].EndsWith(suffix, StringComparison.Ordinal) ||
            !string.Equals(context.Scopes[0][..^suffix.Length].TrimEnd('/'), audience, StringComparison.Ordinal))
        {
            throw new AuthenticationFailedException("The requested token audience is not the configured Blob audience.");
        }
        return new TokenRequestContext([audience + suffix], context.ParentRequestId,
            context.Claims, context.TenantId, context.IsCaeEnabled);
    }
}
