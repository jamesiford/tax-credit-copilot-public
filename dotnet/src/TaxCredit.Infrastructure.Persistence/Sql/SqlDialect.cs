using System.Globalization;
using System.Text.RegularExpressions;

namespace TaxCredit.Infrastructure.Persistence.Sql;

/// <summary>Provider details remain outside application contracts.</summary>
public interface ISqlDialect
{
    /// <summary>Quotes a trusted, qualified table name.</summary>
    string Name(string qualifiedName);

    /// <summary>Pages an ordered SELECT, including SELECT DISTINCT.</summary>
    string Page(string sql, int limit, long offset);

    /// <summary>Escapes a literal LIKE needle; statements use ESCAPE '\'.</summary>
    string Like(string value);

    /// <summary>Rewrites trusted adapter SQL for the selected provider.</summary>
    string Translate(string sql);
}

/// <summary>SQL Server and Warehouse use the same parameterized transport and syntax.</summary>
public sealed class SqlServerDialect : ISqlDialect
{
    /// <inheritdoc />
    public string Name(string qualifiedName) => SqlNames.Qualified(qualifiedName, false);

    /// <inheritdoc />
    public string Page(string sql, int limit, long offset)
    {
        SqlNames.CheckPage(limit, offset);
        return string.Create(CultureInfo.InvariantCulture, $"{sql} OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY");
    }

    /// <inheritdoc />
    public string Like(string value) => SqlNames.Like(value).Replace("[", "\\[", StringComparison.Ordinal);

    /// <inheritdoc />
    public string Translate(string sql) => sql;
}

/// <summary>SQLite executes the same repository statements without credentials.</summary>
public sealed partial class SqliteDialect : ISqlDialect
{
    /// <inheritdoc />
    public string Name(string qualifiedName) => SqlNames.Qualified(qualifiedName, true);

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
        var mask = SqlLex.Mask(sql);
        foreach (Match match in Tables().Matches(mask).Cast<Match>().Reverse())
        {
            sql = sql.Remove(match.Index, match.Length).Insert(match.Index, Name(match.Value));
        }

        return sql;
    }

    [GeneratedRegex(@"\b(?:tcc_gold|tcc_ops|tcc_source)\.[A-Za-z_][A-Za-z0-9_]*\b")]
    private static partial Regex Tables();
}

internal static class SqlNames
{
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
