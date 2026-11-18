using Xunit.Abstractions;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate G3 for the ported families: differential fuzzing of proximity, gold projection, base year, simulation/forecast and credit math against the
/// CPython 3.12 oracle (<c>parity/engine_cli.py</c>, <c>fuzz_ops.py</c>). Each family runs <c>FUZZ_N</c> seeded scenarios (default 20,000; seed
/// <c>FUZZ_SEED</c>, always logged) in batches of <c>FUZZ_BATCH</c> (default 250), each batch in a fresh Python process. A divergence is
/// minimised (ddmin over rows, inputs and fields), saved under <c>parity/goldens/regressions</c>, replayed by
/// <see cref="Saved_family_regressions_still_agree_with_the_python_engine"/> thereafter, and fails the test.
/// </summary>
public sealed class FamilyFuzzTests(ITestOutputHelper output)
{
    private static readonly FuzzFamily[] All = [new ProximityFuzz(), new GoldFuzz(), new BaseYearFuzz(), new SimulationFuzz(), new CreditMathFuzz()];

    [Fact]
    [Trait("Category", "heavy")]
    public void Proximity_scenarios_agree_with_the_python_engine() => Run(All[0]);

    [Fact]
    [Trait("Category", "heavy")]
    public void Gold_projection_scenarios_agree_with_the_python_engine() => Run(All[1]);

    [Fact]
    [Trait("Category", "heavy")]
    public void Base_year_scenarios_agree_with_the_python_engine() => Run(All[2]);

    [Fact]
    [Trait("Category", "heavy")]
    public void Simulation_and_forecast_scenarios_agree_with_the_python_engine() => Run(All[3]);

    [Fact]
    [Trait("Category", "heavy")]
    public void Credit_math_scenarios_agree_with_the_python_engine() => Run(All[4]);

    [Fact]
    public void Saved_family_regressions_still_agree_with_the_python_engine() =>
        Assert.Empty(FamilyFuzzRunner.ReplayRegressions(All.ToDictionary(f => f.Name, StringComparer.Ordinal)));

    private void Run(FuzzFamily family)
    {
        var total = FamilyFuzzRunner.EnvInt("FUZZ_N", 20000);
        var seed = FamilyFuzzRunner.Seed();
        var batch = Math.Max(1, FamilyFuzzRunner.EnvInt("FUZZ_BATCH", 250));
        var parallel = Math.Max(1, FamilyFuzzRunner.EnvInt("FUZZ_PARALLEL", 6));
        output.WriteLine($"fuzz[{family.Name}]: N={total} seed={seed} batch={batch} parallel={parallel} python={PythonSession.PythonExe} ({OracleInterpreter.Version})");
        var outcome = FamilyFuzzRunner.Run(family, total, seed, batch, parallel);
        output.WriteLine($"fuzz[{family.Name}]: {outcome.Total} scenarios in {outcome.Elapsed.TotalSeconds:F0}s, python raised on {outcome.PythonErrors} (compared by exception type and message)");
        output.WriteLine($"fuzz[{family.Name}] operations: " + string.Join(", ", outcome.Ops.Select(k => $"{k.Key}={k.Value}")));
        Assert.True(outcome.Mismatches.Count == 0, $"{outcome.Mismatches.Count} mismatches in {family.Name} (seed {seed}, first of {total}):\n" + string.Join("\n", outcome.Mismatches.Take(5)));
        if (total >= 2000)
        {
            var missing = family.Functions.Where(f => !outcome.Ops.ContainsKey(f)).ToList();
            Assert.True(missing.Count == 0, "functions never generated: " + string.Join(", ", missing));
        }
    }
}
