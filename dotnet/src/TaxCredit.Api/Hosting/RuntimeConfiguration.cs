using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.Api.Hosting;

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
            return _overlay.TryGetValue(name, out var value) ? value : original[name];
        }
    }

    /// <summary>Applies set then unset, as the harness does.</summary>
    public void Apply(IReadOnlyDictionary<string, string> set, IReadOnlyList<string> unset)
    {
        ArgumentNullException.ThrowIfNull(set);
        ArgumentNullException.ThrowIfNull(unset);
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
}
