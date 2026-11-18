using System.Globalization;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Hosting;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Api.Tests.Bench;

/// <summary>The real host and worker executor over a synthetic client, with one calculation queued.</summary>
internal static class BenchHost
{
    internal const string ItemId = "bench-item";

    internal static async Task<TestHost> Start(SyntheticAnalyticsTransport transport, bool cache = false, Action<IServiceCollection>? configure = null)
    {
        var host = await TestHost.Start(hooks: false,
            services: services =>
            {
                services.AddSingleton<IAnalyticsTransport>(transport);
                // The default 10-minute lease is itself a finding at the largest size; the harness keeps the item alive so every size can be timed.
                services.AddSingleton(new RunExecutionOptions(LeaseSeconds: 7200));
                configure?.Invoke(services);
            },
            configuration: new Dictionary<string, string?>
            {
                ["DATA_SOURCE"] = "lakehouse",
                ["SOURCE_CACHE_MODE"] = cache ? "on" : "off",
                ["DATA_CLASSIFICATION"] = "synthetic",
                ["PAY_CODE_POLICY"] = "assume",
                ["FISCAL_RULES_POLICY"] = "assume",
            });
        var clock = host.App.Services.GetRequiredService<IClock>();
        host.App.Services.GetRequiredService<IRunBatchRepository>().Create(new RunBatch
        {
            BatchId = "bench",
            Kind = BatchKind.Calculate,
            ScopeKind = ScopeKind.One,
            ScopeSpec = new PyDict().Add("client_ids", new List<object?> { SyntheticAnalyticsTransport.AccountId }),
            TaxYears = [2024],
            ProgramCode = "GA_JTC",
            Force = true,
            RequestedBy = "bench",
            RequestedAt = PyDateTime.FromIsoFormat(clock.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffffzzz", CultureInfo.InvariantCulture)),
        }, [new RunBatchItem { ItemId = ItemId, BatchId = "bench", ClientId = SyntheticAnalyticsTransport.AccountId, Seq = 0, TaxYear = 2024, ProgramCode = "GA_JTC" }]);
        return host;
    }
}
