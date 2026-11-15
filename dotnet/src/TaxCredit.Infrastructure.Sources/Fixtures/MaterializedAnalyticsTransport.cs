using System.Globalization;
using System.IO.Compression;
using System.Text.Json;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Infrastructure.Sources.Mapping;
using TaxCredit.Infrastructure.Sources.Projection;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Infrastructure.Sources.Fixtures;

/// <summary>Offline logical SQL endpoint over committed P2 materialized tables, not a runtime Delta reader.</summary>
public sealed class MaterializedAnalyticsTransport : IAnalyticsTransport
{
    private readonly SourceMapping _mapping;
    private readonly IReadOnlyDictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object?>>> _tables;
    private readonly IReadOnlyDictionary<string, IReadOnlyList<string>> _schemas;

    /// <summary>Synthetic fixture construction with explicit schema permits empty-but-present tables and missing-table tests.</summary>
    public MaterializedAnalyticsTransport(SourceMapping mapping,
        IReadOnlyDictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object?>>> physicalTables,
        IReadOnlyDictionary<string, IReadOnlyList<string>>? schemas = null)
    {
        _mapping = mapping;
        _tables = physicalTables;
        _schemas = schemas ?? physicalTables.ToDictionary(p => p.Key,
            p => (IReadOnlyList<string>)(p.Value.Count > 0 ? p.Value[0].Keys.ToArray() : mapping.Tables.Values
                .Single(t => t.Physical == p.Key).Fields.Values.Select(f => f.Column).ToArray()), StringComparer.Ordinal);
    }

    /// <summary>Reads only an explicitly selected local seed directory, with a decompressed byte ceiling.</summary>
    public static MaterializedAnalyticsTransport LoadP2(string sourceDirectory, SourceMapping? mapping = null,
        long maximumDecompressedBytes = 256_000_000)
    {
        var active = mapping ?? SourceMapping.Load();
        var tables = new Dictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object?>>>(StringComparer.Ordinal);
        long consumed = 0;
        foreach (var table in active.Tables.Values)
        {
            var path = Path.Combine(sourceDirectory, table.Physical + ".jsonl.gz");
            if (!File.Exists(path)) { continue; }
            using var file = File.OpenRead(path);
            using var gzip = new GZipStream(file, CompressionMode.Decompress);
            using var reader = new StreamReader(gzip);
            var rows = new List<IReadOnlyDictionary<string, object?>>();
            while (reader.ReadLine() is { } line)
            {
                consumed += System.Text.Encoding.UTF8.GetByteCount(line) + 1;
                if (consumed > maximumDecompressedBytes) { throw new SourceTooLarge(maximumDecompressedBytes); }
                using var doc = JsonDocument.Parse(line);
                rows.Add(doc.RootElement.EnumerateObject().ToDictionary(p => p.Name, p => JsonValue(p.Value), StringComparer.Ordinal));
            }
            tables.Add(table.Physical, rows);
        }
        return new MaterializedAnalyticsTransport(active, tables);
    }

    /// <summary>This adapter is explicitly offline, irrespective of credentials/configuration in the process.</summary>
    public const string Provenance = "materialized-P2-offline-analytics-substitution";
    /// <inheritdoc />
    public bool IsConfigured => true;
    /// <inheritdoc />
    public IReadOnlyList<string> Columns(string schema, string physicalTable, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return _schemas.TryGetValue(physicalTable, out var columns) ? columns : [];
    }
    /// <inheritdoc />
    public IEnumerable<IReadOnlyDictionary<string, object?>> Read(AnalyticsQuery query, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(query);
        if (query.Kind is "scope" or "footprint") { return ScopeRows(query, cancellationToken); }
        if (query.Kind == "fingerprint") { return FingerprintRows(query, cancellationToken); }
        return ScanRows(query, cancellationToken);
    }
    /// <inheritdoc />
    public IDisposable SharedScope() => EmptyScope.Instance;

    private IEnumerable<IReadOnlyDictionary<string, object?>> ScanRows(AnalyticsQuery query, CancellationToken cancellationToken)
    {
        var table = _mapping.Tables[query.Table];
        if (!_tables.TryGetValue(table.Physical, out var rows)) { throw new SourceTableMissing(query.Table); }
        var found = _mapping.Resolve(query.Table, _schemas[table.Physical]).Found;
        var values = query.FilterValues?.ToHashSet();
        foreach (var row in rows)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (query.FilterField is { } filter && (values is null
                || !values.Contains(SourceValues.Get(row, found[filter])))) { continue; }
            yield return query.Columns.ToDictionary(p => p.Key, p => SourceValues.Get(row, p.Value), StringComparer.Ordinal);
        }
    }

    private IEnumerable<IReadOnlyDictionary<string, object?>> LogicalRows(string table, long? accountId = null)
    {
        var source = _mapping.Tables[table];
        if (!_tables.TryGetValue(source.Physical, out var rows)) { throw new SourceTableMissing(table); }
        var columns = _mapping.Resolve(table, _schemas[source.Physical]).Found;
        return rows.Select(row => (IReadOnlyDictionary<string, object?>)columns.ToDictionary(p => p.Key,
            p => SourceValues.Get(row, p.Value), StringComparer.Ordinal))
            .Where(r => accountId is null || SourceValues.Id(r, "account_id") == accountId);
    }

    private IEnumerable<IReadOnlyDictionary<string, object?>> ScopeRows(AnalyticsQuery query, CancellationToken cancellationToken)
    {
        var account = query.Kind == "scope" ? Convert.ToInt64(query.Parameters[0], CultureInfo.InvariantCulture) : (long?)null;
        var locations = LogicalRows("Location").ToDictionary(r => SourceValues.Id(r, "location_id")!.Value);
        var addresses = LogicalRows("Address").ToDictionary(r => SourceValues.Id(r, "address_id")!.Value);
        var counties = LogicalRows("StateCountyZip").ToDictionary(r => SourceValues.Id(r, "state_county_zip_id")!.Value);
        var observations = new List<(long Account, long Year, string State, DateOnly Paid)>();
        foreach (var row in LogicalRows("Payroll", account))
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (SourceValues.Date(row, "pay_period_start") is null || SourceValues.Date(row, "pay_period_end") is not { } end) { continue; }
            var paid = SourceValues.Date(row, "pay_date") ?? (_mapping.NullPayDateMode == "period_end" ? end : (DateOnly?)null);
            if (paid is null) { continue; }
            var locationId = _mapping.WorksiteMode switch
            {
                "location_only" => SourceValues.Id(row, "location_id"),
                "worksite_only" => SourceValues.Id(row, "worksite_location_id"),
                _ => SourceValues.Id(row, "worksite_location_id") ?? SourceValues.Id(row, "location_id"),
            };
            var tenant = SourceValues.Id(row, "account_id")!.Value;
            var loc = locationId is { } lid && locations.TryGetValue(lid, out var l) && SourceValues.Id(l, "account_id") == tenant ? l : null;
            var addressId = loc is null ? null : SourceValues.Id(loc, "address_id");
            var address = addressId is { } aid && addresses.TryGetValue(aid, out var a) ? a : null;
            var countyId = address is null ? null : SourceValues.Id(address, "state_county_zip_id");
            var county = countyId is { } cid && counties.TryGetValue(cid, out var c) ? c : null;
            var state = county is null ? "" : SourceValues.Text(county, "state_abbr");
            if (state.Length == 0 && address is not null) { state = SourceValues.Text(address, "state_original"); }
            observations.Add((tenant, paid.Value.Year, state.ToUpperInvariant(), paid.Value));
        }
        if (query.Kind == "footprint")
        {
            return observations.Select(r => (r.Account, r.State)).Distinct().Select(r => Dict(
                ("account_id", r.Account), ("work_state", r.State)));
        }
        return observations.GroupBy(r => (r.Year, r.State, r.Paid)).Select(g => Dict(
            ("tax_year", g.Key.Year), ("work_state", g.Key.State), ("pay_date", g.Key.Paid), ("rows_in", (long)g.Count())));
    }

    private IEnumerable<IReadOnlyDictionary<string, object?>> FingerprintRows(AnalyticsQuery query, CancellationToken cancellationToken)
    {
        var account = Convert.ToInt64(query.Parameters[0], CultureInfo.InvariantCulture);
        long count = 0;
        string? maximum = null;
        foreach (var row in LogicalRows("Payroll", account))
        {
            cancellationToken.ThrowIfCancellationRequested();
            count++;
            var modified = SourceValues.Timestamp(SourceValues.Get(row, "modify_date"));
            if (modified is not null && (maximum is null || string.CompareOrdinal(modified, maximum) > 0)) { maximum = modified; }
        }
        return [Dict(("row_count", count), ("maximum_modified", maximum))];
    }

    private static Dictionary<string, object?> Dict(params (string Key, object? Value)[] cells) =>
        cells.ToDictionary(p => p.Key, p => p.Value, StringComparer.Ordinal);
    private static object? JsonValue(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.Null => null,
        JsonValueKind.String => value.GetString(),
        JsonValueKind.True => true,
        JsonValueKind.False => false,
        JsonValueKind.Number => value.TryGetInt64(out var integer) ? integer : (object)value.GetDouble(),
        _ => throw new InvalidDataException("A materialized source cell must be scalar."),
    };
}
