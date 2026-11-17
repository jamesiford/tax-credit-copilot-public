using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Rules;

/// <summary>The mutating GET remains a write in the authorization pipeline.</summary>
public sealed record RefreshRules(string State, bool Live, string Actor) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

internal sealed class RefreshRulesHandler(CapturedRules captured) : IRequestHandler<RefreshRules, object>
{
    public ValueTask<object> Handle(RefreshRules request, CancellationToken cancellationToken)
    {
        var state = request.State.ToUpperInvariant();
        if (state is not ("GA" or "TN")) { throw new FeatureRefusalException(404, "Refresh is available for GA and TN."); }
        if (request.Live) { throw new FeatureRefusalException(503, "Live rule retrieval is not configured in this host."); }
        var config = captured.Load(state);
        var ingestion = RuleCatalogue.Map(config, "ingestion");
        var web = RuleCatalogue.Map(ingestion, "web_iq");
        var parameters = RuleCatalogue.Map(config, "parameters") ?? new PyDict();
        var urls = parameters.Select(p => RuleCatalogue.Get(RuleCatalogue.Map(p.Value as PyDict, "source"), "url") as string)
            .OfType<string>().Where(u => u.Length > 0).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal);
        var lastChecked = RuleCatalogue.Get(web, "_note") is string { Length: > 0 } ? RuleCatalogue.Get(ingestion, "captured_at") : null;
        return ValueTask.FromResult<object>(new PyDict().Add("state", state).Add("mode", "captured")
            .Add("sources", urls.Select(url => new PyDict().Add("url", url).Add("reachable", null).Add("verified", null).Add("last_checked", lastChecked)).ToArray())
            .Add("parameter_count", parameters.Count).Add("source", "AI-03 LegislativeMonitorAgent \u2014 source reachability + drift."));
    }
}
