using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Infrastructure.Sources.Mapping;
using TaxCredit.Infrastructure.Sources.Projection;

namespace TaxCredit.Infrastructure.Sources.Sql;

/// <summary>Aggregate SQL shares mapping and named transforms with the row projector, without reading payroll into memory.</summary>
public sealed class SourceQueries(SourceScanner scanner)
{
    /// <summary>One grouped observation answers all scope dimensions from the same row population.</summary>
    public AnalyticsQuery Scope(long accountId)
    {
        var paid = Paid();
        var state = State();
        var year = $"YEAR({paid})";
        var sql = $"SELECT {year}, {state}, {paid}, COUNT_BIG(*) {Joins()} WHERE {Ref("Payroll", "account_id", "p")} = @p0"
            + $" AND {HasSpan()} GROUP BY {year}, {state}, {paid}";
        return new AnalyticsQuery(sql, [accountId], "Payroll", Outputs("tax_year", "work_state", "pay_date", "rows_in"), Kind: "scope");
    }

    /// <summary>One portfolio GROUP BY, with no per-account payroll loads.</summary>
    public AnalyticsQuery Footprint()
    {
        var tenant = Ref("Payroll", "account_id", "p");
        var state = State();
        return new AnalyticsQuery($"SELECT {tenant}, {state} {Joins()} WHERE {HasSpan()} GROUP BY {tenant}, {state}",
            [], "Payroll", Outputs("account_id", "work_state"), Kind: "footprint");
    }

    /// <summary>A count/max observation on raw account payroll, including rows the projector would exclude.</summary>
    public (AnalyticsQuery Query, bool HasModifiedColumn) Fingerprint(long accountId)
    {
        var found = scanner.ColumnsOf("Payroll").Found;
        var modified = found.TryGetValue("modify_date", out var column) ? SourceMapping.Quote(column) : "CAST(NULL AS datetime2)";
        var query = new AnalyticsQuery($"SELECT COUNT_BIG(*), MAX({modified}) FROM {scanner.TableName("Payroll")}"
            + $" WHERE {SourceMapping.Quote(found["account_id"])} = @p0", [accountId], "Payroll",
            Outputs("row_count", "maximum_modified"), Kind: "fingerprint");
        return (query, column is not null);
    }

    private static Dictionary<string, string> Outputs(params string[] names) =>
        names.ToDictionary(n => n, n => n, StringComparer.Ordinal);
    private string Ref(string table, string field, string alias)
    {
        var found = scanner.ColumnsOf(table).Found;
        return found.TryGetValue(field, out var actual) ? alias + "." + SourceMapping.Quote(actual) : "NULL";
    }
    private string Paid()
    {
        var paid = Ref("Payroll", "pay_date", "p");
        return scanner.Mapping.NullPayDateMode == "period_end" ? $"COALESCE({paid}, {Ref("Payroll", "pay_period_end", "p")})" : paid;
    }
    private string State() => $"UPPER(COALESCE(NULLIF({Ref("StateCountyZip", "state_abbr", "s")}, ''),"
        + $" NULLIF({Ref("Address", "state_original", "a")}, ''), ''))";
    private string HasSpan() => $"{Ref("Payroll", "pay_period_start", "p")} IS NOT NULL AND {Ref("Payroll", "pay_period_end", "p")} IS NOT NULL"
        + (scanner.Mapping.NullPayDateMode == "exclude" ? $" AND {Paid()} IS NOT NULL" : "");
    private string Location()
    {
        var worksite = Ref("Payroll", "worksite_location_id", "p");
        var location = Ref("Payroll", "location_id", "p");
        return scanner.Mapping.WorksiteMode switch
        {
            "location_only" => location,
            "worksite_only" => worksite,
            _ => $"COALESCE(NULLIF({worksite}, 0), {location})",
        };
    }
    private string Joins() => $"FROM {scanner.TableName("Payroll")} p LEFT JOIN {scanner.TableName("Location")} l"
        + $" ON {Ref("Location", "location_id", "l")} = {Location()} AND {Ref("Location", "account_id", "l")} = {Ref("Payroll", "account_id", "p")}"
        + $" LEFT JOIN {scanner.TableName("Address")} a ON {Ref("Address", "address_id", "a")} = {Ref("Location", "address_id", "l")}"
        + $" LEFT JOIN {scanner.TableName("StateCountyZip")} s ON {Ref("StateCountyZip", "state_county_zip_id", "s")} = {Ref("Address", "state_county_zip_id", "a")}";
}

/// <summary>Version stand-in records limits explicitly; it is not a Delta identity or a snapshot guarantee.</summary>
public sealed class SourceFingerprintReader(SourceScanner scanner, string provenance = "sql-analytics-count-max")
    : ISourceFingerprintReader
{
    /// <inheritdoc />
    public SourceFingerprint Fingerprint(long accountId)
    {
        var (query, hasModified) = new SourceQueries(scanner).Fingerprint(accountId);
        var rows = scanner.ReadAggregate(query).ToArray();
        if (rows.Length != 1) { throw new SourceSchemaMismatch("Payroll", ["fingerprint_aggregate"]); }
        var count = Convert.ToInt64(rows[0]["row_count"], CultureInfo.InvariantCulture);
        var maximum = SourceValues.Timestamp(rows[0]["maximum_modified"]);
        var status = !hasModified ? "column_missing" : count == 0 ? "empty" : maximum is null ? "all_null" : "present";
        var mappingIdentity = string.Join("\n", scanner.ColumnsOf("Payroll").Found.OrderBy(p => p.Key, StringComparer.Ordinal)
            .Select(p => p.Key + "=" + p.Value));
        var encoding = JsonSerializer.Serialize(new
        {
            version = 1,
            row_count = count,
            maximum_modified = maximum,
            modified_status = status,
            mapping_sha256 = Hash(mappingIdentity),
        });
        return new SourceFingerprint("account-count-max-modified-v1", count, maximum, status, encoding, Hash(encoding), provenance,
            ["Count/max-preserving updates are undetected.", "SQL endpoint synchronization lag is unmeasured.",
             "Rows and the fingerprint are separate non-atomic observations.", "This marker is not a Delta version or a historical snapshot."]);
    }
    private static string Hash(string text) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(text)));
}
