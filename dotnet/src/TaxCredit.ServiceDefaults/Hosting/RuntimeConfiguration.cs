using Microsoft.Extensions.Configuration;
using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.ServiceDefaults.Hosting;

/// <summary>A per-host environment overlay; hooks do not alter the shared machine's environment.</summary>
public sealed class RuntimeConfiguration(IConfiguration original) : IRuntimeConfiguration
{
    private readonly Dictionary<string, string?> _overlay = new(StringComparer.Ordinal);
    private readonly object _lock = new();

    /// <inheritdoc />
    public string? Get(string name)
    {
        lock (_lock)
        {
            if (name == "CONTRACT_HOOKS") { return original[name]; }
            return _overlay.TryGetValue(name, out var value) ? value : original[name] ?? Default(name);
        }
    }

    private string? Default(string name) => name switch
    {
        "ENVIRONMENT" => "local",
        "AUTH_MODE" => (original["ENVIRONMENT"] ?? "local") == "local" ? "none" : "entra",
        "DATA_SOURCE" => "csv",
        "DATA_CLASSIFICATION" => "synthetic",
        "PERSISTENCE_PROVIDER" => "sqlite",
        "ARTIFACT_STORE" => "local",
        "CHANNEL_ENFORCE_WRITER_FOR_USERS" => "false",
        "RATE_LIMIT_PER_MINUTE" => "60",
        "FISCAL_RULES_POLICY" => "assume",
        "CHANNEL_WRITER_SOURCE" => "allowlist",
        _ => null,
    };

    /// <summary>Applies set then unset, as the harness does.</summary>
    public void Apply(IReadOnlyDictionary<string, string> set, IReadOnlyList<string> unset)
    {
        ArgumentNullException.ThrowIfNull(set);
        ArgumentNullException.ThrowIfNull(unset);
        if (set.Keys.Concat(unset).Any(k => k is "CONTRACT_HOOKS" or "ENVIRONMENT" or "PERSISTENCE_PROVIDER"
            or "OPERATIONAL_DB" or "REPOSITORY_ROOT" or "SEED_ROOT" or "RULES_DIR" or "ARTIFACT_STORE" or "ARTIFACT_LOCAL_ROOT"))
        {
            throw new ArgumentException("Startup-only settings cannot be changed through the environment hook.", nameof(set));
        }
        lock (_lock)
        {
            foreach (var (name, value) in set)
            {
                _overlay[name] = value;
            }

            foreach (var name in unset)
            {
                _overlay[name] = null;
            }
        }
    }

    /// <summary>Restores startup configuration before selecting the next scenario.</summary>
    public void Reset()
    {
        lock (_lock)
        {
            _overlay.Clear();
        }
    }

    /// <summary>Enables rollback when a control request supplies an invalid immutable-consumer snapshot.</summary>
    public IReadOnlyDictionary<string, string?> Capture()
    {
        lock (_lock) { return new Dictionary<string, string?>(_overlay, StringComparer.Ordinal); }
    }

    /// <summary>Restores only this host's overlay, never machine or process variables.</summary>
    public void Restore(IReadOnlyDictionary<string, string?> values)
    {
        ArgumentNullException.ThrowIfNull(values);
        lock (_lock)
        {
            _overlay.Clear();
            foreach (var (key, value) in values) { _overlay.Add(key, value); }
        }
    }
}
