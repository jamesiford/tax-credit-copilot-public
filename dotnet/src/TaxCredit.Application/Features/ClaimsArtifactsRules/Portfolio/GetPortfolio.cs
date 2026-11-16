using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Portfolio;

/// <summary>One actionable stored cell per client, with history kept outside the year filter.</summary>
public sealed record GetPortfolio(long? Year, string? Program, string? Outcome, string? Scope, bool? Near, string? Status,
    string Sort, string Order, int Limit, int Offset) : IQuery<object>;

internal sealed class GetPortfolioHandler(IClaimRepository repository, ISourceReader source, RuleLibrary rules,
    IClock clock) : IRequestHandler<GetPortfolio, object>
{
    public ValueTask<object> Handle(GetPortfolio request, CancellationToken cancellationToken)
    {
        if (request.Scope is not (null or "" or "in_scope" or "out_of_scope" or "prospective"))
        {
            throw new FeatureRefusalException(422, "Unknown engagement scope.");
        }
        var all = repository.PortfolioCoverage().Where(c => string.IsNullOrEmpty(request.Program)
            || c.ProgramCode.Equals(request.Program, StringComparison.OrdinalIgnoreCase)).ToArray();
        var grouped = all.Where(c => request.Year is null || c.TaxYear == request.Year).GroupBy(c => c.ClientId).OrderBy(g => g.Key).ToArray();
        var accounts = source.ListAccounts();
        var byId = accounts.ToDictionary(a => a.AccountId);
        var footprint = source.Footprint();
        var priceable = rules.LoadRegistry().Active().Where(e => e.State is not null && rules.AuthoredYears(e.PackFile).Count > 0)
            .Select(e => e.State!).ToHashSet(StringComparer.Ordinal);
        var descending = request.Order.Equals("desc", StringComparison.OrdinalIgnoreCase);
        var ranked = new List<PyDict>();
        foreach (var group in grouped)
        {
            var scopes = Scopes(group.Key);
            var candidates = group.Where(c => PortfolioRows.Matches(c, scopes, request)).ToArray();
            var chosen = descending ? candidates.OrderByDescending(c => Score(c, request)).FirstOrDefault()
                : candidates.OrderBy(c => Score(c, request)).FirstOrDefault();
            if (chosen is null) { continue; }
            ranked.Add(PortfolioRows.Ranked(chosen, byId.GetValueOrDefault(group.Key), scopes,
                all.Where(c => c.ClientId == group.Key).ToArray(), rules));
        }
        var unassessed = new List<PyDict>();
        if (request.Outcome is null or "not_assessed" && request.Status is null or "not_assessed" && request.Near != false)
        {
            var assessedIds = grouped.Select(g => g.Key).ToHashSet();
            foreach (var account in accounts.Where(a => !assessedIds.Contains(a.AccountId)).OrderBy(a => a.Name, StringComparer.Ordinal))
            {
                var scopes = Scopes(account.AccountId);
                if (!string.IsNullOrEmpty(request.Scope) && !scopes.Values.Any(s => s?.Value() == request.Scope)) { continue; }
                if (PortfolioRows.Unassessed(account, scopes, request, rules, FeatureValues.Now(clock)) is { } row) { unassessed.Add(row); }
            }
        }
        var rows = PortfolioOrdering.Sort(ranked, request.Sort, descending).Concat(unassessed).ToArray();
        foreach (var row in rows)
        {
            var states = footprint.GetValueOrDefault((long)row["client_id"]!) ?? [];
            row.Add("states", states).Add("priceable_states", states.Where(priceable.Contains).ToArray());
        }
        return ValueTask.FromResult<object>(new
        {
            items = rows.Skip(request.Offset).Take(request.Limit).ToArray(),
            total = rows.Length,
            limit = request.Limit,
            offset = request.Offset,
            sort = PortfolioOrdering.Name(request.Sort),
            order = descending ? "desc" : "asc",
            year = request.Year,
            program = request.Program,
            outcome = request.Outcome,
            scope = request.Scope,
            near = request.Near,
            status = request.Status,
            total_clients = accounts.Count == 0 ? rows.Length : accounts.Count,
            assessed_clients = grouped.Length,
            unavailable_clients = 0,
            degraded = Array.Empty<object>(),
            unassessed_clients = unassessed.Count,
            _note = "One row per client, with the most actionable matching cell surfaced. Ranking is by the jobs gap when possible, because a cell worth $0 can still be the one to call. Clients never assessed are included with null money \u2014 not zero \u2014 and sort after the ranked rows.",
        });
    }

    private Dictionary<string, EngagementScope?> Scopes(long id) => repository.Engagements(id)
        .ToDictionary(e => e.ProgramCode, e => (EngagementScope?)e.Scope, StringComparer.Ordinal);

    private static double Score(ProgramClaim claim, GetPortfolio request) => PortfolioOrdering.Value(
        claim.ToDict().Add("gap_jobs", claim.JobsToThreshold), request.Sort, request.Order.Equals("desc", StringComparison.OrdinalIgnoreCase));
}
