using TaxCredit.Application.Messaging;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Rules;

/// <summary>Names the unavailable external extraction instead of fabricating a proposed rulebook.</summary>
public sealed record GetRuleProposals(string State, long TaxYear) : IQuery<object>;

internal sealed class GetRuleProposalsHandler : IRequestHandler<GetRuleProposals, object>
{
    public ValueTask<object> Handle(GetRuleProposals request, CancellationToken cancellationToken)
    {
        if (!request.State.Equals("GA", StringComparison.OrdinalIgnoreCase)) { throw new FeatureRefusalException(404, "Rulebook proposals are GA-only."); }
        return ValueTask.FromResult<object>(new PyDict().Add("state", "GA").Add("tax_year", request.TaxYear)
            .Add("web_iq_status", "NEEDS_KEY").Add("message", "Web IQ key not configured \u2014 set WEBIQ_API_KEY to retrieve the DCA ranking memo.")
            .Add("schedule_diff", Array.Empty<object>()).Add("county_moves", Array.Empty<object>()).Add("meridiancore_impact", Array.Empty<object>()));
    }
}
