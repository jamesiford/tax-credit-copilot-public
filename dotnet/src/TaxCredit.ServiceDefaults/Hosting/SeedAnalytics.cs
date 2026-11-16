using System.Text.Json;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Infrastructure.Sources.Fixtures;
using TaxCredit.Infrastructure.Sources.Mapping;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.ServiceDefaults.Hosting;

/// <summary>Staged persistence rows feed the existing offline SQL/projector, not a second source implementation.</summary>
public sealed class SeedAnalytics(ISeedData seed, SourceMapping mapping)
{
    private MaterializedAnalyticsTransport? _transport;
    private readonly object _lock = new();

    /// <summary>Loads one generation lazily after reset; no credential can be acquired on this path.</summary>
    public IAnalyticsTransport Transport
    {
        get
        {
            lock (_lock)
            {
                if (_transport is not null) { return _transport; }
                var schemas = seed.Tables();
                if (!schemas.ContainsKey("Payroll")) { throw new SourceNotConfigured(); }
                var tables = schemas.Where(p => mapping.Tables.Values.Any(t => t.Physical == p.Key))
                    .ToDictionary(p => p.Key, p => (IReadOnlyList<IReadOnlyDictionary<string, object?>>)seed.ReadTable(p.Key)
                        .Select(Read).ToArray(), StringComparer.Ordinal);
                _transport = new MaterializedAnalyticsTransport(mapping, tables, schemas);
                return _transport;
            }
        }
    }

    /// <summary>Call only while the host work gate excludes readers and workers.</summary>
    public void Reset()
    {
        lock (_lock) { _transport = null; }
    }

    private static IReadOnlyDictionary<string, object?> Read(string text)
    {
        using var doc = JsonDocument.Parse(text);
        return doc.RootElement.EnumerateObject().ToDictionary(p => p.Name, p => Scalar(p.Value), StringComparer.Ordinal);
    }

    private static object? Scalar(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.Null => null,
        JsonValueKind.String => value.GetString(),
        JsonValueKind.True => true,
        JsonValueKind.False => false,
        JsonValueKind.Number => value.TryGetInt64(out var n) ? n : (object)value.GetDouble(),
        _ => throw new InvalidDataException("Staged source cells must be scalar."),
    };
}
