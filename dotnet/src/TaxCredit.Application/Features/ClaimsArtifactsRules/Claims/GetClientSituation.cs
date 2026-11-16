using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Claims;

/// <summary>Builds the client brief only from recorded claims.</summary>
public sealed record GetClientSituation(long ClientId, long? TaxYear) : IQuery<object>;

internal sealed class GetClientSituationHandler(IClaimRepository repository, ISourceReader source) : IRequestHandler<GetClientSituation, object>
{
    public ValueTask<object> Handle(GetClientSituation request, CancellationToken cancellationToken)
    {
        var claims = repository.Coverage(request.ClientId, taxYears: request.TaxYear is { } y && y != 0 ? [y] : null);
        var result = new PyDict().Add("client_id", request.ClientId).Add("tax_year", request.TaxYear).Add("assessed", claims.Count > 0);
        if (claims.Count == 0)
        {
            result.Add("message", "No assessment has been run for this client"
                + (request.TaxYear is { } year && year != 0 ? $" in TY{year}" : "")
                + ". There is no figure to report \u2014 that is not the same as zero.");
        }
        else
        {
            foreach (var pair in CoverageSituation.Situation(claims)) { result.Add(pair.Key, pair.Value); }
        }
        result.Add("client_name", source.ListAccounts().FirstOrDefault(a => a.AccountId == request.ClientId)?.Name);
        return ValueTask.FromResult<object>(result);
    }
}
