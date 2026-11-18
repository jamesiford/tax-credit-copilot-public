using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Api.Tests.Bench;
using TaxCredit.Application.Hosting;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Runs;
using TaxCredit.Infrastructure.Persistence;
using TaxCredit.Infrastructure.Persistence.Operational;
using TaxCredit.Infrastructure.Persistence.Sql;
using TaxCredit.ServiceDefaults.Hosting;

namespace TaxCredit.Api.Tests.DraftsRuns;

/// <summary>A running item keeps its queue lease for as long as the calculation and the write take, instead of only at the publication boundaries.</summary>
public sealed class LeaseRenewalTests
{
    private sealed class SlowGoldWriter(GoldWriter inner, TimeSpan delay, Func<bool> slow, Action? during = null) : IGoldWriter
    {
        public IReadOnlyList<KeyValuePair<string, long>> WriteRun(GoldRunPayload payload)
        {
            if (slow())
            {
                var until = DateTime.UtcNow + delay;
                during?.Invoke();
                while (DateTime.UtcNow < until) { Thread.Sleep(100); }
            }

            return inner.WriteRun(payload);
        }

        public IReadOnlyList<(string Query, long RowCount)> Validate() => inner.Validate();
    }

    private static Task<TestHost> Start(RunExecutionOptions options, Func<bool> slow, TimeSpan delay, Action? during = null) =>
        BenchHost.Start(new SyntheticAnalyticsTransport(2000), configure: services =>
        {
            services.AddSingleton(options);
            services.AddScoped<IGoldWriter>(sp => new SlowGoldWriter(sp.GetRequiredService<GoldWriter>(), delay, slow, during));
        });

    private static (RunBatchRepository Queue, PersistenceDatabase Database) Store(TestHost host)
    {
        var database = PersistenceDatabase.Sqlite(host.App.Services.GetRequiredService<RuntimePaths>().Database);
        return (new RunBatchRepository(database), database);
    }

    private static string[] Identities(PersistenceDatabase database)
    {
        using var session = database.Open();
        return session.Query(SyntheticAnalyticsTransport.AccountId, "SELECT run_id FROM tcc_ops.run_work_identity WHERE {tenant} AND item_id = ?", BenchHost.ItemId)
            .Select(r => (string)r["run_id"]!).ToArray();
    }

    [Fact]
    public async Task A_write_longer_than_the_lease_keeps_the_item_because_the_lease_is_renewed_while_it_runs()
    {
        await using var host = await Start(new RunExecutionOptions(LeaseSeconds: 3), () => true, TimeSpan.FromSeconds(8));
        var (queue, database) = Store(host);
        Assert.Equal(1, await host.App.Services.GetRequiredService<RunWorkExecutor>().Drain(CancellationToken.None));
        var item = queue.GetItem(SyntheticAnalyticsTransport.AccountId, BenchHost.ItemId)!;
        Assert.True(item.Status == ItemStatus.Succeeded, $"{item.Status}: {item.ErrorDependency}/{item.ErrorMessage}");
        Assert.Equal(1, item.Attempts);
        Assert.Equal(item.RunId, Assert.Single(Identities(database)));
        Assert.Equal(1, new RunManifestRepository(database).Count());
    }

    [Fact]
    public async Task A_renewal_that_finds_the_lease_gone_makes_the_item_lose_it_and_stops_a_write_at_its_next_boundary()
    {
        await using var host = await Start(new RunExecutionOptions(LeaseSeconds: 3), () => false, TimeSpan.Zero);
        var (queue, database) = Store(host);
        var item = Assert.Single(queue.Claim("owner", 1, 3, TaxCredit.Domain.Numerics.PyDateTime.FromIsoFormat(host.App.Services.GetRequiredService<TaxCredit.Application.Ports.Contract.IClock>().UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'+00:00'", System.Globalization.CultureInfo.InvariantCulture))));
        using (var session = database.Open())
        {
            session.Execute(item.ClientId, "UPDATE tcc_ops.run_batch_item SET lease_owner = 'other' WHERE {tenant} AND item_id = ?", item.ItemId);
        }

        using var keeper = new RunLeaseKeeper(queue, item, "owner", 3, 1, host.App.Services.GetRequiredService<TaxCredit.Application.Ports.Contract.IClock>());
        keeper.Start();
        await Task.Delay(2500);
        Assert.Throws<RunLeaseLost>(() => keeper.ThrowIfLost());
        using (keeper.Enter())
        {
            Assert.Throws<RunLeaseLost>(() => RunLeaseScope.ThrowIfLost());
        }

        RunLeaseScope.ThrowIfLost();
    }

    [Fact]
    public async Task An_attempt_that_loses_its_lease_commits_nothing_and_the_next_attempt_publishes_the_same_single_run()
    {
        var calls = 0;
        await using var host = await BenchHost.Start(new SyntheticAnalyticsTransport(2000), configure: services =>
        {
            services.AddScoped<IGoldWriter>(sp => new LoseOnceWriter(sp.GetRequiredService<GoldWriter>(), () => Interlocked.Increment(ref calls) == 1));
        });
        var (queue, db) = Store(host);
        var executor = host.App.Services.GetRequiredService<RunWorkExecutor>();
        await Assert.ThrowsAsync<RunLeaseLost>(async () => await executor.Drain(CancellationToken.None));
        Assert.Equal(0, new RunManifestRepository(db).Count());
        using (var session = db.Open())
        {
            Assert.Empty(session.Query(SyntheticAnalyticsTransport.AccountId, "SELECT run_id FROM tcc_gold.employee_period_fact WHERE {tenant}"));
        }

        var first = Assert.Single(Identities(db));
        var clock = host.App.Services.GetRequiredService<TaxCredit.Application.Ports.Contract.IClock>();
        queue.ReapExpired(TaxCredit.Domain.Numerics.PyDateTime.FromIsoFormat(clock.UtcNow.AddDays(1).ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'+00:00'", System.Globalization.CultureInfo.InvariantCulture)), 3);
        using (var session = db.Open())
        {
            session.Execute(SyntheticAnalyticsTransport.AccountId, "UPDATE tcc_ops.run_batch_item SET not_before = NULL WHERE {tenant} AND item_id = ?", BenchHost.ItemId);
        }

        Assert.Equal(1, await executor.Drain(CancellationToken.None));
        var item = queue.GetItem(SyntheticAnalyticsTransport.AccountId, BenchHost.ItemId)!;
        Assert.True(item.Status == ItemStatus.Succeeded, $"{item.Status}: {item.ErrorDependency}/{item.ErrorMessage}");
        Assert.Equal(first, item.RunId);
        Assert.Equal(first, Assert.Single(Identities(db)));
        Assert.Equal(1, new RunManifestRepository(db).Count());
    }

    private sealed class LoseOnceWriter(GoldWriter inner, Func<bool> first) : IGoldWriter
    {
        public IReadOnlyList<KeyValuePair<string, long>> WriteRun(GoldRunPayload payload) =>
            first() ? throw new RunLeaseLost() : inner.WriteRun(payload);

        public IReadOnlyList<(string Query, long RowCount)> Validate() => inner.Validate();
    }
}
