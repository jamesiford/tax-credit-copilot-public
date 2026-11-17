using System.Text.Json.Nodes;
using TaxCredit.Application.Features.ReadsCalc.Portfolio;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using static TaxCredit.Application.Features.Ai.Capabilities.Bindings.CapabilityBindingValues;

namespace TaxCredit.Application.Features.Ai.Capabilities.Bindings;

/// <summary>Stored eligibility decides membership; only the certified fragility function computes cushions.</summary>
public sealed class CapabilityRiskReads(ReadsStoredPortfolioBriefs stored, Func<ClientRunResolver> resolver, IGoldReadPort gold)
{
    internal CapabilityRead Read(JsonObject args)
    {
        IReadOnlyDictionary<string, object?>? run = null;
        var method = Text(args, "method") is null or "both" ? "min_max" : Text(args, "method")!;
        var resolved = resolver().ResolveStatute(Client(args), Text(args, "state"), Year(args), Text(args, "program_code"), true);
        var facts = Object(stored.JobsAtRisk(resolver(), Client(args), resolved.State, Year(args), method,
            resolved.ProgramCode, row => run = row));
        if (facts["declined"] is not null) { throw new CapabilityException(404, "year_not_authored", facts["declined"]!.GetValue<string>()); }
        if (facts["calculated"]?.GetValue<bool>() != true && run is not null)
        {
            facts = ZeroPopulation(args, resolved, method) ?? facts;
        }
        return new(facts, CapabilityDirectReads.RunEvidence(run is null ? null : Object(run), "tcc_gold"),
            UserOnlyFacts: facts["cohort"] is JsonArray { Count: > 0 } ? ["cohort"] : []);
    }

    private JsonObject? ZeroPopulation(JsonObject args, ResolvedStatute resolved, string method)
    {
        var read = gold.AtRisk(Client(args), Year(args), method, new RiskOptions(
            PortfolioValues.Number(resolved.Floors.MinWeeklyHours),
            PortfolioValues.Number(resolved.Floors.MinWeeklyWages), ProgramCode: resolved.ProgramCode));
        if (read.GetValueOrDefault("counts") is not IReadOnlyDictionary<string, object?> counts ||
            !counts.TryGetValue("eligible_count", out var eligible) || eligible is null ||
            Convert.ToInt64(eligible, System.Globalization.CultureInfo.InvariantCulture) != 0 ||
            !counts.TryGetValue("evaluated", out var evaluated) || evaluated is null)
        {
            return null;
        }
        var population = new PyDict().Add("eligible", 0L).Add("evaluated", evaluated);
        var facts = Object(Proximity.FragileCohort([], resolved.Floors, population: population));
        facts["calculated"] = true;
        facts["client_id"] = Client(args);
        facts["tax_year"] = Year(args);
        facts["state"] = resolved.State;
        facts["program_code"] = resolved.ProgramCode;
        facts["method"] = method;
        return facts;
    }
}
