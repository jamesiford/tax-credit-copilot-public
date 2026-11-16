using Azure.Core;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.ServiceDefaults.Hosting;

internal sealed class CredentialSqlTokens(TokenCredential credential) : IEntraSqlTokenProvider
{
    public async ValueTask<SqlAccessToken> Acquire(string scope, CancellationToken cancellationToken)
    {
        var token = await credential.GetTokenAsync(new TokenRequestContext([scope]), cancellationToken).ConfigureAwait(false);
        return new SqlAccessToken(token.Token, token.ExpiresOn);
    }
}
