using System.Globalization;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Rules;

internal sealed class CapturedRules(IIngestedConfigFiles files)
{
    internal PyDict Load(string state)
    {
        var file = state.ToUpperInvariant() switch
        {
            "GA" or "GA_JTC" => "ga_jtc.json",
            "TN" or "TN_JTC" => "tn_jtc.json",
            _ => null,
        };
        var text = file is null ? null : files.ReadText(file);
        return text is null ? throw new FeatureRefusalException(404, "No captured ingested rule config for this state.")
            : PyJson.Loads(text) as PyDict ?? throw new InvalidOperationException("The captured rule config must be an object.");
    }

    internal static PyDict[] Provenance(PyDict config, long? year)
    {
        var parameters = RuleCatalogue.Map(config, "parameters") ?? new PyDict();
        var rows = parameters.Where(p => p.Value is PyDict).Select(p => ProvenanceRow(p.Key, (PyDict)p.Value!)).ToList();
        if (year is { } y && RuleCatalogue.Map(RuleCatalogue.Map(config, "thresholds_by_year"), y.ToString(CultureInfo.InvariantCulture)) is { } block)
        {
            rows.Add(ProvenanceRow($"min_weekly_wages@{year}", block, "min_weekly_wages"));
        }
        return rows.ToArray();
    }

    private static PyDict ProvenanceRow(string name, PyDict node, string valueKey = "value")
    {
        var source = RuleCatalogue.Map(node, "source");
        return new PyDict().Add("parameter", name).Add("value", RuleCatalogue.Get(node, valueKey))
            .Add("authority", RuleCatalogue.Get(source, "authority")).Add("title", RuleCatalogue.Get(source, "title"))
            .Add("url", RuleCatalogue.Get(source, "url")).Add("artifact_sha256", RuleCatalogue.Get(source, "artifact_sha256"))
            .Add("retrieved_at", RuleCatalogue.Get(source, "retrieved_at")).Add("confidence", RuleCatalogue.Get(node, "confidence"))
            .Add("verify", RuleCatalogue.Get(node, "_prototype_verify") is true).Add("disc_ref", RuleCatalogue.Get(node, "_disc_ref"));
    }
}
