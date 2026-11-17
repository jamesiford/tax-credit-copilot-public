using System.Globalization;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.DraftsRuns;

internal static class DraftScaffold
{
    private const string Todo = "TODO: fill from a cited source; not verified";

    internal static PyDict Base(string code, string state, string name) => new PyDict()
        .Add("_prototype_verification", "DRAFT skeleton. No value here is verified. Fill every null from a cited source, validate, then have it reviewed before any real client use.")
        .Add("rule_pack_version", "0.0.1")
        .Add("jurisdiction", new PyDict().Add("level", "state").Add("code", state).Add("name", name))
        .Add("credit", new PyDict().Add("code", code).Add("name", name).Add("statutory_citation", Todo))
        .Add("tax_year_convention", Flagged().Add("label", null).Add("regulation", null))
        .Add("filing", Flagged().Add("window", Todo).Add("cycle", "annual"))
        .Add("thresholds", Flagged().Add("minimum_new_jobs", null))
        .Add("benefit", Flagged().Add("amount_per_qualifying_job_usd", null).Add("benefit_period_years", null).Add("carryforward_years", null).Add("currency", "USD"))
        .Add("one_zero", Flagged().Add("min_weekly_hours", null).Add("min_weekly_wages", null).Add("wage_basis", "regular")
            .Add("geographic_granularity", "statewide").Add("pt_aggregation", false).Add("headcount_unit_field", "Worksite_ID")
            .Add("entity_combination", "permitted").Add("wage_floor_basis", Flagged().Add("source_tax_year", null).Add("annualized_wage_usd", null)));

    internal static PyDict Years(string code, string state, string name, IEnumerable<long> years)
    {
        var documents = new PyDict();
        foreach (var year in years.Distinct().Order())
        {
            var document = Base(code, state, name);
            document.Set("tax_year", year).Set("rule_pack_version", $"0.0.1+ty{year}")
                .Set("_year_provenance", new PyDict().Add("source", Todo).Add("adr", "ADR-005"));
            documents.Add(year.ToString(CultureInfo.InvariantCulture), document);
        }
        return documents;
    }

    private static PyDict Flagged() => new PyDict().Add("_prototype_verify", true);
}
