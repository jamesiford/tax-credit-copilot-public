using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Applies portfolio filters to one candidate cell, then its client-level band, rather than mixing different cells' answers.</summary>
public sealed class BatchSelection(IClaimRepository claims, RuleLibrary rules)
{
    private readonly Dictionary<long, (IReadOnlyList<ProgramClaim> Claims, IReadOnlyList<ProgramEngagement> Engagements)> _reads = [];

    internal void CheckAvailable(IEnumerable<long> clients)
    {
        foreach (var client in clients) { _ = Read(client); }
    }

    /// <summary>Whether the filter has a state criterion, the only part of a filter that needs the payroll footprint.</summary>
    internal static bool NeedsStates(PyDict filter) => Text(filter, "state") is { Length: > 0 };

    internal bool Matches(long client, PyDict filter, IReadOnlyList<string> states)
    {
        if (Text(filter, "state") is { Length: > 0 } state && !states.Contains(state, StringComparer.OrdinalIgnoreCase)) { return false; }
        if (Present(filter, "unavailable") && GoldValues.Truthy(filter["unavailable"])) { return false; }
        var (all, engagements) = Read(client);
        var scopes = engagements.ToDictionary(e => e.ProgramCode, e => e.Scope, StringComparer.Ordinal);
        var history = all.Where(c => Text(filter, "program") is not { Length: > 0 } program || string.Equals(c.ProgramCode, program, StringComparison.OrdinalIgnoreCase)).ToArray();
        var held = history.Where(c => !Present(filter, "year") || PyEquality.Equal(c.TaxYear, filter["year"])).ToArray();
        var candidates = held.Where(c => CellMatches(c, scopes, filter)).OrderBy(c => c.PriorityBand.Rank())
            .ThenByDescending(c => c.IdentifiedUsd.ToDouble()).ToArray();
        if (held.Length > 0 && candidates.Length == 0) { return false; }
        var chosen = candidates.FirstOrDefault();
        if (chosen is null && !UnassessedMatches(filter, scopes)) { return false; }
        var band = chosen?.PriorityBand ?? PriorityBand.NotAssessed;
        if (chosen is not null && band.Rank() > PriorityBand.Declining.Rank() && ClaimReadings.DecliningReading(history) is not null)
        {
            band = PriorityBand.Declining;
        }
        var unassessed = chosen is null || chosen.Status == ClaimStatus.NotAssessed;
        return (!Present(filter, "unassessed") || unassessed == GoldValues.Truthy(filter["unassessed"]))
            && (!Present(filter, "band") || band.Value() == Text(filter, "band"));
    }

    private (IReadOnlyList<ProgramClaim> Claims, IReadOnlyList<ProgramEngagement> Engagements) Read(long client)
    {
        if (!_reads.TryGetValue(client, out var found)) { _reads[client] = found = (claims.Coverage(client), claims.Engagements(client)); }
        return found;
    }

    private static bool CellMatches(ProgramClaim claim, Dictionary<string, EngagementScope> scopes, PyDict filter)
    {
        var scope = scopes.TryGetValue(claim.ProgramCode, out var found) ? found.Value() : null;
        var outcome = scope == "out_of_scope" && claim.Outcome is Outcome.Unclaimed or Outcome.NotAssessed ? "out_of_scope" : claim.Outcome.Value();
        return (!Present(filter, "outcome") || outcome == Text(filter, "outcome"))
            && (!Present(filter, "scope") || scope == Text(filter, "scope"))
            && (!Present(filter, "status") || claim.Status.Value() == Text(filter, "status"))
            && (!filter.TryGetValue("near", out var near) || near is null || PyEquality.Equal(near, claim.Status == ClaimStatus.NotAssessed || claim.NearThreshold));
    }

    private bool UnassessedMatches(PyDict filter, IReadOnlyDictionary<string, EngagementScope> scopes) =>
        (!Present(filter, "outcome") || Text(filter, "outcome") == "not_assessed")
        && (!Present(filter, "status") || Text(filter, "status") == "not_assessed")
        && (!filter.TryGetValue("near", out var near) || near is not false)
        && (!Present(filter, "scope") || scopes.Values.Any(s => s.Value() == Text(filter, "scope")))
        && (Present(filter, "program") || scopes.Count > 0 || rules.LoadRegistry().Active().Count(e => rules.AuthoredYears(e.PackFile).Count > 0) == 1);

    private static bool Present(PyDict filter, string key) => filter.TryGetValue(key, out var value) && value is not null and not "";
    private static string? Text(PyDict filter, string key) => filter.TryGetValue(key, out var value) && value is not null ? GoldValues.Str(value) : null;
}
