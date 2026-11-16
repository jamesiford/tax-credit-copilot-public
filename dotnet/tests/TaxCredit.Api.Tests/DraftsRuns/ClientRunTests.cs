using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Api.Tests.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Runs;
using TaxCredit.Domain.Warehouse;
using TaxCredit.Infrastructure.Persistence;

namespace TaxCredit.Api.Tests.DraftsRuns;

public sealed class ClientRunTests
{
    [Fact]
    [Trait("Category", "heavy")]
    public async Task A_direct_run_is_visible_through_the_durable_latest_destination_and_never_run_is_not_found()
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host);
        using var never = await host.Client.GetAsync("/api/v2/clients/9999/runs/latest");
        Assert.Equal(404, (int)never.StatusCode);
        using var calculated = await host.Client.PostAsJsonAsync("/api/v2/clients/1001/runs", new { year = 2025, state = "GA", triggered_by = "synthetic-direct-run" });
        Assert.True((int)calculated.StatusCode == 200, await calculated.Content.ReadAsStringAsync());
        var result = await calculated.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(107, result.GetProperty("summary").GetProperty("employees_evaluated").GetInt64());
        Assert.Equal(77, result.GetProperty("summary").GetProperty("min_max_eligible").GetInt64());
        Assert.Equal(72, result.GetProperty("summary").GetProperty("pay_period_eligible").GetInt64());
        Assert.Equal(GoldWriter.Section9QueryCount, result.GetProperty("validation").GetProperty("queries_run").GetInt64());
        using var latest = await host.Client.GetAsync("/api/v2/clients/1001/runs/latest");
        Assert.Equal(200, (int)latest.StatusCode);
        var manifest = await latest.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(result.GetProperty("run_id").GetString(), manifest.GetProperty("run_id").GetString());
        Assert.Equal("success", manifest.GetProperty("run_status").GetString());
        Assert.Equal(0, host.App.Services.GetRequiredService<IRunBatchRepository>().ListBatches(10, 0).Total);
    }

    [Fact]
    [Trait("Category", "heavy")]
    public async Task Rebase_reads_gold_and_same_timestamp_save_change_clear_later_save_recalculate_in_persisted_order()
    {
        var calls = new Counter();
        await using var host = await TestHost.Start(services: services =>
            services.AddScoped<IPayrollSource>(p => new ObservedPayroll(p.GetRequiredService<IClientPayrollSource>(), calls)));
        await RuntimeRequests.Reset(host, "P2");
        using var repriced = await host.Client.GetAsync("/api/v2/clients/2001/units/GA_GA-001/rebase?base_year=2022");
        Assert.True((int)repriced.StatusCode == 200, await repriced.Content.ReadAsStringAsync());
        var rebase = await repriced.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(0, rebase.GetProperty("total_annual_credit_usd").GetInt64());
        Assert.Equal(120820, rebase.GetProperty("run_total_annual_credit_usd").GetInt64());
        Assert.Equal(0, calls.Value);
        var overrides = host.App.Services.GetRequiredService<IManualOverrideRepository>();
        foreach (var year in new int?[] { 2020, 2022, null, 2021 })
        {
            using var saved = await host.Client.PostAsJsonAsync("/api/v2/clients/2001/units/GA_GA-001/base-year",
                new { base_year = year, state = "GA", triggered_by = "synthetic-override" });
            Assert.True((int)saved.StatusCode == 200, await saved.Content.ReadAsStringAsync());
            Assert.True((await saved.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("recorded").GetBoolean());
            using var next = await host.Client.GetAsync("/api/v2/clients/2001/runs/latest");
            Assert.Equal(200, (int)next.StatusCode);
            Assert.Equal((long?)year, overrides.BaseYears(2001, "GA_JTC").TryGetValue("GA_GA-001", out var value) ? value : null);
            var queue = host.App.Services.GetRequiredService<IRunBatchRepository>();
            Assert.All(queue.ListBatches(10, 0).Items, b => Assert.Equal(BatchStatus.Succeeded, b.Status));
        }
        Assert.True(calls.Value >= 4);
        var before = calls.Value;
        using var unchanged = await host.Client.PostAsJsonAsync("/api/v2/clients/2001/units/GA_GA-001/base-year", new { base_year = 2021, state = "GA" });
        Assert.False((await unchanged.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("recorded").GetBoolean());
        Assert.Equal(before, calls.Value);
        Assert.Equal(4, host.App.Services.GetRequiredService<IRunBatchRepository>().ListBatches(10, 0).Total);
    }

    private sealed class Counter
    {
        internal int Value;
    }

    private sealed class ObservedPayroll(IClientPayrollSource source, Counter calls) : IPayrollSource
    {
        public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId)
        {
            Interlocked.Increment(ref calls.Value);
            return source.LoadPayPeriods(accountId);
        }
    }
}
