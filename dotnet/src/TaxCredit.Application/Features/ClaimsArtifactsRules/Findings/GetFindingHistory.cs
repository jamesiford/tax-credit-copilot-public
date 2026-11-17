using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Findings;

/// <summary>Reads all superseded decisions in the selected client partition.</summary>
public sealed record GetFindingHistory(long ClientId, string FindingId) : IQuery<object>;

internal sealed class GetFindingHistoryHandler(IFindingRepository repository) : IRequestHandler<GetFindingHistory, object>
{
    public ValueTask<object> Handle(GetFindingHistory request, CancellationToken cancellationToken) =>
        ValueTask.FromResult<object>(new PyDict().Add("finding_id", request.FindingId)
            .Add("history", repository.History(request.ClientId, request.FindingId).Select(r => r.ToDict()).ToArray()));
}
