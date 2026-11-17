using System.Text.Json;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Domain.Claims;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Claims;

/// <summary>Appends a decision while retaining the complete prior belief.</summary>
public sealed record TransitionClaim(long ClientId, string ProgramCode, long TaxYear, JsonElement Body, string Actor)
    : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

internal sealed class TransitionClaimHandler(IClaimRepository repository, IClock clock, IIdSource ids)
    : IRequestHandler<TransitionClaim, object>
{
    public ValueTask<object> Handle(TransitionClaim request, CancellationToken cancellationToken)
    {
        var current = repository.Current(request.ClientId, request.ProgramCode, request.TaxYear)
            ?? throw new FeatureRefusalException(404, "No recorded claim to transition.");
        var b = request.Body;
        var claim = current.TransitionTo(ClaimEnumExtensions.StatusFromValue(FeatureValues.Text(b, "status")!),
            new TransitionOptions
            {
                DecidedBy = request.Actor,
                DeclineReason = FeatureValues.Text(b, "decline_reason"),
                ClaimedUsd = FeatureValues.Money(b, "claimed_usd"),
                CertifiedUsd = FeatureValues.Money(b, "certified_usd"),
                FilingReference = FeatureValues.Text(b, "filing_reference"),
                Provenance = FeatureValues.Text(b, "provenance") is { } p ? ClaimEnumExtensions.ProvenanceFromValue(p) : null,
            }, new ClaimClock(() => ids.NewId().ToString(), () => FeatureValues.Now(clock)));
        return ValueTask.FromResult<object>(repository.Record(claim).ToDict());
    }
}
