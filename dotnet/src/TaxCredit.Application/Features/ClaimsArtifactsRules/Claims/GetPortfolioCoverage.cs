using TaxCredit.Application.Messaging;
using TaxCredit.Domain.Claims;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Claims;

/// <summary>Keeps exposure and opportunity separate across client partitions.</summary>
public sealed record GetPortfolioCoverage(long? TaxYear) : IQuery<object>;

internal sealed class GetPortfolioCoverageHandler(IClaimRepository repository) : IRequestHandler<GetPortfolioCoverage, object>
{
    public ValueTask<object> Handle(GetPortfolioCoverage request, CancellationToken cancellationToken)
    {
        var claims = repository.PortfolioCoverage(taxYears: request.TaxYear is { } year ? [year] : null);
        return ValueTask.FromResult<object>(new
        {
            clients = Coverage.GroupByClient(claims).OrderBy(g => g.ClientId).Select(g => new
            {
                client_id = g.ClientId,
                cells = Coverage.Matrix(g.Claims, repository.Engagements(g.ClientId)
                    .ToDictionary(e => e.ProgramCode, e => (EngagementScope?)e.Scope, StringComparer.Ordinal)),
                totals = Coverage.Totals(g.Claims),
            }),
            totals = Coverage.Totals(claims),
        });
    }
}
