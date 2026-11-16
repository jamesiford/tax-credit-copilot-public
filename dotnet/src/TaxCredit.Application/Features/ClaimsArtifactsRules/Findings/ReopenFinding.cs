using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Findings;

/// <summary>Withdraws a decision without deleting its actor, reason or reopening audit.</summary>
public sealed record ReopenFinding(string FindingId, long ClientId, string Actor) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

internal sealed class ReopenFindingHandler(IFindingRepository repository, IClock clock) : IRequestHandler<ReopenFinding, object>
{
    public ValueTask<object> Handle(ReopenFinding request, CancellationToken cancellationToken)
    {
        repository.Reopen(request.ClientId, request.FindingId, request.Actor, FeatureValues.Now(clock));
        return ValueTask.FromResult<object>(new PyDict().Add("finding_id", request.FindingId).Add("resolution", null).Add("requires_decision", true));
    }
}
