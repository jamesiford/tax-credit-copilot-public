using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Hosting;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Runs;
using TaxCredit.Domain.Warehouse;
using TaxCredit.Infrastructure.Persistence.Operational;
using TaxCredit.Infrastructure.Persistence.Sql;
using TaxCredit.ServiceDefaults.Hosting;

namespace TaxCredit.Api.Tests.Contract;

public sealed class RuntimeQueueTests
{
    [Fact]
    public async Task Classified_source_outages_back_off_and_cancellation_refunds_the_claimed_attempt()
    {
        await using var retry = await TestHost.Start(services: services =>
        {
            services.AddSingleton<IPayrollSource>(new FailingPayroll(() => new SourceUnavailable()));
        });
        Enqueue(retry, "retry");
        var executor = retry.App.Services.GetRequiredService<RunWorkExecutor>();
        Assert.Equal(1, await executor.Drain(CancellationToken.None));
        Assert.Equal(0, await executor.Drain(CancellationToken.None));
        var item = retry.App.Services.GetRequiredService<IRunBatchRepository>().GetItem(1001, "retry-item")!;
        Assert.True(item.Status == ItemStatus.Queued, $"{item.Status}: {item.ErrorDependency}/{item.ErrorMessage}");
        Assert.Equal("source_unavailable", item.ErrorMessage);
        Assert.NotNull(item.NotBefore);
        using var cancel = new CancellationTokenSource();
        await using var cancelled = await TestHost.Start(services: services =>
            services.AddSingleton<IPayrollSource>(new FailingPayroll(() =>
            {
                cancel.Cancel();
                return new OperationCanceledException(cancel.Token);
            })));
        Enqueue(cancelled, "cancel");
        await Assert.ThrowsAsync<OperationCanceledException>(() =>
            cancelled.App.Services.GetRequiredService<RunWorkExecutor>().Drain(cancel.Token).AsTask());
        var refunded = cancelled.App.Services.GetRequiredService<IRunBatchRepository>().GetItem(1001, "cancel-item")!;
        Assert.Equal(ItemStatus.Queued, refunded.Status);
        Assert.Equal(0, refunded.Attempts);
        Assert.Null(refunded.LeaseOwner);
    }

    [Fact]
    [Trait("Category", "heavy")]
    public async Task Assessment_only_batches_write_claims_without_publishing_a_calculation_manifest()
    {
        await using var host = await TestHost.Start();
        Enqueue(host, "assess", BatchKind.Assess);
        using var response = await host.Client.PostAsJsonAsync("/__contract__/drain", new { });
        Assert.Equal(200, (int)response.StatusCode);
        var item = host.App.Services.GetRequiredService<IRunBatchRepository>().GetItem(1001, "assess-item")!;
        Assert.Equal(ItemStatus.Succeeded, item.Status);
        Assert.Null(item.RunId);
        Assert.Equal(0, host.App.Services.GetRequiredService<IRunManifestRepository>().Count());
        using var session = host.App.Services.GetRequiredService<PersistenceDatabase>().Open();
        Assert.NotEmpty(session.Query(1001, "SELECT claim_id FROM tcc_ops.program_claim WHERE {tenant}"));
        Assert.Empty(session.Query(1001, "SELECT run_id FROM tcc_gold.employee_eligibility WHERE {tenant}"));
    }

    [Fact]
    [Trait("Category", "heavy")]
    public async Task Drain_uses_the_real_transactional_calculation_and_reopen_observes_gold_manifest_claims()
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host);
        Enqueue(host, "drain");
        using var response = await host.Client.PostAsJsonAsync("/__contract__/drain", new { });
        Assert.Equal(200, (int)response.StatusCode);
        Assert.Equal(1, (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("drained").GetInt32());
        VerifyPublication(host, "drain");
        using var empty = await host.Client.PostAsJsonAsync("/__contract__/drain", new { });
        Assert.Equal(0, (await empty.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("drained").GetInt32());
    }

    [Fact]
    public async Task Future_retry_work_remains_pending_and_empty_drain_does_not_advance_the_clock()
    {
        await using var host = await TestHost.Start();
        Enqueue(host, "future");
        var queue = host.App.Services.GetRequiredService<IRunBatchRepository>();
        var at = RuntimeCalculationTime(host);
        var item = queue.Claim("prior", 1, 60, at).Single();
        Assert.True(queue.Requeue(1001, item.ItemId, "prior", at, PyDateTime.FromIsoFormat("2026-01-16T12:00:00+00:00"), "source", "offline"));
        using var response = await host.Client.PostAsJsonAsync("/__contract__/drain", new { });
        Assert.Equal(0, (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("drained").GetInt32());
        var stored = queue.GetItem(1001, item.ItemId)!;
        Assert.Equal(ItemStatus.Queued, stored.Status);
        Assert.Equal(1, stored.Attempts);
        Assert.Equal(at, RuntimeCalculationTime(host));
    }

    internal static void Enqueue(TestHost host, string id, BatchKind kind = BatchKind.Calculate)
    {
        var batch = new RunBatch
        {
            BatchId = id,
            Kind = kind,
            ScopeKind = ScopeKind.One,
            ScopeSpec = new PyDict().Add("client_ids", new List<object?> { 1001L }),
            TaxYears = [2025],
            ProgramCode = "GA_JTC",
            Force = true,
            RequestedBy = "synthetic-worker-check",
            RequestedAt = RuntimeCalculationTime(host),
        };
        host.App.Services.GetRequiredService<IRunBatchRepository>().Create(batch,
            [new RunBatchItem { ItemId = id + "-item", BatchId = id, ClientId = 1001, Seq = 0, TaxYear = 2025, ProgramCode = "GA_JTC" }]);
    }

    internal static void VerifyPublication(TestHost host, string id)
    {
        var path = host.App.Services.GetRequiredService<RuntimePaths>().Database;
        var database = PersistenceDatabase.Sqlite(path);
        var item = new RunBatchRepository(database).GetItem(1001, id + "-item")!;
        Assert.True(item.Status == ItemStatus.Succeeded, $"Terminal status: {item.Status}; classification: {item.ErrorDependency}/{item.ErrorMessage}");
        Assert.Equal(BatchStatus.Succeeded, new RunBatchRepository(database).Get(id)!.Status);
        Assert.Equal("success", new RunManifestRepository(database).Get(item.RunId!)!.RunStatus);
        using var session = database.Open();
        var rows = session.Query(1001, "SELECT method, COUNT(*) AS n, SUM(CASE WHEN eligible=1 THEN 1 ELSE 0 END) AS eligible_count "
            + "FROM tcc_gold.employee_eligibility WHERE {tenant} AND tax_year=? AND run_id=? GROUP BY method", 2025, item.RunId);
        Assert.Equal(2, rows.Count);
        var expected = Corpus.Read(Path.Combine("contract", "seed", "P1", "manifest.json"))
            .GetProperty("api_checks").GetProperty("api_eligibility_by_client").GetProperty("1001");
        Assert.All(rows, row => Assert.Equal(expected.GetProperty("employees_evaluated").GetInt64(), row["n"]));
        Assert.Equal(expected.GetProperty("min_max_eligible").GetInt64(), rows.Single(r => (string)r["method"]! == "min_max")["eligible_count"]);
        Assert.Equal(expected.GetProperty("pay_period_eligible").GetInt64(), rows.Single(r => (string)r["method"]! == "pay_period")["eligible_count"]);
        Assert.NotEmpty(session.Query(1001, "SELECT claim_id FROM tcc_ops.program_claim WHERE {tenant} AND tax_year=?", 2025));
        Assert.NotNull(new RunSourceObservations(database).Get(1001, item.RunId!));
    }

    private static PyDateTime RuntimeCalculationTime(TestHost host) =>
        PyDateTime.FromIsoFormat(host.App.Services.GetRequiredService<IClock>().UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffffzzz",
            System.Globalization.CultureInfo.InvariantCulture));

    private sealed class FailingPayroll(Func<Exception> error) : IPayrollSource
    {
        public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId) => throw error();
    }
}
