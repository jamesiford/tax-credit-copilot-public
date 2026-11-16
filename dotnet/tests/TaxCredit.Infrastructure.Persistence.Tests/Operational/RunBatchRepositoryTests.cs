using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;
using TaxCredit.Infrastructure.Persistence.Operational;

namespace TaxCredit.Infrastructure.Persistence.Tests.Operational;

public sealed class RunBatchRepositoryTests
{
    private static readonly PyDateTime Now = At(0);

    [Fact]
    public void CreateCountersPagesAndRequesterIdempotencySurviveReopening()
    {
        using var store = new OperationalDatabase();
        var repository = new RunBatchRepository(store.Database);
        Assert.Empty(repository.Claim("unused", 1000, 120, Now));
        var batch = Batch("a") with { IdempotencyKey = "same", SkipUnchanged = true };
        var created = repository.Create(batch, Items(batch, 11, 22, 33));
        Assert.Equal(3L, created.Counts["items_total"]);
        Assert.Equal(3L, created.Counts["items_queued"]);
        var restarted = new RunBatchRepository(store.Reopen());
        Assert.Equal(created, restarted.Get("a"));
        Assert.True(restarted.Get("a")!.SkipUnchanged);
        Assert.Equal(3, restarted.ListItems("a", null, 2, 0).Total);
        Assert.Equal(3, restarted.ListItems("a", "", 2, 0).Total);
        Assert.Equal([11L, 22L], restarted.ListItems("a", null, 2, 0).Items.Select(item => item.ClientId).ToArray());
        Assert.Empty(restarted.ListItems("a", null, 2, 20).Items);
        Assert.Single(restarted.ListBatches(10, 0).Items);
        Assert.Single(restarted.ListBatches(10, 0, "").Items);
        Assert.Null(restarted.FindByKey("same", "another"));
        Assert.Equal("a", restarted.FindByKey("same", "requester")!.BatchId);
        Assert.Equal("a", restarted.Create(Batch("b") with { IdempotencyKey = "same" }, Items(Batch("b"), 44)).BatchId);
        Assert.Single(restarted.ListBatches(10, 0).Items);
        Assert.Null(restarted.GetItem(22, "a-0"));
        Assert.Equal(11, restarted.GetItem(11, "a-0")!.ClientId);
    }

    [Fact]
    public async Task SeparateWorkerConnectionsCannotLeaseTwoItemsOfOneClient()
    {
        using var store = new OperationalDatabase();
        var first = new RunBatchRepository(store.Database);
        var second = new RunBatchRepository(store.Reopen());
        var batch = Batch("a");
        first.Create(batch, Items(batch, 11, 11, 22, 22));
        using var start = new Barrier(2);
        var one = Task.Run(() => { start.SignalAndWait(); return first.Claim("worker-a", 2, 120, Now); });
        var two = Task.Run(() => { start.SignalAndWait(); return second.Claim("worker-b", 2, 120, Now); });
        var leased = (await Task.WhenAll(one, two)).SelectMany(items => items).ToArray();
        Assert.Equal(2, leased.Length);
        Assert.Equal(2, leased.Select(item => item.ClientId).Distinct().Count());
        Assert.All(leased, item => Assert.Equal(1, item.Attempts));
        Assert.Equal(2, first.QueueHealth(Now).LiveLeases);
        Assert.Equal(2, first.QueueHealth(Now).Queued);
    }

    [Fact]
    public void LeaseOwnerAndTenantBindHeartbeatStartAndAtomicFinish()
    {
        using var store = new OperationalDatabase();
        var repository = new RunBatchRepository(store.Database);
        var batch = Batch("a");
        repository.Create(batch, Items(batch, 11));
        var item = repository.Claim("owner", 1, 10, Now).Single();
        Assert.False(repository.Heartbeat(22, item.ItemId, "owner", 10, At(5)));
        Assert.False(repository.Heartbeat(11, item.ItemId, "intruder", 10, At(5)));
        Assert.True(repository.Heartbeat(11, item.ItemId, "owner", 10, At(5)));
        Assert.True(repository.MarkRunning(11, item.ItemId, "owner", 2023, "GA_JTC", At(6)));
        Assert.False(repository.MarkRunning(11, item.ItemId, "owner", 2023, "GA_JTC", At(7)));
        Assert.False(repository.Finish(11, item.ItemId, "intruder", At(8), new ItemResult { Status = ItemStatus.Succeeded }, "a"));
        Assert.False(repository.Finish(11, item.ItemId, "owner", At(8), new ItemResult { Status = ItemStatus.Succeeded }, "wrong-batch"));
        Assert.True(repository.Finish(11, item.ItemId, "owner", At(8), new ItemResult { Status = ItemStatus.Succeeded, RunId = "run" }, "a"));
        var restarted = new RunBatchRepository(store.Reopen());
        Assert.Equal(BatchStatus.Succeeded, restarted.Get("a")!.Status);
        Assert.Equal(1L, restarted.Get("a")!.Counts["items_succeeded"]);
        Assert.Equal(0L, restarted.Get("a")!.Counts["items_running"]);
        Assert.Equal("run", restarted.GetItem(11, item.ItemId)!.RunId);
        Assert.Null(restarted.GetItem(11, item.ItemId)!.LeaseOwner);
    }

    [Fact]
    public void ExpiredOwnerCannotRenewFinishOrReleaseAndSpentAttemptsFail()
    {
        using var store = new OperationalDatabase();
        var repository = new RunBatchRepository(store.Database);
        var batch = Batch("a");
        repository.Create(batch, Items(batch, 11));
        var item = repository.Claim("dead", 1, 10, Now).Single();
        Assert.False(repository.Heartbeat(11, item.ItemId, "dead", 10, At(10)));
        Assert.False(repository.Finish(11, item.ItemId, "dead", At(10), new ItemResult { Status = ItemStatus.Succeeded }, "a"));
        Assert.False(repository.Release(11, item.ItemId, "dead", At(10)));
        Assert.Equal(["a"], repository.ReapExpired(At(10), 2));
        Assert.Equal(ItemStatus.Queued, repository.GetItem(11, item.ItemId)!.Status);
        repository.Claim("dead-again", 1, 10, At(10));
        repository.ReapExpired(At(20), 2);
        Assert.Equal(ItemStatus.Failed, repository.GetItem(11, item.ItemId)!.Status);
        Assert.Equal("worker", repository.GetItem(11, item.ItemId)!.ErrorDependency);
        Assert.Equal(BatchStatus.Failed, repository.Get("a")!.Status);
        Assert.Equal(1L, repository.Get("a")!.Counts["items_failed"]);
    }

    [Fact]
    public void BackoffWaitsAndReleaseRefundsOnlyOwnedAttempt()
    {
        using var store = new OperationalDatabase();
        var repository = new RunBatchRepository(store.Database);
        var batch = Batch("a");
        repository.Create(batch, Items(batch, 11));
        var item = repository.Claim("owner", 1, 120, Now).Single();
        Assert.False(repository.Requeue(22, item.ItemId, "owner", At(1), At(60), "sql", "busy"));
        Assert.True(repository.Requeue(11, item.ItemId, "owner", At(1), At(60), "sql", new string('x', 1200)));
        Assert.Empty(repository.Claim("other", 1, 120, At(59)));
        Assert.Single(repository.Claim("other", 1, 120, At(60)));
        Assert.False(repository.Release(11, item.ItemId, "owner", At(61)));
        Assert.True(repository.Release(11, item.ItemId, "other", At(61)));
        Assert.Equal(1, repository.GetItem(11, item.ItemId)!.Attempts);
        Assert.Equal(1000, repository.GetItem(11, item.ItemId)!.ErrorMessage!.Length);
    }

    [Fact]
    public void CancellationLeavesLeasedWorkAndRetryTouchesOnlyFailures()
    {
        using var store = new OperationalDatabase();
        var repository = new RunBatchRepository(store.Database);
        var batch = Batch("a");
        repository.Create(batch, Items(batch, 11, 22, 33));
        var leased = repository.Claim("owner", 1, 120, Now).Single();
        Assert.Equal(2, repository.Cancel("a", At(1)));
        Assert.Equal(ItemStatus.Leased, repository.GetItem(11, leased.ItemId)!.Status);
        Assert.Empty(repository.Claim("other", 3, 120, At(2)));
        repository.Finish(11, leased.ItemId, "owner", At(2), new ItemResult { Status = ItemStatus.Succeeded }, "a");
        Assert.Equal(BatchStatus.Partial, repository.Get("a")!.Status);
        Assert.Equal(0, repository.RetryFailed("a", At(3)));
        var otherBatch = Batch("b");
        repository.Create(otherBatch, Items(otherBatch, 11, 22));
        var items = repository.Claim("owner", 2, 120, At(4));
        repository.Finish(11, items[0].ItemId, "owner", At(5), new ItemResult { Status = ItemStatus.Failed }, "b");
        repository.Finish(22, items[1].ItemId, "owner", At(5), new ItemResult { Status = ItemStatus.Succeeded }, "b");
        Assert.Equal(1, repository.RetryFailed("b", At(6)));
        Assert.Equal(0, repository.GetItem(11, items[0].ItemId)!.Attempts);
        Assert.Equal(ItemStatus.Succeeded, repository.GetItem(22, items[1].ItemId)!.Status);
        Assert.Equal(BatchStatus.Running, repository.Get("b")!.Status);
    }

    [Fact]
    public void OrderingAndOpenIdenticalLookupUseStoredCanonicalScope()
    {
        using var store = new OperationalDatabase();
        var repository = new RunBatchRepository(store.Database);
        var early = Batch("early");
        var late = Batch("late") with { RequestedAt = At(1), ScopeSpec = new PyDict().Add("z", 1L).Add("a", 2L) };
        repository.Create(late, Items(late, 11));
        repository.Create(early, Items(early, 22));
        Assert.Equal("late", repository.FindOpenIdentical("calculate", "{\"z\":1,\"a\":2}", "requester")!.BatchId);
        Assert.Equal("late", repository.FindOpenIdentical("calculate", "{\"a\": 2, \"z\": 1}", "requester")!.BatchId);
        Assert.Null(repository.FindOpenIdentical("calculate", "{\"a\":2,\"z\":1}", "other"));
        Assert.Equal(22, repository.Claim("owner", 1, 120, At(2)).Single().ClientId);
        Assert.Equal(1, repository.StatusCounts("early")["leased"]);
        Assert.Equal(BatchStatus.Running, repository.Refresh("early", At(2)).Status);
    }

    [Fact]
    public void InvalidCreateRollsBackBatchAndEmptyBatchHasExplicitCompletedState()
    {
        using var store = new OperationalDatabase();
        var repository = new RunBatchRepository(store.Database);
        var batch = Batch("a");
        Assert.Throws<ArgumentException>(() => repository.Create(batch, Items(batch, 11).Select(item => item with { BatchId = "wrong" }).ToArray()));
        Assert.Null(repository.Get("a"));
        Assert.Equal(BatchStatus.Succeeded, repository.Create(batch, []).Status);
        Assert.Equal(0L, repository.Get("a")!.Counts["items_total"]);
    }

    [Fact]
    public void QueueItemIdentityConflictCannotCreateAPartialSecondBatch()
    {
        using var store = new OperationalDatabase();
        var repository = new RunBatchRepository(store.Database);
        var first = Batch("a");
        repository.Create(first, Items(first, 11));
        var second = Batch("b");
        var conflicting = Items(second, 22).Select(item => item with { ItemId = "a-0" }).ToArray();
        Assert.Throws<InvalidOperationException>(() => repository.Create(second, conflicting));
        Assert.Null(repository.Get("b"));
        Assert.Single(repository.ListItems("a", null, 10, 0).Items);
        Assert.Equal(11, repository.GetItem(11, "a-0")!.ClientId);
    }

    [Fact]
    public void NonUtcMicrosecondClocksReturnExactlyTheDurableQueueState()
    {
        using var store = new OperationalDatabase();
        var repository = new RunBatchRepository(store.Database);
        var now = Now with { OffsetMinutes = 330, Microsecond = 123456 };
        var batch = Batch("offset") with { RequestedAt = now };
        var created = repository.Create(batch, Items(batch, 11));
        Assert.Equal(created, repository.Get(batch.BatchId));
        var leased = repository.Claim("owner", 1, 60, now).Single();
        Assert.Equal(leased, repository.GetItem(11, leased.ItemId));
        var refreshed = repository.Refresh(batch.BatchId, now);
        Assert.Equal(refreshed, repository.Get(batch.BatchId));
        Assert.Equal(0, refreshed.StartedAt!.Value.OffsetMinutes);
        Assert.Equal(123456, refreshed.StartedAt.Value.Microsecond);
    }

    internal static RunBatch Batch(string id) => new()
    {
        BatchId = id,
        Kind = BatchKind.Calculate,
        ScopeKind = ScopeKind.List,
        ScopeSpec = new PyDict().Add("client_ids", new object?[] { 11L, 22L }),
        RequestedBy = "requester",
        RequestedAt = Now,
    };

    internal static RunBatchItem[] Items(RunBatch batch, params long[] clients) => clients.Select((client, index) => new RunBatchItem
    {
        ItemId = batch.BatchId + "-" + index,
        BatchId = batch.BatchId,
        ClientId = client,
        Seq = index,
    }).ToArray();

    internal static PyDateTime At(int seconds) => PyDateTime.FromIsoFormat(
        new DateTime(2026, 1, 1, 12, 0, 0, DateTimeKind.Utc).AddSeconds(seconds).ToString("yyyy-MM-dd'T'HH:mm:ss", System.Globalization.CultureInfo.InvariantCulture) + "+00:00");
}
