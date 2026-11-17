using System.Numerics;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Pipeline;

/// <summary>
/// One payroll row as Python carries it (a loosely typed <c>dict</c>) together with the engine's reading of it (<see cref="PayrollRow"/>). The pipeline
/// filters and projects the dictionary (<c>row.get("Pay_Date")</c>, the Gold projections) and hands the engine the typed view, so both are built once.
/// </summary>
/// <param name="Dict">The row, key order as loaded.</param>
/// <param name="Row">The ten columns the engine reads, each with its Python type.</param>
public sealed record PayRow(PyDict Dict, PayrollRow Row)
{
    private static readonly string[] Columns =
        ["Employee_ID", "Worksite_ID", "Entity_FEIN", "Pay_Period_Start", "Pay_Period_End", "Pay_Date", "Hours_Worked", "Gross_Wages", "Pay_Code", "Work_State", "Job_Title"];

    /// <summary>Wraps a row dictionary.</summary>
    /// <param name="dict">The row.</param>
    /// <returns>The row with its engine view.</returns>
    public static PayRow Of(PyDict dict)
    {
        ArgumentNullException.ThrowIfNull(dict);
        var c = Columns.Select(name => Cell(dict, name)).ToArray();
        return new PayRow(dict, new PayrollRow(c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8], c[9], c[10]));
    }

    /// <summary>Wraps every row of a payroll.</summary>
    /// <param name="rows">The row dictionaries.</param>
    /// <returns>The wrapped rows, in order.</returns>
    public static IReadOnlyList<PayRow> Of(IEnumerable<PyDict> rows) => rows.Select(Of).ToList();

    /// <summary>Python <c>row.get(key)</c>.</summary>
    /// <param name="key">The column.</param>
    /// <returns>The value, <c>null</c> when absent or None.</returns>
    public object? Get(string key) => Dict.TryGetValue(key, out var v) ? v : null;

    /// <summary>Python <c>str(row.get("Pay_Date") or "")[:10]</c>: the date text the window filters compare as text.</summary>
    /// <returns>The first ten characters of the pay date, empty when there is none.</returns>
    public string PayDateText()
    {
        var v = Get("Pay_Date");
        return v switch
        {
            null => string.Empty,
            string s => PyStr.Prefix(s, 10),
            _ => throw new PyUnsupportedException("a non-text Pay_Date is not modelled"),
        };
    }

    private static RowCell Cell(PyDict d, string key) => !d.TryGetValue(key, out var v) ? RowCell.Absent : v switch
    {
        null => RowCell.Null,
        string s => RowCell.OfText(s),
        long l => RowCell.OfInt(l),
        double x => RowCell.OfFloat(x),
        BigInteger b when b >= long.MinValue && b <= long.MaxValue => RowCell.OfInt((long)b),
        _ => throw new PyUnsupportedException("unsupported payroll cell " + v.GetType().Name + " in " + key),
    };
}

/// <summary>
/// The typing <c>infrastructure/payroll/pay_period_source.load_pay_periods</c> applies to the CSV fixture: <c>Tax_Year</c> becomes an int and the two
/// money columns floats; every other cell stays the text <c>csv.DictReader</c> produced.
/// </summary>
public static class CsvPayroll
{
    /// <summary>Python's per-row typing of the CSV fixture.</summary>
    /// <param name="raw">The rows as <c>csv.DictReader</c> yields them.</param>
    /// <returns>The typed rows, in file order.</returns>
    /// <exception cref="PyKeyError">When a row lacks one of the three typed columns.</exception>
    /// <exception cref="PyValueError">When a typed cell is not a number.</exception>
    public static IReadOnlyList<PyDict> Typed(IEnumerable<PyDict> raw)
    {
        ArgumentNullException.ThrowIfNull(raw);
        var rows = new List<PyDict>();
        foreach (var row in raw)
        {
            var typed = new PyDict();
            foreach (var kv in row)
            {
                typed.Add(kv.Key, kv.Value);
            }

            var year = ToInt(row["Tax_Year"]);
            typed.Set("Tax_Year", year >= long.MinValue && year <= long.MaxValue ? (long)year : year);
            typed.Set("Hours_Worked", ToFloat(row["Hours_Worked"]));
            typed.Set("Gross_Wages", ToFloat(row["Gross_Wages"]));
            rows.Add(typed);
        }

        return rows;
    }

    private static BigInteger ToInt(object? v)
    {
        var text = v as string ?? throw new PyUnsupportedException("a missing CSV cell (None) is not modelled");
        return PyInt.TryParse(text, out var n) ? n : throw new PyValueError($"invalid literal for int() with base 10: {PyStr.Repr(text)}");
    }

    private static double ToFloat(object? v)
    {
        var text = v as string ?? throw new PyUnsupportedException("a missing CSV cell (None) is not modelled");
        return PyFloat.TryParse(text, out var d) ? d : throw new PyValueError($"could not convert string to float: {PyStr.Repr(text)}");
    }
}
