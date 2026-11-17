using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Rules;

/// <summary>No values are applied without a configured canonical-source retrieval and human confirmation.</summary>
public sealed record ApplyRules(string State, long TaxYear, string Actor, string? Note) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

internal sealed class ApplyRulesHandler : IRequestHandler<ApplyRules, object>
{
    public ValueTask<object> Handle(ApplyRules request, CancellationToken cancellationToken)
    {
        if (!request.State.Equals("GA", StringComparison.OrdinalIgnoreCase)) { throw new FeatureRefusalException(404, "Rulebook apply is GA-only."); }
        throw new FeatureRefusalException(503, "Web IQ retrieval is not configured; cannot retrieve the canonical source to apply.");
    }
}
