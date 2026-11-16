using System.Globalization;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Infrastructure.Sources.Projection;

/// <summary>One tenant's logical source rows, including explicit optional-table absence.</summary>
public sealed record SourceDataset(long AccountId,
    IReadOnlyDictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object?>>> Tables,
    IReadOnlyList<string> MissingTables)
{
    /// <summary>Rows of a logical entity; required tables are validated by the reader before construction.</summary>
    public IReadOnlyList<IReadOnlyDictionary<string, object?>> Rows(string table) =>
        Tables.TryGetValue(table, out var rows) ? rows : [];
}

/// <summary>Source-shaped tenant loader, with keyed reads for dimensions that lack tenant columns.</summary>
public sealed class SourceDatasetReader(SourceScanner scanner)
{
    /// <summary>Unknown client returns null before reading payroll. Unconfigured/outage/schema failures propagate.</summary>
    public SourceDataset? Load(long accountId, CancellationToken cancellationToken = default)
    {
        var tables = new Dictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object?>>>(StringComparer.Ordinal);
        var missing = new List<string>();
        tables["Account"] = scanner.Scan("Account", accountId, cancellationToken: cancellationToken);
        if (tables["Account"].Count == 0) { return null; }
        foreach (var table in new[] { "Entity", "Location", "PayCode", "Payroll" })
        {
            tables[table] = scanner.Scan(table, accountId, cancellationToken: cancellationToken);
        }
        ReadKeyed("Address", "address_id", Keys(tables["Location"], "address_id"));
        ReadKeyed("StateCountyZip", "state_county_zip_id", Keys(tables["Address"], "state_county_zip_id"));
        ReadKeyed("Employment", "employee_id", Keys(tables["Payroll"], "employee_id"));
        ReadKeyed("EntityFiscalYearRules", "fiscal_year_rules_id", Keys(tables["Entity"], "fiscal_year_rules_id"));
        ReadKeyed("PayFrequency", "pay_frequency_id", Keys(tables["Payroll"], "pay_frequency_id"));
        return new SourceDataset(accountId, tables, missing);

        void ReadKeyed(string table, string key, IEnumerable<long> ids)
        {
            try { tables[table] = scanner.Scan(table, key: key, ids: ids, cancellationToken: cancellationToken); }
            catch (SourceTableMissing) when (scanner.Mapping.Tables[table].Optional)
            {
                tables[table] = [];
                missing.Add(table);
            }
        }
    }

    internal static IEnumerable<long> Keys(IEnumerable<IReadOnlyDictionary<string, object?>> rows, string key) =>
        rows.Select(r => SourceValues.Id(r, key)).OfType<long>().Distinct();
}

/// <summary>Source coercions are bounded by Domain-supported identifiers/dates; unsupported non-finite numbers fail explicitly (FZ-04).</summary>
public static class SourceValues
{
    /// <summary>A nullable source cell, with no default inferred from schema presence.</summary>
    public static object? Get(IReadOnlyDictionary<string, object?> row, string key) => row.TryGetValue(key, out var value) ? value : null;
    /// <summary>Invariant source text; no logging occurs at this boundary.</summary>
    public static string Text(IReadOnlyDictionary<string, object?> row, string key) =>
        Convert.ToString(Get(row, key), CultureInfo.InvariantCulture) ?? "";
    /// <summary>Int64 identifiers are required by the certified engine; malformed IDs are schema errors, not dropped tenants.</summary>
    public static long? Id(IReadOnlyDictionary<string, object?> row, string key) => ParseIdentifier(Get(row, key), key);
    /// <summary>Accepts Python integer carriers as well as SQL integers, without changing certified row dictionaries.</summary>
    public static long? ParseIdentifier(object? value, string key)
    {
        if (value is null) { return null; }
        return long.TryParse(Convert.ToString(value, CultureInfo.InvariantCulture), NumberStyles.Integer,
            CultureInfo.InvariantCulture, out var result) ? result : throw new SourceSchemaMismatch("identifier", [key]);
    }
    /// <summary>Dates accept SQL dates/timestamps and the fixture's ISO text; a malformed span becomes a counted excluded row.</summary>
    public static DateOnly? Date(IReadOnlyDictionary<string, object?> row, string key)
    {
        var value = Get(row, key);
        if (value is DateOnly date) { return date; }
        if (value is DateTime timestamp) { return DateOnly.FromDateTime(timestamp); }
        if (value is DateTimeOffset offset) { return DateOnly.FromDateTime(offset.DateTime); }
        var text = Text(row, key);
        return text.Length >= 10 && DateOnly.TryParseExact(text[..10], "yyyy-MM-dd", CultureInfo.InvariantCulture,
            DateTimeStyles.None, out var parsed) ? parsed : null;
    }
    /// <summary>Junk and null decimal text coerce to null; non-finite values are unsupported rather than contaminating figures.</summary>
    public static double? Number(IReadOnlyDictionary<string, object?> row, string key)
    {
        var raw = Get(row, key);
        if (raw is null) { return null; }
        var text = Text(row, key).Trim().Replace(",", "", StringComparison.Ordinal).TrimStart('$');
        if (!double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out var result)) { return null; }
        if (!double.IsFinite(result))
        {
            throw new UnsupportedNonfinitePayroll();
        }
        return result;
    }
    /// <summary>Normalizes SQL/fixture timestamps without treating missing values as an epoch.</summary>
    public static string? Timestamp(object? value)
    {
        if (value is null) { return null; }
        var text = Convert.ToString(value, CultureInfo.InvariantCulture);
        if (value is DateTime dt) { return dt.ToString("yyyy-MM-ddTHH:mm:ss.fffffff", CultureInfo.InvariantCulture); }
        if (DateTime.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.None, out var parsed))
        {
            return parsed.ToString("yyyy-MM-ddTHH:mm:ss.fffffff", CultureInfo.InvariantCulture);
        }
        throw new SourceSchemaMismatch("Payroll", ["modify_date"]);
    }
}

/// <summary>Every source assumption/drop is counted, independently of the engine's statutory filtering.</summary>
public sealed record ProjectionControls(long PayrollRowsIn, long RowsOut, long DroppedNoSpan,
    long NullPayDates, long ImputedPayDates, long ExcludedPayDates, long NullHoursCoerced,
    long NullWagesCoerced, long WorksiteFallbacks, long UnmappedCodeRows, long DefaultedCodeRows,
    int InferredCodes, IReadOnlyDictionary<string, int> CodeProviders, long RowsWithoutCounty,
    int DistinctEmployees, int DistinctWorksites, int DistinctFeins);

/// <summary>Engine rows and their input controls travel together.</summary>
public sealed record PayrollProjection(IReadOnlyList<PayRow> Rows, ProjectionControls Controls,
    IReadOnlyList<string> MissingTables, string Provenance);
