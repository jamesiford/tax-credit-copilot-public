using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Domain.Claims;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Claims;

/// <summary>Records who accepted or declined the mandate, independently of computed credit.</summary>
public sealed record SetEngagement(long ClientId, string ProgramCode, string Scope, string? Note, string Actor)
    : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

internal sealed class SetEngagementHandler(IClaimRepository repository, IClock clock) : IRequestHandler<SetEngagement, object>
{
    public ValueTask<object> Handle(SetEngagement request, CancellationToken cancellationToken)
    {
        var now = FeatureValues.Now(clock);
        return ValueTask.FromResult<object>(repository.SetEngagement(new ProgramEngagement
        {
            ClientId = request.ClientId,
            ProgramCode = request.ProgramCode,
            Scope = ClaimEnumExtensions.ScopeFromValue(request.Scope),
            Note = request.Note,
            SetBy = request.Actor,
            SetAt = now,
            EffectiveFrom = now,
        }).ToDict());
    }
}
