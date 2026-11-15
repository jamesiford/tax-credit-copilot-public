using System.Diagnostics;
using System.Globalization;
using Xunit.Abstractions;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Mutation self-test: proves the parity harness can fail. For each mutation, the Domain sources are copied to a scratch
/// tree, one deliberate defect is applied (a rounding mode, a comparison, a sort tie-break), and the golden and
/// differential-fuzz tests are run against that copy; they must FAIL. Slow (a build per mutation), so it runs only when
/// <c>TCC_RUN_MUTATION_TESTS=1</c>; the result of the last run is recorded in <c>docs/parity-report.md</c>.
/// </summary>
public sealed class MutationSelfTests(ITestOutputHelper output)
{
    private static readonly (string Name, string File, string Old, string New)[] Mutations =
    [
        ("rounding: half-up becomes half-even", @"src\TaxCredit.Domain\Calculation\OneZeroEligibility.cs", "PyRoundingMode.HalfUp", "PyRoundingMode.HalfEven"),
        ("comparison: >= floor becomes > floor", @"src\TaxCredit.Domain\Calculation\OneZeroEligibility.cs", "avgHours + 1e-9 >= minHours", "avgHours + 1e-9 > minHours"),
        ("sort: stable tie-break reversed", @"src\TaxCredit.Domain\Numerics\PySort.cs", "return x.Index.CompareTo(y.Index);", "return y.Index.CompareTo(x.Index);"),
    ];

    [Fact]
    public void Each_deliberate_defect_in_a_copy_of_the_port_is_caught_by_the_harness()
    {
        if (Environment.GetEnvironmentVariable("TCC_RUN_MUTATION_TESTS") != "1")
        {
            output.WriteLine("skipped: set TCC_RUN_MUTATION_TESTS=1 to run (each mutation needs a build).");
            return;
        }

        var parity = GoldenFiles.ParityDirectory;
        var repo = Directory.GetParent(parity)!.FullName;
        var caught = new List<string>();
        var missed = new List<string>();
        foreach (var (name, file, oldText, newText) in Mutations)
        {
            var root = Path.Combine(Path.GetTempPath(), "tcc-mutant-" + Guid.NewGuid().ToString("N")[..8]);
            try
            {
                Copy(Path.Combine(repo, "dotnet"), Path.Combine(root, "dotnet"));
                Copy(parity, Path.Combine(root, "parity"));
                Run("cmd.exe", $"/c mklink /J \"{Path.Combine(root, "backend")}\" \"{Path.Combine(repo, "backend")}\"", root, null);
                var target = Path.Combine(root, "dotnet", file);
                var text = File.ReadAllText(target);
                Assert.Contains(oldText, text, StringComparison.Ordinal);
                File.WriteAllText(target, text.Replace(oldText, newText, StringComparison.Ordinal));

                var env = new Dictionary<string, string> { ["TCC_FUZZ_N"] = "2000", ["TCC_RUN_MUTATION_TESTS"] = "0" };
                var (exit, log) = Run("dotnet", "test tests\\TaxCredit.Parity.Tests --filter \"FullyQualifiedName~GoldenEngineTests|FullyQualifiedName~DifferentialFuzz\"", Path.Combine(root, "dotnet"), env);
                var failedLines = log.Split('\n').Count(l => l.Contains("diverged", StringComparison.Ordinal) || l.Contains("mismatches", StringComparison.Ordinal));
                output.WriteLine($"{name}: exit={exit}, {failedLines} failure summaries");
                (exit != 0 && failedLines > 0 ? caught : missed).Add(name);
            }
            finally
            {
                Run("cmd.exe", $"/c rmdir \"{Path.Combine(root, "backend")}\"", root, null);
                if (Directory.Exists(root))
                {
                    Directory.Delete(root, true);
                }
            }
        }

        Assert.True(missed.Count == 0, "mutations NOT caught: " + string.Join("; ", missed));
        output.WriteLine("caught: " + string.Join("; ", caught));
    }

    private static void Copy(string from, string to)
    {
        Directory.CreateDirectory(to);
        foreach (var dir in Directory.EnumerateDirectories(from))
        {
            var leaf = Path.GetFileName(dir);
            if (leaf is "artifacts" or "bin" or "obj" or "regressions")
            {
                continue;
            }

            Copy(dir, Path.Combine(to, leaf));
        }

        foreach (var file in Directory.EnumerateFiles(from))
        {
            File.Copy(file, Path.Combine(to, Path.GetFileName(file)), true);
        }
    }

    private static (int Exit, string Log) Run(string exe, string args, string cwd, Dictionary<string, string>? env)
    {
        var info = new ProcessStartInfo(exe, args) { WorkingDirectory = cwd, RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false };
        if (env is not null)
        {
            foreach (var kv in env)
            {
                info.Environment[kv.Key] = kv.Value;
            }
        }

        using var p = Process.Start(info)!;
        var stdout = p.StandardOutput.ReadToEndAsync();
        var stderr = p.StandardError.ReadToEndAsync();
        p.WaitForExit();
        return (p.ExitCode, stdout.Result + stderr.Result);
    }
}
