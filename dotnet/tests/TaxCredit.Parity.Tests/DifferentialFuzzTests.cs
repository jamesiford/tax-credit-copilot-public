using System.Globalization;
using System.Text.Json;
using Xunit.Abstractions;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate G3: differential fuzzing. C# generates N seeded random scenarios (default 20,000; <c>TCC_FUZZ_N</c>,
/// <c>TCC_FUZZ_SEED</c>), the Python production engine answers each through <c>parity/engine_cli.py</c>, and the C# engine
/// must agree bit for bit. A mismatch is minimised (ddmin over the rows), saved as a regression golden under
/// <c>parity/goldens/regressions</c>, and fails the test.
/// </summary>
public sealed class DifferentialFuzzTests(ITestOutputHelper output)
{
    private const ulong DefaultSeed = 20261114;
    private const int BatchSize = 250;

    private static int EnvInt(string name, int fallback) =>
        int.TryParse(Environment.GetEnvironmentVariable(name), NumberStyles.Integer, CultureInfo.InvariantCulture, out var v) ? v : fallback;

    [Fact]
    public void Random_scenarios_agree_with_the_python_engine()
    {
        var total = EnvInt("TCC_FUZZ_N", 20000);
        var seed = ulong.TryParse(Environment.GetEnvironmentVariable("TCC_FUZZ_SEED"), NumberStyles.Integer, CultureInfo.InvariantCulture, out var s) ? s : DefaultSeed;
        var parallel = Math.Max(1, EnvInt("TCC_FUZZ_PARALLEL", 4));
        output.WriteLine($"fuzz: N={total} seed={seed} batch={BatchSize} parallel={parallel} python={PythonSession.PythonExe} ({OracleInterpreter.Version})");

        var batches = Enumerable.Range(0, (total + BatchSize - 1) / BatchSize).ToList();
        var failures = new System.Collections.Concurrent.ConcurrentBag<string>();
        var opCounts = new System.Collections.Concurrent.ConcurrentDictionary<string, int>();
        var pythonErrors = 0;
        Parallel.ForEach(batches, new ParallelOptions { MaxDegreeOfParallelism = parallel }, b =>
        {
            // Each batch has its own seed stream and its own Python process (so its own string-hash seed).
            var rng = new Rng(seed ^ (0xA5A5A5A5UL * (ulong)(b + 1)));
            var n = Math.Min(BatchSize, total - (b * BatchSize));
            var scenarios = Enumerable.Range(0, n).Select(i => FuzzGenerator.Scenario(rng, $"fuzz-{seed}-{(b * BatchSize) + i}")).ToList();
            var requests = scenarios.Select(sc => sc.ToJson()).ToList();
            using var python = PythonSession.Start();
            var responses = python.Run(requests);
            for (var i = 0; i < n; i++)
            {
                opCounts.AddOrUpdate(scenarios[i].Op, 1, (_, c) => c + 1);
                if (!responses[i].Contains("\"ok\":true", StringComparison.Ordinal))
                {
                    Interlocked.Increment(ref pythonErrors);
                }

                var diff = DifferentialCheck.Compare(requests[i], responses[i]);
                if (diff is not null)
                {
                    failures.Add(Minimise(scenarios[i], diff, python));
                }
            }
        });

        output.WriteLine($"python raised on {pythonErrors} of {total} scenarios (those are compared by exception type)");
        output.WriteLine("operations: " + string.Join(", ", opCounts.OrderBy(k => k.Key, StringComparer.Ordinal).Select(k => $"{k.Key}={k.Value}")));
        Assert.True(failures.IsEmpty, $"{failures.Count} mismatches (first of {total}):\n" + string.Join("\n", failures.Take(5)));
    }

    /// <summary>Shrinks the rows of a failing scenario while it still fails, then saves it as a regression golden.</summary>
    private static string Minimise(FuzzScenario scenario, string firstDiff, PythonSession python)
    {
        bool StillFails(List<FuzzRow> rows)
        {
            var request = scenario.ToJson(rows);
            return DifferentialCheck.Compare(request, python.RunOne(request)) is not null;
        }

        var current = scenario.Rows.ToList();
        var chunk = Math.Max(1, current.Count / 2);
        while (chunk >= 1 && current.Count > 1)
        {
            var removedAny = false;
            for (var start = 0; start < current.Count;)
            {
                var candidate = current.Take(start).Concat(current.Skip(start + chunk)).ToList();
                if (candidate.Count > 0 && StillFails(candidate))
                {
                    current = candidate;
                    removedAny = true;
                }
                else
                {
                    start += chunk;
                }
            }

            if (!removedAny)
            {
                chunk /= 2;
            }
        }

        var minimalRequest = scenario.ToJson(current);
        var response = python.RunOne(minimalRequest);
        var dir = Path.Combine(GoldenFiles.ParityDirectory, "goldens", "regressions");
        Directory.CreateDirectory(dir);
        var file = Path.Combine(dir, scenario.Id + ".json");
        using var doc = JsonDocument.Parse(minimalRequest);
        using var resp = JsonDocument.Parse(response);
        File.WriteAllText(file, "{\"request\":" + doc.RootElement.GetRawText() + ",\"expected\":" + resp.RootElement.GetRawText() + "}\n");
        return $"{scenario.Id}: {firstDiff} (minimised to {current.Count} rows, saved {file})";
    }

    [Fact]
    public void Saved_regression_goldens_still_agree_with_the_python_engine()
    {
        var dir = Path.Combine(GoldenFiles.ParityDirectory, "goldens", "regressions");
        if (!Directory.Exists(dir))
        {
            return;
        }

        var failures = new List<string>();
        foreach (var file in Directory.EnumerateFiles(dir, "*.json"))
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(file));
            var diff = DifferentialCheck.Compare(doc.RootElement.GetProperty("request").GetRawText(), doc.RootElement.GetProperty("expected").GetRawText());
            if (diff is not null)
            {
                failures.Add($"{Path.GetFileName(file)}: {diff}");
            }
        }

        Assert.Empty(failures);
    }
}
