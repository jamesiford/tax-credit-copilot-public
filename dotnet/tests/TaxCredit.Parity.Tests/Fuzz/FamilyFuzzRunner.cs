using System.Collections.Concurrent;
using System.Globalization;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>What one family's fuzz run saw.</summary>
/// <param name="Total">Scenarios run.</param>
/// <param name="Seed">The seed (batch streams derive from it and the family).</param>
/// <param name="Ops">Scenarios per function.</param>
/// <param name="PythonErrors">Scenarios the oracle answered with an exception (compared by type and message).</param>
/// <param name="Mismatches">One line per divergence, each already minimised and saved.</param>
/// <param name="Elapsed">Wall time.</param>
internal sealed record FuzzOutcome(int Total, ulong Seed, IReadOnlyDictionary<string, int> Ops, int PythonErrors, IReadOnlyList<string> Mismatches, TimeSpan Elapsed);

/// <summary>Runs a family's scenarios in batches, each batch against its own Python process (so its own string-hash seed), and minimises any divergence.</summary>
internal static class FamilyFuzzRunner
{
    public const ulong DefaultSeed = 20261114;

    public static int EnvInt(string name, int fallback) =>
        int.TryParse(Environment.GetEnvironmentVariable(name), NumberStyles.Integer, CultureInfo.InvariantCulture, out var v) ? v : fallback;

    public static ulong Seed() =>
        ulong.TryParse(Environment.GetEnvironmentVariable("TCC_FUZZ_SEED"), NumberStyles.Integer, CultureInfo.InvariantCulture, out var s) ? s : DefaultSeed;

    public static FuzzOutcome Run(FuzzFamily family, int total, ulong seed, int batchSize, int parallel)
    {
        var started = DateTime.UtcNow;
        var batches = Enumerable.Range(0, (total + batchSize - 1) / batchSize).ToList();
        var failures = new ConcurrentBag<string>();
        var ops = new ConcurrentDictionary<string, int>();
        var pythonErrors = 0;
        Parallel.ForEach(batches, new ParallelOptions { MaxDegreeOfParallelism = parallel }, b =>
        {
            var rng = new Rng(seed ^ family.Salt ^ (0xA5A5A5A5UL * (ulong)(b + 1)));
            var n = Math.Min(batchSize, total - (b * batchSize));
            var cases = Enumerable.Range(0, n).Select(i => family.Generate(rng, $"{family.Name}-{seed}-{(b * batchSize) + i}")).ToList();
            var check = family.CreateChecker();
            using var python = PythonSession.Start();
            var lines = python.Run(cases.Select(c => c.ToRequest(family.Name)).ToList());
            for (var i = 0; i < n; i++)
            {
                ops.AddOrUpdate(cases[i].Fn, 1, (_, c) => c + 1);
                var call = PyJson.Loads(lines[i]) as PyDict;
                if (call is null || !call.ContainsKey("k"))
                {
                    failures.Add($"{cases[i].Id}: the oracle could not read the request ({lines[i][..Math.Min(200, lines[i].Length)]})");
                    continue;
                }

                if (call.ContainsKey("err"))
                {
                    Interlocked.Increment(ref pythonErrors);
                }

                if (check(call) is { } diff)
                {
                    failures.Add(Minimise(family, cases[i], diff, python, check));
                }
            }
        });
        return new FuzzOutcome(total, seed, ops.OrderBy(k => k.Key, StringComparer.Ordinal).ToDictionary(k => k.Key, k => k.Value), pythonErrors, [.. failures], DateTime.UtcNow - started);
    }

    /// <summary>Shrinks the arguments of a failing case, then saves the minimal case with the oracle's answer as a regression golden.</summary>
    private static string Minimise(FuzzFamily family, FamilyCase failing, string firstDiff, PythonSession python, Func<PyDict, string?> check)
    {
        string? Diff(PyDict args)
        {
            var line = python.RunOne(failing.ToRequest(family.Name, args));
            return PyJson.Loads(line) is PyDict call && call.ContainsKey("k") ? check(call) : null;
        }

        // A shrunk case must fail the same way: dropping a required field makes both sides raise for a different reason.
        var kind = Kind(firstDiff);
        var minimal = TreeMinimiser.Minimise(failing.Args, args => Diff(args) is { } d && Kind(d) == kind);
        var line = python.RunOne(failing.ToRequest(family.Name, minimal));
        var diff = Diff(minimal) ?? firstDiff;
        var dir = Path.Combine(GoldenFiles.ParityDirectory, "goldens", "regressions");
        Directory.CreateDirectory(dir);
        var file = Path.Combine(dir, failing.Id + ".json");
        File.WriteAllText(file, "{\"family\":" + PyJson.Dumps(family.Name) + ",\"expected\":" + line + "}\n");
        return $"{failing.Id} ({failing.Fn}): {diff} (first seen: {firstDiff[..Math.Min(300, firstDiff.Length)]}) [minimised {PyJson.Dumps(failing.Args, false, true).Length} -> {PyJson.Dumps(minimal, false, true).Length} chars, saved {file}]";
    }

    private static string Kind(string diff) =>
        diff.StartsWith('$') ? "value" : System.Text.RegularExpressions.Regex.Match(diff, "^exception: got (\\w+) .* expected (\\w+) ") is { Success: true } m ? $"exception:{m.Groups[1].Value}:{m.Groups[2].Value}" : diff.Split(':')[0];

    /// <summary>Replays every saved family regression against the port and returns the divergences.</summary>
    public static List<string> ReplayRegressions(IReadOnlyDictionary<string, FuzzFamily> families)
    {
        var dir = Path.Combine(GoldenFiles.ParityDirectory, "goldens", "regressions");
        var failures = new List<string>();
        if (!Directory.Exists(dir))
        {
            return failures;
        }

        foreach (var file in Directory.EnumerateFiles(dir, "*.json").Where(f => !Path.GetFileName(f).StartsWith("fuzz-", StringComparison.Ordinal)))
        {
            var doc = (PyDict)PyJson.Loads(File.ReadAllText(file))!;
            var family = families[(string)doc["family"]!];
            if (family.CreateChecker()((PyDict)doc["expected"]!) is { } diff)
            {
                failures.Add($"{Path.GetFileName(file)}: {diff}");
            }
        }

        return failures;
    }
}
