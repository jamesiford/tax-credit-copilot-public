using System.Numerics;
using System.Text.RegularExpressions;
using TaxCredit.Domain.Gold;

namespace TaxCredit.Parity.Tests;

/// <summary>One column of a <c>tcc_gold</c> table as <c>docs/data/schema/tcc-schema.fabric.sql</c> declares it.</summary>
/// <param name="Name">The column.</param>
/// <param name="Type">The base type (<c>BIGINT</c>, <c>DECIMAL</c>, <c>VARCHAR</c> ...), upper case.</param>
/// <param name="Precision">DECIMAL precision, or null.</param>
/// <param name="Scale">DECIMAL scale, or null.</param>
/// <param name="Length">VARCHAR/CHAR length, or null.</param>
/// <param name="Nullable">Whether NULL is allowed (the DDL default for an unmarked column is nullable).</param>
internal sealed record DdlColumn(string Name, string Type, int? Precision, int? Scale, int? Length, bool Nullable);

/// <summary>Reads the Warehouse DDL (comments stripped) and checks Python-built cells against it.</summary>
internal static partial class GoldDdl
{
    public static string File { get; } = Path.Combine(Directory.GetParent(GoldenFiles.ParityDirectory)!.FullName, "docs", "data", "schema", "tcc-schema.fabric.sql");

    /// <summary>The seven <c>tcc_gold</c> tables the projection feeds, in file order.</summary>
    public static Dictionary<string, List<DdlColumn>> Parse()
    {
        var text = BlockComment().Replace(System.IO.File.ReadAllText(File), string.Empty);
        text = LineComment().Replace(text, string.Empty);
        var tables = new Dictionary<string, List<DdlColumn>>(StringComparer.Ordinal);
        foreach (Match table in CreateTable().Matches(text))
        {
            var columns = new List<DdlColumn>();
            foreach (var raw in table.Groups[2].Value.Split('\n'))
            {
                var line = raw.Trim();
                if (line.Length == 0)
                {
                    continue;
                }

                var m = ColumnLine().Match(line);
                Assert.True(m.Success, $"{table.Groups[1].Value}: unparsed DDL line '{line}'");
                var type = m.Groups[2].Value.ToUpperInvariant();
                var (first, second) = (Number(m.Groups[3]), Number(m.Groups[4]));
                columns.Add(new DdlColumn(
                    m.Groups[1].Value, type, type == "DECIMAL" ? first : null, type == "DECIMAL" ? second : null, type is "VARCHAR" or "CHAR" ? first : null,
                    !m.Groups[5].Value.StartsWith("NOT", StringComparison.OrdinalIgnoreCase)));
            }

            tables[table.Groups[1].Value] = columns;
        }

        return tables;
    }

    /// <summary>Why a cell cannot be stored in its column (empty when it can).</summary>
    public static IEnumerable<string> Violations(DdlColumn column, GoldCell cell)
    {
        if (cell.Kind == GoldKind.Null)
        {
            return column.Nullable ? [] : ["NULL in a NOT NULL column"];
        }

        return column.Type switch
        {
            "BIGINT" or "INT" or "SMALLINT" => IntCheck(column, cell),
            "BIT" => cell.Kind == GoldKind.WholeNumber && (cell.AsInt == 0 || cell.AsInt == 1) ? [] : ["not 0 or 1 for a BIT"],
            "DECIMAL" => DecimalCheck(column, cell),
            "DATE" => cell.Kind == GoldKind.Date ? [] : ["not a date"],
            "DATETIME2" => cell.Kind == GoldKind.DateTime ? [] : ["not a datetime"],
            "VARCHAR" or "CHAR" => cell.Kind == GoldKind.Text && cell.AsText.Length <= column.Length ? [] : [$"longer than {column.Type}({column.Length})"],
            _ => [$"unknown DDL type {column.Type}"],
        };
    }

    private static IEnumerable<string> IntCheck(DdlColumn column, GoldCell cell)
    {
        if (cell.Kind != GoldKind.WholeNumber)
        {
            return ["not an int"];
        }

        var limit = column.Type == "INT" ? new BigInteger(int.MaxValue) : column.Type == "SMALLINT" ? short.MaxValue : long.MaxValue;
        return BigInteger.Abs(cell.AsInt) <= limit ? [] : [$"out of range for {column.Type}"];
    }

    private static List<string> DecimalCheck(DdlColumn column, GoldCell cell)
    {
        if (cell.Kind != GoldKind.ExactDecimal)
        {
            return ["not a finite decimal"];
        }

        var d = cell.AsDecimal;
        var problems = new List<string>();
        if (d.Exponent != -column.Scale)
        {
            problems.Add($"scale {-d.Exponent} for DECIMAL({column.Precision},{column.Scale})");
        }

        if (d.Coefficient.ToString().Length > column.Precision)
        {
            problems.Add($"overflows DECIMAL({column.Precision},{column.Scale})");
        }

        return problems;
    }

    private static int? Number(Group g) => g.Success ? int.Parse(g.Value, System.Globalization.CultureInfo.InvariantCulture) : null;

    [GeneratedRegex(@"/\*.*?\*/", RegexOptions.Singleline)]
    private static partial Regex BlockComment();

    [GeneratedRegex(@"--[^\n]*")]
    private static partial Regex LineComment();

    [GeneratedRegex(@"CREATE\s+TABLE\s+tcc_gold\.(\w+)\s*\((.*?)\n\)\s*;", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
    private static partial Regex CreateTable();

    [GeneratedRegex(@"^(\w+)\s+(BIGINT|INT|SMALLINT|BIT|DATE|DATETIME2|DECIMAL|VARCHAR|CHAR)(?:\((\d+)(?:,\s*(\d+))?\))?\s*(?:(NOT\s+NULL|NULL))?\s*,?$", RegexOptions.IgnoreCase)]
    private static partial Regex ColumnLine();
}
