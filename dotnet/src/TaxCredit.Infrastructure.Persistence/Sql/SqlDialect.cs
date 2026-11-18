using System.Globalization;
using System.Text.RegularExpressions;
using TaxCredit.Domain.DataMap;

namespace TaxCredit.Infrastructure.Persistence.Sql;

/// <summary>Provider details remain outside application contracts.</summary>
public interface ISqlDialect
{
    /// <summary>The logical-to-actual name resolver this dialect applies; the embedded shipped map unless a data map file is supplied.</summary>
    PhysicalNames Names => PhysicalNames.Default;

    /// <summary>Quotes a trusted table name: a logical key (<c>ops.run_manifest</c>) resolves through the data map.</summary>
    string Name(string qualifiedName);

    /// <summary>Replaces logical table tokens (<c>{ops.run_manifest}</c>) in trusted adapter SQL with actual names.</summary>
    string Resolve(string sql);

    /// <summary>Pages an ordered SELECT, including SELECT DISTINCT.</summary>
    string Page(string sql, int limit, long offset);

    /// <summary>Escapes a literal LIKE needle; statements use ESCAPE '\'.</summary>
    string Like(string value);

    /// <summary>Rewrites trusted adapter SQL for the selected provider.</summary>
    string Translate(string sql);

    /// <summary>How large inserts are sent; <see cref="BulkLoadPolicy.Off" /> keeps bounded multi-row statements.</summary>
    BulkLoadPolicy Bulk { get; }
}

/// <summary>SQL Server and Warehouse use the same parameterized transport and syntax.</summary>
public sealed class SqlServerDialect : ISqlDialect
{
    /// <summary>Uses the default bulk-load policy.</summary>
    public SqlServerDialect() : this(null) { }

    /// <summary>Selects how large inserts are sent; a null policy means <see cref="BulkLoadPolicy.Default" />.</summary>
    public SqlServerDialect(BulkLoadPolicy? bulk) : this(bulk, new SqlBulkCopyWriter()) { }

    /// <summary>Applies the supplied names (a data map file) instead of the shipped map.</summary>
    public SqlServerDialect(BulkLoadPolicy? bulk, PhysicalNames names) : this(bulk, new SqlBulkCopyWriter(), names) { }

    internal SqlServerDialect(BulkLoadPolicy? bulk, IBulkWriter writer, PhysicalNames? names = null)
    {
        Bulk = bulk ?? BulkLoadPolicy.Default;
        Writer = writer;
        Names = names ?? PhysicalNames.Default;
    }

    /// <inheritdoc />
    public BulkLoadPolicy Bulk { get; }

    /// <inheritdoc />
    public PhysicalNames Names { get; }

    internal IBulkWriter Writer { get; }

    /// <inheritdoc />
    public string Name(string qualifiedName)
    {
        qualifiedName = SqlNames.Key(qualifiedName);
        return Names.Map.Tables.ContainsKey(qualifiedName) ? Names.Bracketed(qualifiedName) : SqlNames.Qualified(qualifiedName, false);
    }

    /// <inheritdoc />
    public string Resolve(string sql) => Names.Resolve(sql);

    /// <inheritdoc />
    public string Page(string sql, int limit, long offset)
    {
        SqlNames.CheckPage(limit, offset);
        return string.Create(CultureInfo.InvariantCulture, $"{sql} OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY");
    }

    /// <inheritdoc />
    public string Like(string value) => SqlNames.Like(value).Replace("[", "\\[", StringComparison.Ordinal);

    /// <inheritdoc />
    public string Translate(string sql) => Resolve(sql);
}

/// <summary>SQLite executes the same repository statements without credentials.</summary>
public sealed class SqliteDialect : ISqlDialect
{
    /// <summary>Uses the shipped map's names.</summary>
    public SqliteDialect() : this(PhysicalNames.Default) { }

    /// <summary>Applies the supplied names (a data map file) instead of the shipped map.</summary>
    public SqliteDialect(PhysicalNames names) => Names = names;

    /// <inheritdoc />
    public BulkLoadPolicy Bulk => BulkLoadPolicy.Off;

    /// <inheritdoc />
    public PhysicalNames Names { get; }

    /// <inheritdoc />
    public string Name(string qualifiedName)
    {
        qualifiedName = SqlNames.Key(qualifiedName);
        return Names.Map.Tables.ContainsKey(qualifiedName) ? "\"" + Names.Flat(qualifiedName) + "\"" : SqlNames.Qualified(qualifiedName, true);
    }

    /// <inheritdoc />
    public string Resolve(string sql) => Names.ResolveFlat(sql);

    /// <inheritdoc />
    public string Page(string sql, int limit, long offset)
    {
        SqlNames.CheckPage(limit, offset);
        return string.Create(CultureInfo.InvariantCulture, $"{sql} LIMIT {limit} OFFSET {offset}");
    }

    /// <inheritdoc />
    public string Like(string value) => SqlNames.Like(value);

    /// <inheritdoc />
    public string Translate(string sql)
    {
        sql = Resolve(sql);
        var mask = SqlLex.Mask(sql);
        foreach (Match match in Names.QualifiedPattern.Matches(mask).Cast<Match>().Reverse())
        {
            sql = sql.Remove(match.Index, match.Length).Insert(match.Index, SqlNames.Qualified(match.Value, true));
        }

        return sql;
    }
}

internal static class SqlNames
{
    /// <summary>A table argument may be a logical key (<c>ops.x</c>) or a <c>{ops.x}</c> token; both name the same table.</summary>
    internal static string Key(string name) => name.Length > 2 && name[0] == '{' && name[^1] == '}' ? name[1..^1] : name;

    internal static string Qualified(string name, bool sqlite)
    {
        var parts = name.Split('.');
        if (parts.Length is < 1 or > 2 || parts.Any(p => !TenantBinding.Identifier().IsMatch(p)))
        {
            throw new TenantScopeViolation("Invalid SQL identifier.");
        }

        return sqlite ? "\"" + string.Join("_", parts) + "\"" : string.Join(".", parts.Select(p => "[" + p + "]"));
    }

    internal static void CheckPage(int limit, long offset)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(limit, 1);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(limit, 10000);
        ArgumentOutOfRangeException.ThrowIfNegative(offset);
    }

    internal static string Like(string value) => value.Replace("\\", "\\\\", StringComparison.Ordinal)
        .Replace("%", "\\%", StringComparison.Ordinal).Replace("_", "\\_", StringComparison.Ordinal);
}
