using System.Diagnostics;
using System.Text.Json;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using Xunit.Abstractions;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Micro-benchmark of the C# engine on the same data as <c>parity/bench_python.py</c> (numbers only, no claims about
/// production load). Runs only with <c>BENCH_RUN=1</c>; use <c>-c Release</c>.
/// </summary>
public sealed class EngineBenchmark(ITestOutputHelper output)
{
    [Fact]
    public void Time_the_engine_on_the_synthetic_and_a_generated_large_set()
    {
        if (Environment.GetEnvironmentVariable("BENCH_RUN") != "1")
        {
            output.WriteLine("skipped: set BENCH_RUN=1");
            return;
        }

        List<PayrollRow> small = [];
        foreach (var line in GoldenEngineTests.Lines("datasets.jsonl.gz"))
        {
            if (line.StartsWith("{\"name\":\"csv\",", StringComparison.Ordinal))
            {
                using var doc = JsonDocument.Parse(line);
                small = EngineRunner.Rows(doc.RootElement.GetProperty("rows"));
            }
        }

        const int copies = 20;
        var large = new List<PayrollRow>(small.Count * copies);
        for (var k = 0; k < copies; k++)
        {
            large.AddRange(small.Select(r => r with { EmployeeId = RowCell.OfText(r.EmployeeId.Text + "-" + k) }));
        }

        var pack = new OneZeroPack { MinWeeklyHours = PyNumber.OfFloat(35.0), MinWeeklyWages = PyNumber.OfFloat(680.0), Citation = "bench" };
        foreach (var (name, rows) in new[] { ($"synthetic {small.Count:N0} rows", small), ($"generated {large.Count:N0} rows", large) })
        {
            foreach (var method in new[] { "pay_period", "min_max" })
            {
                Func<OneZeroResult> run = method == "pay_period"
                    ? () => PayPeriodMethod.Run(rows, 2025, new DateOnly(2025, 1, 1), pack)
                    : () => MinMaxMethod.Run(rows, 2025, new DateOnly(2025, 1, 1), pack);
                run();
                var samples = new List<double>();
                for (var i = 0; i < 5; i++)
                {
                    var sw = Stopwatch.StartNew();
                    run();
                    samples.Add(sw.Elapsed.TotalMilliseconds);
                }

                samples.Sort();
                output.WriteLine($"csharp {name,24} {method,10}: min {samples[0],9:F1} ms  median {samples[2],9:F1} ms");
            }
        }
    }
}
