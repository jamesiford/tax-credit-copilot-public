using TaxCredit.Application.Messaging;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Rules;

/// <summary>Returns the captured cited config, never a successful-looking live retrieval.</summary>
public sealed record GetIngestedRules(string State, long? TaxYear) : IQuery<object>;

internal sealed class GetIngestedRulesHandler(CapturedRules captured) : IRequestHandler<GetIngestedRules, object>
{
    public ValueTask<object> Handle(GetIngestedRules request, CancellationToken cancellationToken)
    {
        var config = captured.Load(request.State);
        return ValueTask.FromResult<object>(new PyDict().Add("state", request.State.ToUpperInvariant())
            .Add("program", RuleCatalogue.Get(config, "program")).Add("credit_name", RuleCatalogue.Get(config, "credit_name"))
            .Add("ingestion", RuleCatalogue.Get(config, "ingestion")).Add("config", config)
            .Add("provenance", CapturedRules.Provenance(config, request.TaxYear))
            .Add("source", "AI-01/A5 RulesIngestionAgent \u2014 Web IQ retrieval, per-value citations (GOV-01)."));
    }
}
