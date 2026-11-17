using System.Globalization;
using System.Numerics;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>Decoding of the gold golden's tagged arguments and the typed-cell trees its outputs are compared as.</summary>
internal static class GoldReplay
{
    /// <summary>Rebuilds a recorded argument: <c>$dec</c>, <c>$date</c> and <c>$dt</c> tags become <see cref="PyDecimal"/> (or <see cref="PyDecimalSpecial"/>), <see cref="DateOnly"/> and <see cref="PyDateTime"/>.</summary>
    public static object? Decode(object? v) => v switch
    {
        PyDict { Count: 1 } d when d.TryGetValue("$dec", out var t) => Decimal((string)t!),
        PyDict { Count: 1 } d when d.TryGetValue("$date", out var t) => PyDate.FromIsoFormat((string)t!),
        PyDict { Count: 1 } d when d.TryGetValue("$dt", out var t) => PyDateTime.FromIsoFormat((string)t!),
        PyDict d => d.Aggregate(new PyDict(), (acc, kv) => acc.Add(kv.Key, Decode(kv.Value))),
        List<object?> l => l.Select(Decode).ToList(),
        _ => v,
    };

    /// <summary>A recorded Decimal: finite ones parse exactly, NaN and infinities stay as text.</summary>
    public static object Decimal(string text) =>
        text.Contains("nan", StringComparison.OrdinalIgnoreCase) || text.Contains("inf", StringComparison.OrdinalIgnoreCase)
            ? new PyDecimalSpecial(text)
            : PyDecimal.Parse(text);

    /// <summary>A list of recorded mappings.</summary>
    public static List<PyDict> Rows(object? tree) => ((List<object?>)tree!).Cast<PyDict>().ToList();

    /// <summary>An optional int argument (<c>None</c> is <c>null</c>).</summary>
    public static BigInteger? MaybeInt(object? v) => v is null ? null : Int(v);

    /// <summary>An int argument, whatever width the JSON reader chose.</summary>
    public static BigInteger Int(object? v) => v is BigInteger b ? b : (long)v!;

    /// <summary>The typed-cell tree of one value, exactly as the exporter's <c>cell()</c> writes it.</summary>
    public static List<object?> Cell(GoldCell c) => c.Kind switch
    {
        GoldKind.Null => ["null"],
        GoldKind.WholeNumber => ["int", c.AsInt >= long.MinValue && c.AsInt <= long.MaxValue ? (object)(long)c.AsInt : c.AsInt],
        GoldKind.ExactDecimal => ["dec", c.AsDecimal.ToString()],
        GoldKind.DecimalNaN => ["nan", c.AsText],
        GoldKind.Text => ["str", c.AsText],
        GoldKind.Date => ["date", c.AsDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)],
        GoldKind.DateTime => ["dt", c.AsDateTime.IsoFormat()],
        _ => throw new InvalidOperationException("unknown kind"),
    };

    /// <summary>The comparison tree of a table: its name, its columns as the C# rows carry them, and every cell.</summary>
    public static PyDict Table(string table, IReadOnlyList<GoldRow> rows) => new PyDict()
        .Add("table", table)
        .Add("columns", GoldColumns.All[table].Select(c => (object?)c).ToList())
        .Add("rows", rows.Select(r => (object?)r.Cells.Select(c => (object?)Cell(c)).ToList()).ToList());

    /// <summary>Every row's own column list must be the table's (a row built from the wrong list is a column-order defect).</summary>
    public static void AssertColumns(IReadOnlyList<GoldRow> rows)
    {
        foreach (var row in rows)
        {
            Assert.True(row.Columns.SequenceEqual(GoldColumns.All[row.Table]), row.Table + ": a row carries another table's columns");
        }
    }
}
