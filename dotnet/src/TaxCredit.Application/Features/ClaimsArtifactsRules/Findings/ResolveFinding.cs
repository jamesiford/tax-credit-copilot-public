using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Findings;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Findings;

/// <summary>Appends an attributed finding decision, not an ingestion-QC instruction.</summary>
public sealed record ResolveFinding(string FindingId, long ClientId, long TaxYear, string Resolution,
    string? KeepWorksite, string? Note, string Actor) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

internal sealed class ResolveFindingHandler(IFindingRepository repository, IClock clock) : IRequestHandler<ResolveFinding, object>
{
    public ValueTask<object> Handle(ResolveFinding request, CancellationToken cancellationToken)
    {
        if (string.IsNullOrEmpty(request.FindingId) || request.Resolution is not ("accept" or "assign" or "drop" or "flag")
            || request.Resolution == "assign" && string.IsNullOrEmpty(request.KeepWorksite))
        {
            throw new FeatureRefusalException(422, "assign requires keep_worksite; resolution must be accept, assign, drop or flag.");
        }
        return ValueTask.FromResult<object>(repository.Record(new FindingResolution
        {
            FindingId = request.FindingId,
            ClientId = request.ClientId,
            TaxYear = request.TaxYear,
            Resolution = request.Resolution,
            Detail = string.IsNullOrEmpty(request.KeepWorksite) ? null : new PyDict().Add("keep_worksite", request.KeepWorksite),
            Note = request.Note,
            DecidedBy = request.Actor,
            DecidedAt = FeatureValues.Now(clock).IsoFormat(),
        }).ToDict());
    }
}
