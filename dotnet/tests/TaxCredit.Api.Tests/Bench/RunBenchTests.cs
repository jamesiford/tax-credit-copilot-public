using System.Collections.Concurrent;
using System.Diagnostics;
using System.Globalization;
using System.Text;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Hosting;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;
using TaxCredit.Infrastructure.Sources.Sql;
using TaxCredit.ServiceDefaults.Hosting;
using Xunit.Abstractions;

namespace TaxCredit.Api.Tests.Bench;

/// <summary>
/// Opt-in stage timing of one queued client calculation end to end over a synthetic client (set <c>TCC_RUN_BENCH=1</c>;
/// <c>TCC_BENCH_SIZES</c> overrides the 100000,400000,1000000 default). A normal test run does nothing here.
/// </summary>
public sealed class RunBenchTests(ITestOutputHelper output)
{
    private const string Enable = "TCC_RUN_BENCH";

    [Fact]
    [Trait("Category", "bench")]
    public async Task One_queued_calculation_is_timed_per_stage()
    {
        if (Environment.GetEnvironmentVariable(Enable) != "1") { return; }
        var sizes = (Environment.GetEnvironmentVariable("TCC_BENCH_SIZES") ?? "100000,400000,1000000")
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(s => long.Parse(s, CultureInfo.InvariantCulture)).ToArray();
        var directory = Path.Combine(Corpus.Root, "dotnet", "artifacts", "bench");
        Directory.CreateDirectory(directory);
        var file = Path.Combine(directory, "bench-" + (Environment.GetEnvironmentVariable("TCC_BENCH_LABEL") ?? "run") + ".txt");
        File.Delete(file);
        foreach (var size in sizes)
        {
            string text;
            try { text = await Measure(size); }
            catch (Exception error) { text = $"=== {size:N0} payroll rows FAILED: {error.GetType().Name}: {error.Message}\n"; }
            // Appended per size so a long or failed size never loses the ones that finished.
            await File.AppendAllTextAsync(file, text + "\n");
            output.WriteLine(text);
        }
    }

    private static async Task<string> Measure(long size)
    {
        var transport = new SyntheticAnalyticsTransport(size);
        var spans = new ConcurrentQueue<Span>();
        using var listener = new ActivityListener
        {
            ShouldListenTo = source => source.Name == RunSpans.SourceName,
            Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllData,
            ActivityStopped = activity => spans.Enqueue(new Span(activity.Id!, activity.ParentId, activity.OperationName,
                activity.Duration, activity.StartTimeUtc, activity.TagObjects.ToDictionary(t => t.Key, t => t.Value))),
        };
        ActivitySource.AddActivityListener(listener);

        await using var host = await TestHost.Start(hooks: false,
            services: services => services.AddSingleton<IAnalyticsTransport>(transport),
            configuration: new Dictionary<string, string?>
            {
                ["DATA_SOURCE"] = "lakehouse",
                ["DATA_CLASSIFICATION"] = "synthetic",
                ["PAY_CODE_POLICY"] = "assume",
                ["FISCAL_RULES_POLICY"] = "assume",
            });
        var queue = host.App.Services.GetRequiredService<IRunBatchRepository>();
        var clock = host.App.Services.GetRequiredService<IClock>();
        queue.Create(new RunBatch
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
        }, [new RunBatchItem { ItemId = "bench-item", BatchId = "bench", ClientId = SyntheticAnalyticsTransport.AccountId, Seq = 0, TaxYear = 2024, ProgramCode = "GA_JTC" }]);

        var executor = host.App.Services.GetRequiredService<RunWorkExecutor>();
        var wall = Stopwatch.StartNew();
        var drained = await executor.Drain(CancellationToken.None);
        wall.Stop();
        var item = queue.GetItem(SyntheticAnalyticsTransport.AccountId, "bench-item")!;
        var path = host.App.Services.GetRequiredService<RuntimePaths>().Database;
        var dumpDirectory = Environment.GetEnvironmentVariable("TCC_BENCH_DUMP");
        var dump = GoldDump.Hash(path, dumpDirectory is null ? null : Path.Combine(dumpDirectory, "gold-" + size.ToString(CultureInfo.InvariantCulture) + ".tsv"));
        var table = SpanTable.Render(spans.ToArray(), wall.Elapsed);
        return $"=== {transport.RowCount:N0} payroll rows | drained {drained} | item {item.Status} {item.ErrorDependency}/{item.ErrorMessage} | "
            + $"wall {wall.Elapsed.TotalSeconds:F1}s | peak {Process.GetCurrentProcess().PeakWorkingSet64 / 1048576:N0} MB | payroll scans {transport.PayrollScans} ===\n{table}\ngold dump sha256: {dump}\n";
    }
}
