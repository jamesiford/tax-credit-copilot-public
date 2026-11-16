using TaxCredit.Application.Messaging;
using TaxCredit.Domain.Claims;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Claims;

/// <summary>Publishes the domain vocabulary rather than a second UI-maintained copy.</summary>
public sealed record GetLifecycle : IQuery<object>;

internal sealed class GetLifecycleHandler : IRequestHandler<GetLifecycle, object>
{
    public ValueTask<object> Handle(GetLifecycle request, CancellationToken cancellationToken) =>
        ValueTask.FromResult<object>(new
        {
            statuses = Enum.GetValues<ClaimStatus>().Select(s => new { value = s.Value(), is_claimed = s.IsClaimed() }),
            provenance = Enum.GetValues<Provenance>().Select(p => new { value = p.Value(), verified = p.Verified() }),
            outcomes = Enum.GetValues<Outcome>().Select(o => o.Value()),
            engagement_scopes = Enum.GetValues<EngagementScope>().Select(s => s.Value()),
        });
}
