using System.Globalization;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Portfolio;

internal static class PortfolioRows
{
    internal static string Outcome(ProgramClaim claim, IReadOnlyDictionary<string, EngagementScope?> scopes) =>
        scopes.GetValueOrDefault(claim.ProgramCode) == EngagementScope.OutOfScope
        && claim.Outcome is Domain.Claims.Outcome.Unclaimed or Domain.Claims.Outcome.NotAssessed
            ? "out_of_scope" : claim.Outcome.Value();

    internal static bool Matches(ProgramClaim claim, IReadOnlyDictionary<string, EngagementScope?> scopes, GetPortfolio request) =>
        (string.IsNullOrEmpty(request.Outcome) || Outcome(claim, scopes) == request.Outcome)
        && (string.IsNullOrEmpty(request.Scope) || scopes.GetValueOrDefault(claim.ProgramCode)?.Value() == request.Scope)
        && (request.Near is null || request.Near == (claim.Status == ClaimStatus.NotAssessed || claim.NearThreshold == true))
        && (string.IsNullOrEmpty(request.Status) || request.Status == claim.Status.Value());

    internal static PyDict Ranked(ProgramClaim claim, SourceAccount? account, IReadOnlyDictionary<string, EngagementScope?> scopes,
        IReadOnlyList<ProgramClaim> history, RuleLibrary rules)
    {
        var item = claim.ToDict().Add("engagement_scope", scopes.GetValueOrDefault(claim.ProgramCode)?.Value())
            .Add("effective_outcome", Outcome(claim, scopes)).Add("gap_jobs", claim.JobsToThreshold)
            .Add("one_more_job_qualifies", claim.JobsToThreshold is <= 1).Add("client_name", account?.Name)
            .Add("industry", Industry(account, rules));
        if (ClaimReadings.DecliningReading(history) is { } trend)
        {
            item.Add("trend", trend);
            if (claim.PriorityBand.Rank() > PriorityBand.Declining.Rank())
            {
                item.Set("priority_band", "declining").Set("priority_rank", PriorityBand.Declining.Rank());
            }
        }
        return item;
    }

    internal static PyDict? Unassessed(SourceAccount account, IReadOnlyDictionary<string, EngagementScope?> scopes,
        GetPortfolio request, RuleLibrary rules, PyDateTime now)
    {
        var calculable = rules.LoadRegistry().Active().Where(e => e.Level != "federal" && rules.AuthoredYears(e.PackFile).Count > 0).ToArray();
        var code = request.Program?.ToUpperInvariant() ?? scopes.Keys.FirstOrDefault()
            ?? (calculable.Length == 1 ? calculable[0].Code : null);
        if (code is null) { return null; }
        var claim = ProgramClaim.Create(new ClaimSpec
        {
            ClaimId = "",
            ClientId = account.AccountId,
            ProgramCode = code,
            TaxYear = request.Year ?? 0,
            EffectiveFrom = now,
        });
        var item = Ranked(claim, account, scopes, [], rules);
        item.Set("effective_outcome", "not_assessed");
        foreach (var key in new[] { "identified_usd", "claimed_usd", "certified_usd", "variance_usd", "opportunity_usd" }) { item.Set(key, null); }
        return item;
    }

    private static object? Industry(SourceAccount? account, RuleLibrary rules)
    {
        if (account?.IndustryTypeId is not { } id) { return null; }
        var seed = rules.LoadPack("lookups/industry_type.v1.json");
        return seed.TryGetValue("entries", out var entries) && entries is PyDict map
            && map.TryGetValue(id.ToString(CultureInfo.InvariantCulture), out var value) ? value : null;
    }
}
