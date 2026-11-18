using System.Globalization;
using System.Numerics;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using TaxCredit.Domain.DataMap;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence;

/// <summary>A column's deployed type, precision and nullability; SQLite does not erase this contract.</summary>
public sealed record StorageColumn(string Name, string SqlType, int? Precision, int? Scale, bool Nullable)
{
    /// <summary>Converts a projected value without silently rounding or losing an integer.</summary>
    public object? ConvertValue(object? value, bool retainSeedScale = false)
    {
        value = SqlValues.Unwrap(value);
        if (value is null)
        {
            return Nullable ? null : throw new InvalidOperationException(Name + " is required.");
        }

        if (Scale is { } scale && SqlType == "DECIMAL")
        {
            var number = value is PyDecimal d ? d : PyDecimal.Parse(System.Convert.ToString(value, CultureInfo.InvariantCulture)!);
            var fixedValue = number.Quantize(scale, PyRoundingMode.HalfEven);
            if (PyDecimalOps.Compare(number, fixedValue) != 0 || fixedValue.Coefficient.ToString(CultureInfo.InvariantCulture).Length > Precision)
            {
                throw new InvalidOperationException(Name + " exceeds its declared decimal precision or scale.");
            }

            return retainSeedScale ? number.ToString() : fixedValue;
        }

        if (SqlType is "VARCHAR" or "CHAR")
        {
            var text = System.Convert.ToString(value, CultureInfo.InvariantCulture)!;
            if (text.Length > Precision)
            {
                throw new InvalidOperationException(Name + " exceeds its declared text length.");
            }

            return text;
        }

        if (SqlType is "BIGINT" or "INT" or "BIT")
        {
            var integer = value is BigInteger big ? checked((long)big) : System.Convert.ToInt64(value, CultureInfo.InvariantCulture);
            if ((SqlType == "INT" && (integer < int.MinValue || integer > int.MaxValue)) || (SqlType == "BIT" && integer is not (0 or 1)))
            {
                throw new InvalidOperationException(Name + " exceeds its declared integer range.");
            }

            return integer;
        }

        if (SqlType == "FLOAT")
        {
            var number = System.Convert.ToDouble(value, CultureInfo.InvariantCulture);
            return double.IsFinite(number) ? number : throw new InvalidOperationException(Name + " must be finite.");
        }

        return value;
    }
}

/// <summary>Non-destructive local schema administration derived from the checked-in DDL and forward migrations.</summary>
public static partial class PersistenceSchema
{
    private static readonly string[] EmployeeTables = ["employee_eligibility", "onezero_matrix", "employee_period_fact", "unit_month_summary", "run_method_summary"];
    private static IEnumerable<string> Files(string repositoryRoot)
    {
        var folder = Path.Combine(repositoryRoot, "docs", "data", "schema");
        return new[] { Path.Combine(folder, "tcc-schema.sqlserver.sql") }
            .Concat(Directory.EnumerateFiles(Path.Combine(folder, "migrations"), "*.sql").Order(StringComparer.Ordinal));
    }

    /// <summary>Reads the bootstrap and all five forward migrations; operator execution remains Python-owned.</summary>
    public static IReadOnlyDictionary<string, IReadOnlyList<StorageColumn>> Read(string repositoryRoot)
    {
        var result = new Dictionary<string, IReadOnlyList<StorageColumn>>(StringComparer.Ordinal);
        foreach (var file in Files(repositoryRoot))
        {
            var sql = Comments().Replace(File.ReadAllText(file), string.Empty);
            foreach (Match table in Tables().Matches(sql))
            {
                if (Logical(table.Groups[1].Value) is { } key)
                {
                    result.Add(key, Columns().Matches(table.Groups[2].Value).Select(match => Column(match)).ToArray());
                }
            }

            foreach (Match alter in AddColumns().Matches(sql))
            {
                if (Logical(alter.Groups[1].Value) is { } name)
                {
                    result[name] = [.. result[name], Column(alter, 2)];
                }
            }
        }

        return result;
    }

    /// <summary>Creates missing SQLite tables, including migration additions, without dropping existing state.</summary>
    public static void Initialize(PersistenceDatabase database, string repositoryRoot)
    {
        ArgumentNullException.ThrowIfNull(database);
        if (database.Dialect is not SqliteDialect)
        {
            throw new NotSupportedException("Deployed schema migrations are applied by the existing Python operator.");
        }

        var schema = Read(repositoryRoot);
        database.Transact(session =>
        {
            foreach (var (table, columns) in schema)
            {
                if (columns.Count == 0)
                {
                    throw new InvalidOperationException("DDL table has no recognized columns: " + table);
                }

                session.ExecuteExempt(SqlExemption.Schema, "CREATE TABLE IF NOT EXISTS " + session.Dialect.Name(table)
                    + " (" + string.Join(",", columns.Select(SqliteColumn)) + ") STRICT");
                EnsureColumns(session, table, columns);
            }

            foreach (var table in EmployeeTables)
            {
                session.ExecuteExempt(SqlExemption.Schema, "CREATE INDEX IF NOT EXISTS ix_" + table
                    + "_run ON " + session.Dialect.Name("gold." + table) + " (client_id,run_id,tax_year)");
            }

            session.ExecuteExempt(SqlExemption.Schema, "CREATE UNIQUE INDEX IF NOT EXISTS ix_run_identity ON {ops.run_manifest}(run_id)");
            session.ExecuteExempt(SqlExemption.Schema, "CREATE UNIQUE INDEX IF NOT EXISTS ix_claim_identity ON {ops.program_claim}(claim_id)");
            RecordMigrations(session, repositoryRoot);
            return 0;
        });
    }

    private static void EnsureColumns(SqlSession session, string table, IReadOnlyList<StorageColumn> expected)
    {
        var actual = session.QueryExempt(SqlExemption.Schema, "PRAGMA table_info(" + session.Dialect.Name(table) + ")")
            .ToDictionary(row => (string)row["name"]!, StringComparer.Ordinal);
        foreach (var column in expected)
        {
            if (!actual.TryGetValue(column.Name, out var row))
            {
                if (!column.Nullable)
                {
                    throw new InvalidOperationException("An existing table lacks a required column: " + table + "." + column.Name);
                }

                session.ExecuteExempt(SqlExemption.Schema, "ALTER TABLE " + session.Dialect.Name(table) + " ADD COLUMN " + SqliteColumn(column));
                continue;
            }

            var nullable = (long)row["notnull"]! == 0;
            if ((string)row["type"]! != SqliteType(column) || nullable != column.Nullable)
            {
                throw new InvalidOperationException("An existing column has incompatible type/nullability: " + table + "." + column.Name);
            }
        }
    }

    private static void RecordMigrations(SqlSession session, string root)
    {
        foreach (var file in Files(root))
        {
            var name = Path.GetFileNameWithoutExtension(file);
            var version = name == "tcc-schema.sqlserver" ? "0000" : name[..4];
            var hash = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(file)));
            var existing = session.QueryExempt(SqlExemption.Schema, "SELECT sha256 FROM {ops.schema_migration} WHERE version=?", version);
            if (existing.Count > 0)
            {
                if ((string)existing[0]["sha256"]! != hash)
                {
                    throw new InvalidOperationException("Applied schema content changed: " + version);
                }

                continue;
            }

            session.ExecuteExempt(SqlExemption.Schema,
                "INSERT INTO {ops.schema_migration} (version,name,sha256,applied_at,applied_by) VALUES (?,?,?,?,?)",
                version, name, hash, DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture), "persistence-local");
        }
    }

    private static StorageColumn Column(Match match, int start = 1)
    {
        var type = match.Groups[start + 1].Value.ToUpperInvariant();
        int? precision = match.Groups[start + 2].Success ? int.Parse(match.Groups[start + 2].Value, CultureInfo.InvariantCulture) : null;
        int? scale = match.Groups[start + 3].Success ? int.Parse(match.Groups[start + 3].Value, CultureInfo.InvariantCulture) : null;
        return new StorageColumn(match.Groups[start].Value, type, precision, scale,
            !match.Groups[start + 4].Value.Equals("NOT NULL", StringComparison.OrdinalIgnoreCase));
    }

    private static string SqliteColumn(StorageColumn column)
    {
        var name = "\"" + column.Name + "\"";
        var type = SqliteType(column);
        var check = column.SqlType switch
        {
            "BIT" => $" CHECK ({name} IN (0,1))",
            "INT" => $" CHECK ({name} BETWEEN -2147483648 AND 2147483647)",
            "VARCHAR" or "CHAR" => string.Create(CultureInfo.InvariantCulture, $" CHECK (length({name}) <= {column.Precision})"),
            "DECIMAL" => string.Create(CultureInfo.InvariantCulture, $" COLLATE TCC_DECIMAL CHECK (tcc_decimal_valid({name},{column.Precision},{column.Scale}))"),
            _ => string.Empty,
        };
        return name + " " + type + (column.Nullable ? string.Empty : " NOT NULL") + check;
    }

    private static string SqliteType(StorageColumn column) => column.SqlType switch
    {
        "BIGINT" or "INT" or "BIT" => "INTEGER",
        "FLOAT" => "REAL",
        _ => "TEXT",
    };

    [GeneratedRegex(@"/\*[\s\S]*?\*/|--[^\r\n]*")]
    private static partial Regex Comments();

    [GeneratedRegex(@"CREATE\s+TABLE\s+(\w+\.\w+)\s*\(([\s\S]*?)\)\s*;", RegexOptions.IgnoreCase)]
    private static partial Regex Tables();

    [GeneratedRegex(@"(\w+)\s+(BIGINT|INT|BIT|FLOAT|DECIMAL|VARCHAR|CHAR|DATETIME2|DATE)(?:\((\d+)(?:,(\d+))?\))?\s+(NOT\s+NULL|NULL)", RegexOptions.IgnoreCase)]
    private static partial Regex Columns();

    [GeneratedRegex(@"ALTER\s+TABLE\s+(\w+\.\w+)\s+ADD\s+(\w+)\s+(BIGINT|INT|BIT|FLOAT|DECIMAL|VARCHAR|CHAR|DATETIME2|DATE)(?:\((\d+)(?:,(\d+))?\))?\s+(NOT\s+NULL|NULL)", RegexOptions.IgnoreCase)]
    private static partial Regex AddColumns();

    /// <summary>The checked-in DDL spells the shipped actual names; the schema is keyed by logical key.</summary>
    private static string? Logical(string shippedQualified)
    {
        var shipped = DataMap.Default;
        return shipped.Tables.Values.FirstOrDefault(t => shipped.Schema(t.Schema) + "." + t.Physical == shippedQualified)?.Key;
    }
}
