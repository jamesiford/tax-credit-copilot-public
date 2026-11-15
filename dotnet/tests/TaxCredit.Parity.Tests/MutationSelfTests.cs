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
        ("sum: a 3.14-style compensated int after a float", @"src\TaxCredit.Domain\Numerics\PySum.cs", "f += (double)items[i].IntValue;", "var xi = (double)items[i].IntValue; var ti = f + xi; c += Math.Abs(f) >= Math.Abs(xi) ? (f - ti) + xi : (xi - ti) + f; f = ti;"),
        ("sort: stable tie-break reversed", @"src\TaxCredit.Domain\Numerics\PySort.cs", "return x.Index.CompareTo(y.Index);", "return y.Index.CompareTo(x.Index);"),
        ("proximity rounding: half-up becomes banker's on the binary value", @"src\TaxCredit.Domain\Calculation\ProximityCoerce.cs", "return OneZeroEligibility.RoundHalfUp(value, places);", "return PyRound.Round(value, places);"),
        ("proximity comparison: hours floor >= becomes >", @"src\TaxCredit.Domain\Calculation\Proximity.cs", "var passedHours = avgHours >= minHours;", "var passedHours = avgHours > minHours;"),
        ("proximity comparison: recorded verdict ignored", @"src\TaxCredit.Domain\Calculation\Proximity.cs", "var eligible = recorded is not null ? ProximityCoerce.Truthy(recorded) : derived;", "var eligible = derived;"),
        ("proximity max/min inversion: the larger need no longer binds", @"src\TaxCredit.Domain\Calculation\Proximity.cs", "PyArith.Max(needs)", "PyArith.Min(needs)"),
        ("proximity max/min inversion: the smaller cushion no longer binds", @"src\TaxCredit.Domain\Calculation\Proximity.cs", "PyArith.Min(hoursHeadroom, wagesHeadroomHours.Value)", "PyArith.Max(hoursHeadroom, wagesHeadroomHours.Value)"),
        ("proximity ordering: id tie-break reversed", @"src\TaxCredit.Domain\Calculation\ProximityCohorts.cs", "PyStr.Compare(x.Id, y.Id)", "PyStr.Compare(y.Id, x.Id)"),
        ("proximity counting: population no longer overrides the ineligible count", @"src\TaxCredit.Domain\Calculation\ProximityCohorts.cs", ".Add(\"ineligible\", usePopulation ? ProximityCoerce.ToInt(Req(population!, \"ineligible\")) : (long)ineligible.Count)", ".Add(\"ineligible\", (long)ineligible.Count)"),
        ("decimal rounding: the 28-digit context rounds half up instead of half even", @"src\TaxCredit.Domain\Numerics\PyDecimalOps.cs", "if (cmp > 0 || (cmp == 0 && !q.IsEven))", "if (cmp >= 0)"),
        ("claims rounding: fallen_by rounds away from zero instead of half even", @"src\TaxCredit.Domain\Claims\ClaimReadings.cs", "PyRound.Round(peak.AverageHeadcount.Value - latest.AverageHeadcount.Value, 2)", "Math.Round(peak.AverageHeadcount.Value - latest.AverageHeadcount.Value, 2, MidpointRounding.AwayFromZero)"),
        ("claims rounding: jobs_margin truncates instead of rounding", @"src\TaxCredit.Domain\Claims\ProgramClaim.Readings.cs", "PyRound.Round(netNew - threshold, 2)", "Math.Truncate((netNew - threshold) * 100) / 100"),
        ("claims comparison: materiality <= becomes < (confirmed)", @"src\TaxCredit.Domain\Claims\ProgramClaim.Readings.cs", "PyDecimalOps.Compare(PyDecimalOps.Abs(variance), ClaimMoney.Materiality) <= 0", "PyDecimalOps.Compare(PyDecimalOps.Abs(variance), ClaimMoney.Materiality) < 0"),
        ("claims comparison: materiality <= becomes < (correctly not claimed)", @"src\TaxCredit.Domain\Claims\ProgramClaim.Readings.cs", "PyDecimalOps.Compare(IdentifiedUsd, ClaimMoney.Materiality) <= 0", "PyDecimalOps.Compare(IdentifiedUsd, ClaimMoney.Materiality) < 0"),
        ("claims comparison: on the line is exclusive of one whole job", @"src\TaxCredit.Domain\Claims\ProgramClaim.Readings.cs", "Math.Abs(margin) <= OnTheLineJobs", "Math.Abs(margin) < OnTheLineJobs"),
        ("claims gate: exposure no longer needs a verified claim", @"src\TaxCredit.Domain\Claims\ProgramClaim.Readings.cs", "if (IsExposure && Provenance.Verified())", "if (IsExposure)"),
        ("claims gate: an unverified claim is netted into the outstanding test", @"src\TaxCredit.Domain\Claims\ProgramClaim.Readings.cs", "var outstanding = Provenance.Verified() ? OpportunityUsd : IdentifiedUsd;", "var outstanding = OpportunityUsd;"),
        ("claims clamp: jobs_to_threshold no longer clamps at zero", @"src\TaxCredit.Domain\Claims\ProgramClaim.Readings.cs", "PyRound.Round(gap > 0.0 ? gap : 0.0, 2)", "PyRound.Round(gap, 2)"),
        ("claims comparison: declining peak takes the last maximum instead of the first", @"src\TaxCredit.Domain\Claims\ClaimReadings.cs", "if (c.AverageHeadcount > peak.AverageHeadcount)", "if (c.AverageHeadcount >= peak.AverageHeadcount)"),
        ("claims ordering: band rank of declining moves below unclaimed", @"src\TaxCredit.Domain\Claims\ClaimEnumExtensions.cs", "PriorityBand.Declining => 2,", "PriorityBand.Declining => 4,"),
        ("coverage ordering: identified dollars ascending within a band", @"src\TaxCredit.Domain\Claims\CoverageSituation.cs", "-c.IdentifiedUsd.ToDouble()", "c.IdentifiedUsd.ToDouble()"),
        ("coverage ordering: tax year tie-break reversed", @"src\TaxCredit.Domain\Claims\CoverageSituation.cs", "x.TaxYear.CompareTo(y.TaxYear)", "y.TaxYear.CompareTo(x.TaxYear)"),
        ("coverage ordering: programme totals in insertion order, not sorted", @"src\TaxCredit.Domain\Claims\Coverage.cs", "PySort.Sorted(grouped.Keys, k => k, PyStr.Comparer)", "grouped.Keys"),
        ("coverage netting: opportunity summed from the signed variance", @"src\TaxCredit.Domain\Claims\Coverage.cs", "claims.Select(c => c.OpportunityUsd)", "claims.Select(c => c.VarianceUsd)"),
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
                var (exit, log) = Run("dotnet", "test tests\\TaxCredit.Parity.Tests --filter \"FullyQualifiedName~GoldenEngineTests|FullyQualifiedName~DifferentialFuzz|FullyQualifiedName~Sum_matches_python|FullyQualifiedName~ProximityParityTests|FullyQualifiedName~ClaimsParityTests|FullyQualifiedName~CoverageParityTests\"", Path.Combine(root, "dotnet"), env);
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
