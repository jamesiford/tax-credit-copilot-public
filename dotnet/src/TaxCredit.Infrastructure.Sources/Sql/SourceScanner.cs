using System.Collections.Concurrent;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Infrastructure.Sources.Mapping;

namespace TaxCredit.Infrastructure.Sources.Sql;

/// <summary>Projected filtered scans; a missing tenant/key column is a refusal, never an unfiltered query.</summary>
public sealed class SourceScanner
{
    /// <summary>Headroom below SQL Server's 2,100-parameter ceiling.</summary>
    public const int IdBatchSize = 900;
    private readonly ConcurrentDictionary<string, ColumnResolution> _columns = new(StringComparer.Ordinal);
    private readonly IAnalyticsTransport _transport;
    private readonly long _maximumRows;

    /// <summary>Each scanner has its own mapping/schema cache; no cross-configuration static state.</summary>
    public SourceScanner(IAnalyticsTransport transport, SourceMapping mapping, string? schema = null,
        long maximumRows = 1_000_000)
    {
        ArgumentNullException.ThrowIfNull(transport);
        ArgumentNullException.ThrowIfNull(mapping);
        ArgumentOutOfRangeException.ThrowIfLessThan(maximumRows, 1);
        Schema = schema is null ? Domain.DataMap.PhysicalNames.Active.Map.SourceSchema : schema.Trim();
        if (Schema.Length > 0) { SourceMapping.ValidateIdentifier(Schema); }
        _transport = transport;
        Mapping = mapping;
        _maximumRows = maximumRows;
    }

    /// <summary>Blank means a non-schema-enabled lakehouse; SQL metadata resolves dbo.</summary>
    public string Schema { get; }
    /// <summary>The immutable active mapping.</summary>
    public SourceMapping Mapping { get; }
    /// <summary>Source configuration readiness, not connectivity health.</summary>
    public bool IsConfigured => _transport.IsConfigured;
    /// <summary>The transport's evidence label; offline substitutions cannot silently claim SQL provenance.</summary>
    public string SourceProvenance => _transport.SourceProvenance;
    /// <summary>True when blank SOURCE_SCHEMA requires operator confirmation.</summary>
    public bool HasBlankSchemaWarning => Schema.Length == 0;
    /// <summary>Shared source connection lifetime; no Warehouse connection is involved.</summary>
    public IDisposable SharedScope() => _transport.SharedScope();
    /// <summary>Explicit reset for source reload/metadata changes.</summary>
    public void ClearCache() => _columns.Clear();
    /// <summary>Qualified source table, with dbo for non-schema-enabled SQL endpoints.</summary>
    public string TableName(string logical) => SourceMapping.Quote(Schema.Length == 0 ? "dbo" : Schema)
        + "." + SourceMapping.Quote(Mapping.Tables[logical].Physical);

    /// <summary>Missing tables are not cached, so adding a previously absent optional table is observed.</summary>
    public ColumnResolution ColumnsOf(string logical, CancellationToken cancellationToken = default)
    {
        if (!IsConfigured) { throw new SourceNotConfigured(); }
        if (_columns.TryGetValue(logical, out var cached)) { return cached; }
        var actual = _transport.Columns(Schema, Mapping.Tables[logical].Physical, cancellationToken);
        if (actual.Count == 0) { throw new SourceTableMissing(logical); }
        var resolution = Mapping.Resolve(logical, actual);
        if (resolution.MissingRequired.Count != 0) { throw new SourceSchemaMismatch(logical, resolution.MissingRequired); }
        return _columns.GetOrAdd(logical, resolution);
    }

    /// <summary>One tenant statement or bounded deterministic ID batches, with immediate streaming size enforcement.</summary>
    public IReadOnlyList<IReadOnlyDictionary<string, object?>> Scan(string logical, long? accountId = null,
        string? key = null, IEnumerable<long>? ids = null, CancellationToken cancellationToken = default)
    {
        var table = Mapping.Tables[logical];
        if (table.TenantField is not null && accountId is null && key is null && logical != "Account")
        {
            throw new ArgumentException("A tenant table requires a selected account or bounded keyed read.");
        }
        var resolution = ColumnsOf(logical, cancellationToken);
        var found = resolution.Found;
        var filter = accountId is not null ? table.TenantField : key;
        if (accountId is not null && filter is null) { throw new ArgumentException("This table requires a keyed read, not a tenant scan."); }
        if (filter is not null && !found.ContainsKey(filter)) { throw new SourceSchemaMismatch(logical, [filter]); }
        var columns = found.Where(p => table.Fields[p.Key].Engine || p.Key == filter)
            .ToDictionary(p => p.Key, p => p.Value, StringComparer.Ordinal);
        if (columns.Count == 0) { return []; }
        var batches = accountId is { } account ? new[] { new object?[] { account } }
            : key is not null ? (ids ?? []).Distinct().Order().Chunk(IdBatchSize).Select(b => b.Cast<object?>().ToArray())
            : new[] { Array.Empty<object?>() };
        using var span = TaxCredit.Application.Hosting.RunSpans.Start("source.scan");
        span?.SetTag("table", logical);
        var output = new List<IReadOnlyDictionary<string, object?>>();
        foreach (var batch in batches)
        {
            var sql = $"SELECT {string.Join(", ", columns.Values.Select(SourceMapping.Quote))} FROM {TableName(logical)}";
            if (filter is not null)
            {
                sql += accountId is not null ? $" WHERE {SourceMapping.Quote(found[filter])} = @p0"
                    : $" WHERE {SourceMapping.Quote(found[filter])} IN ({string.Join(",", Enumerable.Range(0, batch.Length).Select(i => "@p" + i))})";
            }
            var query = new AnalyticsQuery(sql, batch, logical, columns, filter, batch);
            foreach (var row in _transport.Read(query, cancellationToken))
            {
                if (output.Count >= _maximumRows) { throw new SourceTooLarge(_maximumRows); }
                output.Add(row);
            }
        }
        span?.SetTag("rows", output.Count);
        return output;
    }

    /// <summary>Executes an adapter-built aggregate with the same cancellation and source transport.</summary>
    public IEnumerable<IReadOnlyDictionary<string, object?>> ReadAggregate(AnalyticsQuery query,
        CancellationToken cancellationToken = default) => _transport.Read(query, cancellationToken);
}
