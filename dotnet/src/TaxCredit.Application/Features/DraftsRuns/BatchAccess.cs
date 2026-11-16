using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Visibility is resolved before totals, paging and queue mutations.</summary>
public sealed class BatchAccess(IRunBatchRepository repository, IClientAuthorizer authorizer, IApiPrincipalAccessor principals)
{
    /// <summary>Unknown and wholly invisible batches both remain not found.</summary>
    public async ValueTask<(RunBatch Batch, IReadOnlyList<RunBatchItem> Items)> Read(string id, CancellationToken cancellationToken)
    {
        var batch = repository.Get(id) ?? throw Missing();
        var items = AllItems(id);
        var allowed = new Dictionary<long, bool>();
        foreach (var client in items.Select(i => i.ClientId).Distinct())
        {
            allowed[client] = await authorizer.IsAuthorizedAsync(principals.Current ?? ApiPrincipal.Anonymous, client, cancellationToken).ConfigureAwait(false);
        }
        var mine = items.Where(i => allowed[i.ClientId]).ToArray();
        if (mine.Length == 0) { throw Missing(); }
        if (mine.Length == items.Count) { return (batch, mine); }
        var byStatus = mine.GroupBy(i => i.Status.Value()).ToDictionary(g => g.Key, g => (long)g.Count(), StringComparer.Ordinal);
        var counts = new PyDict().Add("items_total", (long)mine.Length).Add("items_queued", Count(ItemStatus.Queued))
            .Add("items_running", Count(ItemStatus.Leased) + Count(ItemStatus.Running)).Add("items_succeeded", Count(ItemStatus.Succeeded))
            .Add("items_skipped", Count(ItemStatus.SkippedNoPayroll) + Count(ItemStatus.SkippedUnchanged))
            .Add("items_failed", Count(ItemStatus.Failed)).Add("items_cancelled", Count(ItemStatus.Cancelled));
        var clients = mine.Select(i => i.ClientId).Distinct().Order().ToArray();
        var spec = new PyDict();
        foreach (var pair in batch.ScopeSpec) { spec.Add(pair.Key, pair.Value); }
        spec.Set("client_count", (long)clients.Length);
        spec.Set("clients_sha256", BatchPlanner.ClientDigest(clients));
        if (spec.ContainsKey("program_items")) { spec.Set("program_items", (long)mine.Select(i => (i.ClientId, i.ProgramCode)).Distinct().Count()); }
        if (spec.ContainsKey("client_ids")) { spec.Set("client_ids", clients.Cast<object?>().ToList()); }
        return (batch with
        {
            Counts = counts,
            Status = RunStateMachine.BatchStatusOf(byStatus, batch.CancelRequested),
            ScopeSpec = spec,
            DryRunSummary = new()
        }, mine);

        long Count(ItemStatus status) => byStatus.GetValueOrDefault(status.Value());
    }

    /// <summary>A batch-wide mutation cannot silently affect clients hidden from the caller.</summary>
    public async ValueTask RequireAll(string id, CancellationToken cancellationToken)
    {
        _ = repository.Get(id) ?? throw Missing();
        foreach (var client in AllItems(id).Select(i => i.ClientId).Distinct())
        {
            if (!await authorizer.IsAuthorizedAsync(principals.Current ?? ApiPrincipal.Anonymous, client, cancellationToken).ConfigureAwait(false))
            {
                throw new AuthRefusalException(403, "client_refused", "Not authorized to change every client in this batch.");
            }
        }
    }

    internal List<RunBatchItem> AllItems(string id)
    {
        var all = new List<RunBatchItem>();
        while (true)
        {
            var (items, total) = repository.ListItems(id, null, 500, all.Count);
            all.AddRange(items);
            if (items.Count == 0 || all.Count >= total) { return all; }
        }
    }

    internal static DraftsRunsRefusalException Missing() => new(404, "Unknown run batch.");
}
