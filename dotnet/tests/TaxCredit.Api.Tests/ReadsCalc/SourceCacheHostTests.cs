using System.Net.Http.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Application.Hosting;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Runs;
using TaxCredit.Infrastructure.Sources;
using TaxCredit.Infrastructure.Sources.Cache;
using TaxCredit.ServiceDefaults.Hosting;

namespace TaxCredit.Api.Tests.ReadsCalc;

public sealed class SourceCacheHostTests
{
    private static Dictionary<string, string?> On() => new() { ["SOURCE_CACHE_MODE"] = "on", ["SOURCE_CACHE_MB"] = "32", ["SOURCE_CACHE_ACCOUNTS"] = "3", ["SOURCE_VERSION_CHECK_SECONDS"] = "7" };

    [Fact]
    public async Task The_cache_is_off_by_default_and_the_run_path_is_the_unwrapped_runner()
    {
        await using var host = await TestHost.Start();
        Assert.Null(host.App.Services.GetService<ClientProjectionCache>());
        Assert.False(host.App.Services.GetRequiredService<ProjectionCacheOptions>().Enabled);
        using var scope = host.App.Services.CreateScope();
        Assert.Equal("PersistedClientCalculation", scope.ServiceProvider.GetRequiredService<IClientCalculationRunner>().GetType().Name);
    }

    [Fact]
    public async Task Turning_it_on_registers_one_shared_cache_and_every_run_goes_through_the_fresh_scope()
    {
        await using var host = await TestHost.Start(configuration: On());
        var cache = host.App.Services.GetRequiredService<ClientProjectionCache>();
        Assert.Same(cache, host.App.Services.GetRequiredService<ClientProjectionCache>());
        Assert.Equal(new ProjectionCacheOptions(true, 32L * 1024 * 1024, 3, TimeSpan.FromSeconds(7)), host.App.Services.GetRequiredService<ProjectionCacheOptions>());
        using var scope = host.App.Services.CreateScope();
        Assert.Equal("FreshSourceRunner", scope.ServiceProvider.GetRequiredService<IClientCalculationRunner>().GetType().Name);
        // The CSV fixture holds nothing that can be stale, so it tracks nothing; only the SQL source is a fresh-scope owner.
        Assert.Same(NoPayrollFreshness.Instance, scope.ServiceProvider.GetRequiredService<IPayrollFreshness>());
        Assert.True(typeof(IPayrollFreshness).IsAssignableFrom(typeof(SqlClientSource)));
    }

    [Fact]
    public void A_synchronous_run_reads_under_the_fresh_scope()
    {
        var probe = new Probe();
        var runner = new FreshSourceRunner(new ProbeRunner(probe), new ProbeFreshness(probe));
        runner.Run(new RunClientCalculationCommand(1001, 2023));
        Assert.Equal((1, 0), (probe.Opened, probe.Open));
        Assert.Equal([true], probe.Seen);
    }

    [Fact]
    public async Task Queued_run_steps_and_claim_assessment_read_under_the_fresh_scope()
    {
        var probe = new Probe();
        await using var host = await TestHost.Start(services: services =>
        {
            services.Replace(ServiceDescriptor.Singleton(probe));
            services.Replace(ServiceDescriptor.Scoped<IPayrollFreshness>(_ => new ProbeFreshness(probe)));
            services.Replace(ServiceDescriptor.Scoped<IClientPayrollSource>(_ => new ProbeSource(probe)));
            services.Replace(ServiceDescriptor.Scoped<IPayrollSource>(p => p.GetRequiredService<IClientPayrollSource>()));
        });
        using (var scope = host.App.Services.CreateScope())
        {
            var execution = scope.ServiceProvider.GetRequiredService<RunItemExecution>();
            var batch = new RunBatch
            {
                BatchId = "b",
                Kind = Enum.GetValues<BatchKind>()[0],
                ScopeKind = Enum.GetValues<ScopeKind>()[0],
                ScopeSpec = new PyDict(),
                RequestedBy = "test",
                RequestedAt = PyDateTime.FromIsoFormat("2026-01-01T00:00:00+00:00"),
            };
            var item = new RunBatchItem { ItemId = "i", BatchId = "b", ClientId = 1001 };
            Assert.Equal(ItemStatus.SkippedNoPayroll, execution.Assess(item, batch).Status);
            Assert.Throws<ClientRunNotAvailable>(() => execution.Resolve(item, batch));
        }
        Assert.Equal(new[] { true, true }, probe.Seen);
        using var response = await host.Client.PostAsJsonAsync("/api/claims/assess", new { client_id = 1001, program_code = "GA_JTC" });
        Assert.Equal(404, (int)response.StatusCode);
        Assert.Equal(new[] { true, true, true }, probe.Seen);
        Assert.Equal((3, 0), (probe.Opened, probe.Open));
    }

    [Fact]
    public async Task A_plain_page_read_is_not_a_fresh_scope()
    {
        var probe = new Probe();
        await using var host = await TestHost.Start(services: services =>
        {
            services.Replace(ServiceDescriptor.Singleton(probe));
            services.Replace(ServiceDescriptor.Scoped<IPayrollFreshness>(_ => new ProbeFreshness(probe)));
            services.Replace(ServiceDescriptor.Singleton<IClientPayrollSource>(new ProbeSource(probe)));
        });
        using var response = await host.Client.GetAsync("/api/forecast/2025?state=GA&account_id=1001");
        Assert.Equal(0, probe.Opened);
        Assert.DoesNotContain(true, probe.Seen);
    }

    private sealed class Probe
    {
        internal int Opened, Open;
        internal List<bool> Seen { get; } = [];
    }

    private sealed class ProbeFreshness(Probe probe) : IPayrollFreshness
    {
        public IDisposable RequireFresh()
        {
            probe.Opened++;
            probe.Open++;
            return new Leave(probe);
        }

        private sealed class Leave(Probe probe) : IDisposable
        {
            public void Dispose() => probe.Open--;
        }
    }

    private sealed class ProbeRunner(Probe probe) : IClientCalculationRunner
    {
        public PyDict Run(RunClientCalculationCommand command)
        {
            probe.Seen.Add(probe.Open > 0);
            return new PyDict();
        }
    }

    private sealed class ProbeSource(Probe probe) : IClientPayrollSource, ISourceReader
    {
        public long? FixtureAccountId => 1001;
        public bool IsConfigured => true;
        public IReadOnlyList<SourceAccount> ListAccounts() => [new(1001, "Synthetic client", "GA")];
        public IReadOnlyDictionary<long, IReadOnlyList<string>> Footprint() => new Dictionary<long, IReadOnlyList<string>> { [1001] = ["GA"] };
        public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId)
        {
            probe.Seen.Add(probe.Open > 0);
            return [];
        }
        public IReadOnlyDictionary<long, IReadOnlyList<PayRow>> LoadPortfolioPayPeriods() => new Dictionary<long, IReadOnlyList<PayRow>>();
        public FiscalWindow ClientFiscalWindow(long? accountId, long taxYear, string convention) =>
            new(new DateOnly((int)taxYear, 1, 1), new DateOnly((int)taxYear, 12, 31), taxYear, convention, "synthetic");
        public FiscalWindow? FiscalWindowForStateYear(long? accountId, string state, long taxYear) => ClientFiscalWindow(accountId, taxYear, "ends");
        public (DateOnly Begin, DateOnly End)? WindowForStateYear(long? accountId, string state, long taxYear) =>
            (new DateOnly((int)taxYear, 1, 1), new DateOnly((int)taxYear, 12, 31));
    }

    [Fact]
    public async Task An_invalid_cache_setting_stops_the_host_at_startup()
    {
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            TestHost.Start(configuration: new Dictionary<string, string?> { ["SOURCE_CACHE_MODE"] = "maybe" }));
        Assert.StartsWith("SOURCE_CACHE_MODE must be", error.Message, StringComparison.Ordinal);
    }
}
