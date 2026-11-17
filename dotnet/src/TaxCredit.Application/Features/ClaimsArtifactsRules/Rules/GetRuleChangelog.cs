using TaxCredit.Application.Messaging;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Rules;

/// <summary>Reports no applied rulebooks while external apply is unavailable.</summary>
public sealed record GetRuleChangelog(string State) : IQuery<object>;

internal sealed class GetRuleChangelogHandler(CapturedRules captured) : IRequestHandler<GetRuleChangelog, object>
{
    public ValueTask<object> Handle(GetRuleChangelog request, CancellationToken cancellationToken)
    {
        captured.Load(request.State);
        return ValueTask.FromResult<object>(new PyDict().Add("state", request.State.ToUpperInvariant())
            .Add("applied_years", Array.Empty<object>()).Add("changelog", Array.Empty<object>()));
    }
}
