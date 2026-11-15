using TaxCredit.Domain.Runs;
using TaxCredit.Infrastructure.Persistence.Operational;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.Operational;

public sealed class RunQueueCostTests
{
    [Fact]
    public void SevenItemDrainStaysWithinRecordedStatementAndTransactionBudgets()
    {
        using var store = new OperationalDatabase();
        var cost = new QueueCost();
        var database = new PersistenceDatabase(() => new QueueCostConnection(store.Path, cost), new SqliteDialect());
        var repository = new RunBatchRepository(database);
        var batch = RunBatchRepositoryTests.Batch("cost");
        var items = RunBatchRepositoryTests.Items(batch, 11, 22, 33, 44, 55, 66, 77);
        repository.Create(batch, items);
        var before = (cost.Statements, cost.Transactions);
        var now = RunBatchRepositoryTests.At(0);
        repository.ReapExpired(now, 3);
        foreach (var expected in items)
        {
            var item = repository.Claim("owner", 1, 120, now).Single();
            Assert.Equal(expected.ItemId, item.ItemId);
            Assert.True(repository.MarkRunning(item.ClientId, item.ItemId, "owner", 2023, "GA_JTC", now));
            var finishBefore = (cost.Statements, cost.Transactions);
            Assert.True(repository.Finish(item.ClientId, item.ItemId, "owner", now, new ItemResult { Status = ItemStatus.Succeeded }, item.BatchId));
            Assert.Equal(1, cost.Transactions - finishBefore.Transactions);
            Assert.Equal(4, cost.Statements - finishBefore.Statements);
        }

        Assert.Empty(repository.Claim("owner", 1, 120, now));
        Assert.True((cost.Statements - before.Statements) / (double)items.Length <= 10.5);
        Assert.True((cost.Transactions - before.Transactions) / (double)items.Length <= 4.5);
        Assert.Equal(7L, repository.Get("cost")!.Counts["items_succeeded"]);
        Assert.Equal(BatchStatus.Succeeded, repository.Get("cost")!.Status);
    }

    [Fact]
    public async Task ConcurrentFinishesRefreshAllCountersWithoutLostUpdates()
    {
        using var store = new OperationalDatabase();
        var first = new RunBatchRepository(store.Database);
        var second = new RunBatchRepository(store.Reopen());
        var now = RunBatchRepositoryTests.At(0);
        var batch = RunBatchRepositoryTests.Batch("finish");
        first.Create(batch, RunBatchRepositoryTests.Items(batch, 11, 22));
        var items = first.Claim("owner", 2, 120, now);
        using var start = new Barrier(2);
        bool Finish(RunBatchRepository repository, RunBatchItem item)
        {
            start.SignalAndWait();
            return repository.Finish(item.ClientId, item.ItemId, "owner", now, new ItemResult { Status = ItemStatus.Succeeded }, "finish");
        }

        Assert.All(await Task.WhenAll(Task.Run(() => Finish(first, items[0])), Task.Run(() => Finish(second, items[1]))), Assert.True);
        var final = new RunBatchRepository(store.Reopen()).Get("finish")!;
        Assert.Equal(2L, final.Counts["items_succeeded"]);
        Assert.Equal(0L, final.Counts["items_running"]);
        Assert.Equal(BatchStatus.Succeeded, final.Status);
    }
}
