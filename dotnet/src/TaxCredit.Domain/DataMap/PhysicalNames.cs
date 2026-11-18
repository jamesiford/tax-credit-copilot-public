using System.Text.RegularExpressions;

namespace TaxCredit.Domain.DataMap;

/// <summary>
/// The one place logical Warehouse names become actual ones. Statements spell tables as <c>{ops.run_manifest}</c> tokens;
/// <see cref="Resolve" /> turns them into the actual, qualified, quoted-as-needed names just before a statement reaches
/// the provider.
/// </summary>
public sealed partial class PhysicalNames(DataMap map)
{
    /// <summary>Names from the embedded shipped map.</summary>
    public static PhysicalNames Default { get; } = new(DataMap.Default);

    /// <summary>
    /// The names this process runs with: <see cref="Default" /> until the host calls <see cref="Use" /> once at start-up.
    /// It exists for static helpers that label evidence with the actual schema; statements get their names from the dialect.
    /// </summary>
    public static PhysicalNames Active { get; private set; } = Default;

    /// <summary>Sets the process-wide names; called once by the host composition root before any statement runs.</summary>
    public static void Use(PhysicalNames names) => Active = names ?? throw new ArgumentNullException(nameof(names));

    /// <summary>The map these names come from.</summary>
    public DataMap Map { get; } = map;

    /// <summary>The actual qualified table name for a logical key such as <c>ops.run_manifest</c>.</summary>
    public string Table(string key) => Quote(Map.Schema(Entry(key).Schema)) + "." + Quote(Entry(key).Physical);

    /// <summary>The actual <c>(schema, table)</c> for a logical key; unquoted.</summary>
    public (string Schema, string Table) Parts(string key) => (Map.Schema(Entry(key).Schema), Entry(key).Physical);

    /// <summary>The actual flattened SQLite name for a logical key: <c>&lt;schema&gt;_&lt;table&gt;</c>.</summary>
    public string Flat(string key) => string.Join("_", Parts(key).Schema, Parts(key).Table);

    /// <summary>The actual qualified name with both parts bracket-quoted, as bulk and multi-row insert statements spell it.</summary>
    public string Bracketed(string key) => "[" + Parts(key).Schema + "].[" + Parts(key).Table + "]";

    /// <summary>The actual qualified Gold table name.</summary>
    public string Gold(string table) => Table("gold." + table);

    /// <summary>The actual qualified Ops table name.</summary>
    public string Ops(string table) => Table("ops." + table);

    /// <summary>Replaces every <c>{gold.x}</c> and <c>{ops.x}</c> token with the actual qualified name.</summary>
    public string Resolve(string sql) => sql.Contains('{', StringComparison.Ordinal)
        ? Token().Replace(sql, m => Table(m.Groups[1].Value + "." + m.Groups[2].Value))
        : sql;

    /// <summary>Replaces every table token with the SQLite flattened, double-quoted name.</summary>
    public string ResolveFlat(string sql) => sql.Contains('{', StringComparison.Ordinal)
        ? Token().Replace(sql, m => "\"" + Flat(m.Groups[1].Value + "." + m.Groups[2].Value) + "\"")
        : sql;

    /// <summary>Matches an actual <c>schema.table</c> reference for any mapped schema, for SQLite flattening of literal SQL.</summary>
    public Regex QualifiedPattern { get; } = new(
        @"\b(?:" + string.Join("|", new[] { map.GoldSchema, map.OpsSchema, map.SourceSchema }.Distinct().Select(Regex.Escape))
        + @")\.[A-Za-z_][A-Za-z0-9_]*\b", RegexOptions.CultureInvariant | RegexOptions.Compiled);

    private WarehouseTable Entry(string key) => Map.Tables.TryGetValue(key, out var table)
        ? table
        : throw new DataMapException($"warehouse.tables.{key} is not a known key.");

    private static string Quote(string name) => PlainName().IsMatch(name) ? name : "[" + name + "]";

    [GeneratedRegex(@"\{(gold|ops)\.([a-z][a-z0-9_]*)\}", RegexOptions.CultureInvariant)]
    private static partial Regex Token();

    [GeneratedRegex("^[A-Za-z_][A-Za-z0-9_]*$", RegexOptions.CultureInvariant)]
    private static partial Regex PlainName();
}
