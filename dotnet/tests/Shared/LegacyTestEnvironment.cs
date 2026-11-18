using System.Runtime.CompilerServices;

namespace TaxCredit.TestSupport;

/// <summary>
/// One-release fallback for the test, bench, fuzz, mutation and oracle switches renamed away from the product prefix:
/// a developer's shell that still carries the old name keeps working. The new name always wins when both are set, and
/// only the NAME of a deprecated variable is written, never its value. Linked into every test project by
/// <c>Directory.Build.props</c>; delete this file with the aliases next release.
/// </summary>
internal static class LegacyTestEnvironment
{
    /// <summary>New name to the deprecated name it replaces.</summary>
    internal static IReadOnlyDictionary<string, string> Table { get; } = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["ORACLE_PYTHON"] = "TCC_PYTHON",
        ["ORACLE_ALLOW_OTHER_PYTHON"] = "TCC_ALLOW_OTHER_PYTHON",
        ["BENCH_RUN"] = "TCC_RUN_BENCH",
        ["BENCH_SIZES"] = "TCC_BENCH_SIZES",
        ["BENCH_LABEL"] = "TCC_BENCH_LABEL",
        ["BENCH_DUMP"] = "TCC_BENCH_DUMP",
        ["BENCH_OUT"] = "TCC_BENCH_OUT",
        ["FUZZ_N"] = "TCC_FUZZ_N",
        ["FUZZ_SEED"] = "TCC_FUZZ_SEED",
        ["FUZZ_PARALLEL"] = "TCC_FUZZ_PARALLEL",
        ["FUZZ_BATCH"] = "TCC_FUZZ_BATCH",
        ["MUTATION_RUN"] = "TCC_RUN_MUTATION_TESTS",
        ["MUTATION_FILTER"] = "TCC_MUTATION_FILTER",
        ["MUTATION_TEST_FILTER"] = "TCC_MUTATION_TEST_FILTER",
        ["TEST_UPDATE_DEVIATIONS"] = "TCC_UPDATE_DEVIATIONS",
        ["TEST_SQLSERVER"] = "TCC_SQLSERVER_TEST",
        ["TEST_LIVE_PROFILE"] = "TCC_LIVE_PROFILE",
        ["TEST_LIVE_SQL_SERVER"] = "TCC_LIVE_SQL_SERVER",
        ["TEST_LIVE_SQL_DATABASE"] = "TCC_LIVE_SQL_DATABASE",
        ["TEST_ENV_FILE"] = "TCC_ENV_FILE",
    };

    [ModuleInitializer]
    internal static void Apply() => Apply(Environment.GetEnvironmentVariable, Environment.SetEnvironmentVariable, Console.Error.WriteLine);

    /// <summary>Copies each deprecated value to its new name when the new name is unset, reporting the name only.</summary>
    internal static void Apply(Func<string, string?> get, Action<string, string?> set, Action<string> report)
    {
        foreach (var (current, legacy) in Table)
        {
            if (get(current) is not null || get(legacy) is not { } value)
            {
                continue;
            }

            set(current, value);
            report($"Deprecated environment variable {legacy} is in use; set {current} instead.");
        }
    }
}
