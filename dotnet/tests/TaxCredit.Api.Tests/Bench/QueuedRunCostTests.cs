using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Hosting;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Runs;

namespace TaxCredit.Api.Tests.Bench;

/// <summary>Regression guards for the two causes found by the S4 profile; they run in every normal test run on a small synthetic client.</summary>
public sealed class QueuedRunCostTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task A_queued_calculation_reads_the_client_payroll_once_not_four_times(bool cache)
    {
        var transport = new SyntheticAnalyticsTransport(3000);
        await using var host = await BenchHost.Start(transport, cache);
        Assert.Equal(1, await host.App.Services.GetRequiredService<RunWorkExecutor>().Drain(CancellationToken.None));
        var item = host.App.Services.GetRequiredService<IRunBatchRepository>().GetItem(SyntheticAnalyticsTransport.AccountId, BenchHost.ItemId)!;
        Assert.True(item.Status == ItemStatus.Succeeded, $"{item.Status}: {item.ErrorDependency}/{item.ErrorMessage}");
        Assert.Equal(1, transport.PayrollScans);
    }

    [Fact]
    public async Task With_the_cache_on_a_second_run_still_takes_a_fresh_fingerprint_and_rereads_nothing_while_unchanged()
    {
        var transport = new SyntheticAnalyticsTransport(3000);
        await using var host = await BenchHost.Start(transport, cache: true);
        var cache = host.App.Services.GetRequiredService<TaxCredit.Infrastructure.Sources.Cache.ClientProjectionCache>();
        await host.App.Services.GetRequiredService<RunWorkExecutor>().Drain(CancellationToken.None);
        Assert.Equal((1, 1), (transport.PayrollScans, (int)cache.Metrics.Misses));
        using var scope = host.App.Services.CreateScope();
        using (scope.ServiceProvider.GetRequiredService<TaxCredit.Application.Ports.Sources.IPayrollFreshness>().RequireFresh())
        {
            scope.ServiceProvider.GetRequiredService<TaxCredit.Domain.Pipeline.IPayrollSource>().LoadPayPeriods(SyntheticAnalyticsTransport.AccountId);
        }
        Assert.Equal(1, cache.Metrics.Revalidations);
        Assert.Equal(1, transport.PayrollScans);
    }

    [Fact]
    public async Task A_queued_calculation_sends_no_statement_with_thousands_of_parameters()
    {
        var parameters = new List<long>();
        using var listener = new System.Diagnostics.ActivityListener
        {
            ShouldListenTo = source => source.Name == RunSpans.SourceName,
            Sample = (ref System.Diagnostics.ActivityCreationOptions<System.Diagnostics.ActivityContext> _) => System.Diagnostics.ActivitySamplingResult.AllData,
            ActivityStopped = activity =>
            {
                if (activity.OperationName == "sql.insert-batch") { lock (parameters) { parameters.Add(Convert.ToInt64(activity.GetTagItem("parameters"), System.Globalization.CultureInfo.InvariantCulture)); } }
            },
        };
        System.Diagnostics.ActivitySource.AddActivityListener(listener);
        await using var host = await BenchHost.Start(new SyntheticAnalyticsTransport(3000));
        await host.App.Services.GetRequiredService<RunWorkExecutor>().Drain(CancellationToken.None);
        Assert.NotEmpty(parameters);
        Assert.All(parameters, count => Assert.InRange(count, 1, 128));
    }
}
