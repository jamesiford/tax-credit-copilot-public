using Microsoft.Extensions.Configuration;

namespace TaxCredit.ServiceDefaults.Hosting;

/// <summary>
/// One-release fallbacks for settings renamed away from the product prefix. This table is the only place the old
/// names live for the .NET hosts. A host that still carries the old name keeps working: the old value is read when
/// the new name is unset, and the new name always wins when both are set. Only the NAME of a deprecated variable is
/// ever reported, never its value. To remove the aliases next release, delete this file and the calls to
/// <see cref="Read"/> and <see cref="Report"/>.
/// </summary>
public static class LegacySettingAliases
{
    /// <summary>New setting name to the deprecated name it replaces.</summary>
    public static IReadOnlyDictionary<string, string> Table { get; } = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["PERSISTENCE_PROVIDER"] = "TCC_PERSISTENCE_PROVIDER",
        ["REPOSITORY_ROOT"] = "TCC_REPOSITORY_ROOT",
        ["SEED_ROOT"] = "TCC_SEED_ROOT",
        ["WORKER_ONCE"] = "TCC_WORKER_ONCE",
        ["CONTRACT_HOOKS"] = "TCC_CONTRACT_HOOKS",
        ["CONTRACT_PROFILE"] = "TCC_CONTRACT_PROFILE",
        ["FEATURE_ASSEMBLIES"] = "TCC_FEATURE_ASSEMBLIES",
        ["RETAIN_SUPERSEDED_RUNS"] = "TCC_RETAIN_SUPERSEDED_RUNS",
        ["BULK_LOAD"] = "TCC_BULK_LOAD",
        ["BULK_LOAD_MIN_ROWS"] = "TCC_BULK_LOAD_MIN_ROWS",
        ["BULK_TIMEOUT_SECONDS"] = "TCC_BULK_TIMEOUT_SECONDS",
    };

    /// <summary>Reads a setting by its new name, falling back to the deprecated name when the new one is unset.</summary>
    /// <param name="configuration">The configuration to read.</param>
    /// <param name="name">The new setting name.</param>
    /// <returns>The value, or null when neither name is set.</returns>
    public static string? Read(IConfiguration configuration, string name)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        return configuration[name] ?? (Table.TryGetValue(name, out var legacy) ? configuration[legacy] : null);
    }

    /// <summary>The deprecated names that currently supply a value, because their new name is unset.</summary>
    /// <param name="configuration">The configuration to inspect.</param>
    /// <returns>Deprecated names in table order.</returns>
    public static IReadOnlyList<string> InUse(IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        return Table.Where(pair => configuration[pair.Key] is null && configuration[pair.Value] is not null)
            .Select(pair => pair.Value).ToArray();
    }

    /// <summary>Writes one line per deprecated name in use. The line names the variable and never its value.</summary>
    /// <param name="configuration">The configuration to inspect.</param>
    /// <param name="write">Where each line goes.</param>
    public static void Report(IConfiguration configuration, Action<string> write)
    {
        ArgumentNullException.ThrowIfNull(write);
        foreach (var legacy in InUse(configuration))
        {
            var current = Table.First(pair => pair.Value == legacy).Key;
            write($"Deprecated environment variable {legacy} is in use; set {current} instead.");
        }
    }

    /// <summary>Reads a setting by its new name through the alias table; the host-wide spelling of <c>configuration[name]</c>.</summary>
    /// <param name="configuration">The configuration to read.</param>
    /// <param name="name">The new setting name.</param>
    /// <returns>The value, or null when neither name is set.</returns>
    public static string? Setting(this IConfiguration configuration, string name) => Read(configuration, name);
}
