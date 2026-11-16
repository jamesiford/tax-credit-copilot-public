using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Runs;
using TaxCredit.Infrastructure.Persistence.Operational;
using TaxCredit.Infrastructure.Persistence.Sql;
using TaxCredit.Infrastructure.Persistence.Tests.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.Operational;

public sealed class RunPublicationTests
{
    [Fact]
    public void An_ambiguous_acknowledgement_is_accepted_only_after_reopening_terminal_work_and_its_manifest()
    {
        using var store = new OperationalDatabase();
        var queue = new RunBatchRepository(store.Database);
        var item = Claim(queue);
        var manifests = new RunManifestRepository(store.Database);
        using var connection = new RecordingConnection { CommitError = new IOException("Synthetic lost acknowledgement") };
        var acknowledgement = new PersistenceDatabase(() => connection, new SqlServerDialect());
        var publication = new RunPublication(acknowledgement, queue, manifests);
        var calls = 0;
        publication.Publish(item, "owner", "committed", () =>
        {
            calls++;
            manifests.Record(ManifestOverrideTests.Manifest("committed", 11));
            return new ItemResult { Status = ItemStatus.Succeeded, RunId = "committed" };
        }, () => RunBatchRepositoryTests.At(1), CancellationToken.None);
        Assert.Equal(1, calls);
        Assert.Equal(1, connection.Commits);
        Assert.Equal(ItemStatus.Succeeded, new RunBatchRepository(store.Reopen()).GetItem(11, item.ItemId)!.Status);
        Assert.NotNull(new RunManifestRepository(store.Reopen()).Get("committed"));
    }

    [Fact]
    public void Reclaimed_work_reuses_its_durable_identity_and_an_accepted_manifest_without_recalculating()
    {
        using var store = new OperationalDatabase();
        var queue = new RunBatchRepository(store.Database);
        var manifests = new RunManifestRepository(store.Database);
        var publication = new RunPublication(store.Database, queue, manifests);
        var item = Claim(queue);
        Assert.Equal("stable", publication.Identity(item, "owner", RunBatchRepositoryTests.At(1), () => "stable"));
        manifests.Record(ManifestOverrideTests.Manifest("stable", 11));
        queue.ReapExpired(RunBatchRepositoryTests.At(61), 3);
        var reopened = store.Reopen();
        var next = new RunBatchRepository(reopened);
        item = next.Claim("next", 1, 60, RunBatchRepositoryTests.At(62)).Single();
        var recovered = new RunPublication(reopened, next, new RunManifestRepository(reopened));
        Assert.Equal("stable", recovered.Identity(item, "next", RunBatchRepositoryTests.At(62), () => throw new InvalidOperationException("allocated twice")));
        recovered.Publish(item, "next", "stable", () => throw new InvalidOperationException("calculated twice"),
            () => RunBatchRepositoryTests.At(62), CancellationToken.None);
        Assert.Equal(ItemStatus.Succeeded, next.GetItem(11, item.ItemId)!.Status);
        Assert.Equal("stable", next.GetItem(11, item.ItemId)!.RunId);
        Assert.Equal(BatchStatus.Succeeded, next.Get(item.BatchId)!.Status);
        Assert.Equal(1, manifests.Count());
    }

    [Fact]
    public void Cancellation_after_calculation_rolls_back_its_manifest_and_completion_together()
    {
        using var store = new OperationalDatabase();
        var queue = new RunBatchRepository(store.Database);
        var manifests = new RunManifestRepository(store.Database);
        var publication = new RunPublication(store.Database, queue, manifests);
        var item = Claim(queue);
        using var cancellation = new CancellationTokenSource();
        Assert.Throws<OperationCanceledException>(() => publication.Publish(item, "owner", "cancelled", () =>
        {
            manifests.Record(ManifestOverrideTests.Manifest("cancelled", 11));
            cancellation.Cancel();
            return new ItemResult { Status = ItemStatus.Succeeded, RunId = "cancelled" };
        }, () => RunBatchRepositoryTests.At(1), cancellation.Token));
        Assert.Null(new RunManifestRepository(store.Reopen()).Get("cancelled"));
        Assert.Equal(ItemStatus.Leased, new RunBatchRepository(store.Reopen()).GetItem(11, item.ItemId)!.Status);
        Assert.True(queue.Release(11, item.ItemId, "owner", RunBatchRepositoryTests.At(2)));
        Assert.Equal(0, queue.GetItem(11, item.ItemId)!.Attempts);
    }

    [Fact]
    public async Task Independent_publishers_cannot_commit_the_same_lease_twice()
    {
        using var store = new OperationalDatabase();
        var item = Claim(new RunBatchRepository(store.Database));
        var calls = 0;
        using var start = new Barrier(2);
        Task Publish() => Task.Run(() =>
        {
            var database = store.Reopen();
            var manifests = new RunManifestRepository(database);
            var publication = new RunPublication(database, new RunBatchRepository(database), manifests);
            start.SignalAndWait();
            try
            {
                publication.Publish(item, "owner", "once", () =>
                {
                    Interlocked.Increment(ref calls);
                    manifests.Record(ManifestOverrideTests.Manifest("once", 11));
                    return new ItemResult { Status = ItemStatus.Succeeded, RunId = "once" };
                }, () => RunBatchRepositoryTests.At(1), CancellationToken.None);
            }
            catch (RunLeaseLost) { }
        });
        await Task.WhenAll(Publish(), Publish());
        Assert.Equal(1, calls);
        Assert.Equal(1, new RunManifestRepository(store.Reopen()).Count());
        Assert.Equal(ItemStatus.Succeeded, new RunBatchRepository(store.Reopen()).GetItem(11, item.ItemId)!.Status);
    }

    [Fact]
    public void A_lost_or_expired_lease_is_refused_before_any_calculation()
    {
        using var store = new OperationalDatabase();
        var queue = new RunBatchRepository(store.Database);
        var item = Claim(queue);
        var publication = new RunPublication(store.Database, queue, new RunManifestRepository(store.Database));
        Assert.Throws<RunLeaseLost>(() => publication.Publish(item, "other", null, () => throw new NotSupportedException(),
            () => RunBatchRepositoryTests.At(1), CancellationToken.None));
        Assert.Throws<RunLeaseLost>(() => publication.Publish(item, "owner", null, () => throw new NotSupportedException(),
            () => RunBatchRepositoryTests.At(61), CancellationToken.None));
    }

    private static RunBatchItem Claim(RunBatchRepository queue)
    {
        var batch = RunBatchRepositoryTests.Batch("publication");
        queue.Create(batch, RunBatchRepositoryTests.Items(batch, 11));
        return queue.Claim("owner", 1, 60, RunBatchRepositoryTests.At(0)).Single();
    }
}
