using TaxCredit.Application.Messaging;
using TaxCredit.Domain.Claims;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Claims;

/// <summary>Answers what was believed before and after each decision.</summary>
public sealed record GetCellHistory(long ClientId, string ProgramCode, long TaxYear) : IQuery<object>;

internal sealed class GetCellHistoryHandler(IClaimRepository repository) : IRequestHandler<GetCellHistory, object>
{
    public ValueTask<object> Handle(GetCellHistory request, CancellationToken cancellationToken) =>
        ValueTask.FromResult<object>(new
        {
            current = (repository.Current(request.ClientId, request.ProgramCode, request.TaxYear)
                ?? throw new FeatureRefusalException(404, "No claim recorded for this cell.")).ToDict(),
            history = repository.History(request.ClientId, request.ProgramCode, request.TaxYear).Select(c => c.ToDict()),
        });
}
