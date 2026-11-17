using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;
using TaxCredit.Domain.Warehouse;
using TaxCredit.Infrastructure.Persistence.Operational;
using TaxCredit.Infrastructure.Persistence.Sql;
using TaxCredit.ServiceDefaults.Hosting;

namespace TaxCredit.Api.Tests.DraftsRuns;

public sealed class LeaseBoundaryTests
{
    [Fact]
    public async Task Expiry_during_synchronous_compute_rolls_back_publication_and_completion_before_reclaim()
    {
        await using var host = await TestHost.Start();
        var paths = host.App.Services.GetRequiredService<RuntimePaths>();
        var database = PersistenceDatabase.Sqlite(paths.Database);
        var queue = new RunBatchRepository(database);
        var now = PyDateTime.FromIsoFormat("2026-01-01T00:00:00+00:00");
        queue.Create(new RunBatch
        {
            BatchId = "expiry",
            Kind = BatchKind.Calculate,
            ScopeKind = ScopeKind.One,
            ScopeSpec = new(),
            RequestedBy = "synthetic",
            RequestedAt = now
        }, [new RunBatchItem { ItemId = "expiry-item", BatchId = "expiry", ClientId = 1001, Seq = 0 }]);
        var item = Assert.Single(queue.Claim("owner", 1, 60, now));
        var manifests = new RunManifestRepository(database);
        var publication = new RunPublication(database, queue, manifests);
        var calls = 0;
        Assert.Throws<RunLeaseLost>(() => publication.Publish(item, "owner", "expired-run", () =>
        {
            calls++;
            manifests.Record(new RunManifest("expired-run", 1001, "GA_JTC", 2025,
                new DateOnly(2025, 1, 1), new DateOnly(2025, 12, 31), now, "success"));
            now = PyDateTime.FromIsoFormat("2026-01-01T00:01:01+00:00");
            return new ItemResult { Status = ItemStatus.Succeeded, RunId = "expired-run" };
        }, () => now, CancellationToken.None, leaseSeconds: 60));
        Assert.Equal(1, calls);
        var reopened = PersistenceDatabase.Sqlite(paths.Database);
        Assert.Null(new RunManifestRepository(reopened).Get("expired-run"));
        var persisted = new RunBatchRepository(reopened);
        Assert.Equal(ItemStatus.Leased, persisted.GetItem(1001, item.ItemId)!.Status);
        Assert.Equal(BatchStatus.Queued, persisted.Get(item.BatchId)!.Status);
        persisted.ReapExpired(now, 3);
        Assert.Single(persisted.Claim("next-owner", 1, 60, now));
    }
}
