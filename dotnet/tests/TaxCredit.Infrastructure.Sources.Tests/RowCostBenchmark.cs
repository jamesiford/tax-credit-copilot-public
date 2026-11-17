using System.Diagnostics;
using System.Globalization;
using System.Runtime.CompilerServices;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Infrastructure.Sources.Fixtures;
using TaxCredit.Infrastructure.Sources.Lookups;
using TaxCredit.Infrastructure.Sources.Mapping;
using TaxCredit.Infrastructure.Sources.Projection;
using TaxCredit.Infrastructure.Sources.Sql;
using Xunit.Abstractions;

namespace TaxCredit.Infrastructure.Sources.Tests;

/// <summary>Skipped unless <c>TCC_RUN_BENCH=1</c>, so ordinary runs stay fast.</summary>
internal sealed class BenchFactAttribute : FactAttribute
{
    internal const string Switch = "TCC_RUN_BENCH";

    public BenchFactAttribute()
    {
        if (Environment.GetEnvironmentVariable(Switch) != "1") { Skip = "Set " + Switch + "=1 to run the row-cost benchmark."; }
    }
}

/// <summary>
/// What one payroll row costs in memory, in the real source shape. Each size is its own test so a fresh test host measures
/// it: run <c>TCC_RUN_BENCH=1 dotnet test --filter "FullyQualifiedName~RowCostBenchmark.Rows_100k"</c> (and 400k, 1M), one per process.
/// </summary>
public sealed class RowCostBenchmark(ITestOutputHelper output)
{
    [BenchFact] public void Rows_100k() => Measure(100_000);
    [BenchFact] public void Rows_400k() => Measure(400_000);
    [BenchFact] public void Rows_1M() => Measure(1_000_000);
    [BenchFact] public void Rows_400k_CompactRow() => Measure(400_000, compact: true);

    private void Measure(int rows, bool compact = false)
    {
        var mapping = SourceMapping.Load();
        var transport = new SyntheticPayrollTransport(mapping, rows, compact);
        var scanner = new SourceScanner(transport, mapping, maximumRows: rows + 1);
        var projector = new PayrollProjector(mapping, SourceTestData.Lookups());
        var baseline = Heap();
        using var sampler = new WorkingSetSampler();
        var baselineWorkingSet = WorkingSetSampler.Current;

        var clock = Stopwatch.StartNew();
        var held = ScanInto(scanner);
        var scanTime = clock.Elapsed;
        var scanned = Heap() - baseline;
        var scanPeak = sampler.Peak;

        clock.Restart();
        var projection = Project(projector, held);
        var projectTime = clock.Elapsed;
        var withBoth = Heap() - baseline;
        var peak = sampler.Peak;

        Check(rows, held, projection);
        var weak = Drop(held);
        var projectedOnly = Heap() - baseline;
        output.WriteLine("payroll rows collected after dataset dropped: " + !weak.IsAlive);
        GC.KeepAlive(projection);

        var mib = 1024.0 * 1024.0;
        var line = string.Create(CultureInfo.InvariantCulture,
            $"| {rows:N0} | {scanned / (double)rows:F0} | {(withBoth - scanned) / (double)rows:F0} | {projectedOnly / (double)rows:F0} | "
            + $"{scanned / mib:F0} | {projectedOnly / mib:F0} | {scanPeak / mib:F0} | {peak / mib:F0} | {baselineWorkingSet / mib:F0} | "
            + $"{scanTime.TotalSeconds:F1} | {projectTime.TotalSeconds:F1} |");
        output.WriteLine("| rows | scan B/row | projection B/row | retained B/row after dataset dropped | scan heap MiB | projected heap MiB | "
            + "peak WS after scan MiB | peak WS MiB | WS before MiB | scan s | project s |");
        output.WriteLine(line + (compact ? " compact row" : ""));
        if (Environment.GetEnvironmentVariable("TCC_BENCH_OUT") is { Length: > 0 } path) { File.AppendAllText(path, line + (compact ? " compact row" : "") + Environment.NewLine); }
    }

    // Each phase runs in its own frame: an unoptimized test method would otherwise keep every temporary alive and hide what the GC can free.
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static Held ScanInto(SourceScanner scanner) => new(Load(scanner));

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static PayrollProjection Project(PayrollProjector projector, Held held) => projector.Project(held.Dataset!);

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void Check(int rows, Held held, PayrollProjection projection)
    {
        Assert.Equal(rows, held.Dataset!.Rows("Payroll").Count);
        Assert.Equal(rows, projection.Rows.Count);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static WeakReference Drop(Held held)
    {
        var weak = new WeakReference(held.Dataset!.Rows("Payroll"));
        held.Dataset = null;
        return weak;
    }

    private sealed class Held(SourceDataset dataset)
    {
        internal SourceDataset? Dataset { get; set; } = dataset;
    }

    private static SourceDataset Load(SourceScanner scanner) =>
        new SourceDatasetReader(scanner).Load(7) ?? throw new InvalidOperationException("The synthetic client was not found.");

    private static long Heap()
    {
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
        return GC.GetTotalMemory(true);
    }

    private sealed class WorkingSetSampler : IDisposable
    {
        private readonly CancellationTokenSource _stop = new();
        private readonly Task _loop;
        private long _peak;

        internal WorkingSetSampler()
        {
            _peak = Current;
            _loop = Task.Run(async () =>
            {
                while (!_stop.IsCancellationRequested)
                {
                    var now = Current;
                    if (now > Interlocked.Read(ref _peak)) { Interlocked.Exchange(ref _peak, now); }
                    await Task.Delay(10).ConfigureAwait(false);
                }
            });
        }

        internal static long Current
        {
            get
            {
                using var process = Process.GetCurrentProcess();
                return process.WorkingSet64;
            }
        }

        internal long Peak => Math.Max(Interlocked.Read(ref _peak), Current);

        public void Dispose()
        {
            _stop.Cancel();
            _loop.Wait();
            _stop.Dispose();
        }
    }
}

/// <summary>
/// A transport that streams one client's payroll as fresh <c>Dictionary&lt;string, object?&gt;</c> rows, which is exactly what
/// the SQL transport hands the scanner, without holding the table itself; dimensions come from the materialized fixture.
/// </summary>
internal sealed class SyntheticPayrollTransport : IAnalyticsTransport
{
    private const int PaychecksPerEmployee = 40;
    private readonly SourceMapping _mapping;
    private readonly long _rows;
    private readonly bool _compact;
    private readonly int _employees;
    private readonly MaterializedAnalyticsTransport _dimensions;

    internal SyntheticPayrollTransport(SourceMapping mapping, long rows, bool compact = false)
    {
        _compact = compact;
        _mapping = mapping;
        _rows = rows;
        _employees = (int)Math.Max(1, rows / PaychecksPerEmployee);
        var tables = SourceTestData.MiniTables(mapping);
        var employment = mapping.Tables["Employment"];
        tables[employment.Physical] = Enumerable.Range(0, _employees).Select(i => (IReadOnlyDictionary<string, object?>)employment.Fields
            .ToDictionary(f => f.Value.Column, f => f.Key switch
            {
                "employee_id" => (object?)(1000L + i),
                "job_title" => "Synthetic role",
                _ => null,
            }, StringComparer.Ordinal)).ToArray();
        tables[mapping.Tables["Payroll"].Physical] = [];
        _dimensions = new MaterializedAnalyticsTransport(mapping, tables);
    }

    public string SourceProvenance => "synthetic-bench";
    public bool IsConfigured => true;
    public IReadOnlyList<string> Columns(string schema, string physicalTable, CancellationToken cancellationToken = default) =>
        _dimensions.Columns(schema, physicalTable, cancellationToken);
    public IDisposable SharedScope() => _dimensions.SharedScope();

    public IEnumerable<IReadOnlyDictionary<string, object?>> Read(AnalyticsQuery query, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(query);
        return query is { Kind: "scan", Table: "Payroll" } ? Payroll(query) : _dimensions.Read(query, cancellationToken);
    }

    private IEnumerable<IReadOnlyDictionary<string, object?>> Payroll(AnalyticsQuery query)
    {
        var names = query.Columns.Keys.ToArray();
        var first = new DateTime(2023, 1, 1, 0, 0, 0, DateTimeKind.Unspecified);
        for (long i = 0; i < _rows; i++)
        {
            var period = (int)(i / _employees % PaychecksPerEmployee);
            var start = first.AddDays(14 * period);
            var values = new object?[names.Length];
            var slot = 0;
            foreach (var column in names)
            {
                values[slot++] = (column switch
                {
                    "payroll_id" => i + 1,
                    "account_id" => 7L,
                    "employee_id" => 1000L + (i % _employees),
                    "entity_id" => 70L,
                    "location_id" => 700L,
                    "worksite_location_id" => null,
                    "pay_frequency_id" => 77L,
                    "pay_period_start" => start,
                    "pay_period_end" => start.AddDays(13),
                    "pay_date" => start.AddDays(18),
                    "hours" => 80m,
                    "wages" => 1600.00m + (i % 97),
                    "pay_code_id" => 1L,
                    "modify_date" => start.AddDays(19),
                    _ => null,
                });
            }
            yield return _compact ? new CompactRow(names, values)
                : names.Zip(values).ToDictionary(p => p.First, p => p.Second, StringComparer.Ordinal);
        }
    }
}

/// <summary>A candidate scan row: the column names are shared by every row and only the values are per-row.</summary>
internal sealed class CompactRow(string[] names, object?[] values) : IReadOnlyDictionary<string, object?>
{
    public int Count => names.Length;
    public IEnumerable<string> Keys => names;
    public IEnumerable<object?> Values => values;
    public object? this[string key] => TryGetValue(key, out var value) ? value : throw new KeyNotFoundException(key);
    public bool ContainsKey(string key) => Array.IndexOf(names, key) >= 0;

    public bool TryGetValue(string key, out object? value)
    {
        var index = Array.IndexOf(names, key);
        value = index >= 0 ? values[index] : null;
        return index >= 0;
    }

    public IEnumerator<KeyValuePair<string, object?>> GetEnumerator() =>
        names.Select((name, i) => new KeyValuePair<string, object?>(name, values[i])).GetEnumerator();

    System.Collections.IEnumerator System.Collections.IEnumerable.GetEnumerator() => GetEnumerator();
}
