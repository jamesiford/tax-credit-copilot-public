using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Simulation;

/// <summary>The Python conversions the lever code applies to a loosely typed row cell: <c>float(r[col])</c>, <c>int(x)</c> and a slice end.</summary>
internal static class RowOps
{
    /// <summary>
    /// Python <c>float(r[column])</c>: <c>KeyError</c> for an absent key, and then the ordinary <c>float()</c> rules. Unlike the engine's
    /// <c>_coerce_float</c>, <c>None</c> and <c>""</c> are errors here (<c>TypeError</c> and <c>ValueError</c>).
    /// </summary>
    internal static double Float(RowCell cell, string column) => cell.Kind switch
    {
        CellKind.Absent => throw new PyKeyError(column),
        CellKind.Null => ProximityCoerce.ToFloat((object?)null),
        CellKind.Text => ProximityCoerce.ToFloat(cell.Text),
        CellKind.WholeNumber => cell.IntValue,
        _ => cell.FloatValue,
    };

    /// <summary>Python <c>int(x)</c> of a float: truncates toward zero; <c>NaN</c> is a <c>ValueError</c> and an infinity an <c>OverflowError</c>.</summary>
    internal static long Int(double x)
    {
        if (double.IsNaN(x))
        {
            throw new PyValueError("cannot convert float NaN to integer");
        }

        if (double.IsInfinity(x))
        {
            throw new PyOverflowError("cannot convert float infinity to integer");
        }

        var whole = PyArith.Truncate(x);
        return whole > long.MaxValue ? long.MaxValue : (whole < long.MinValue ? long.MinValue : (long)whole);
    }

    /// <summary>The end index of Python <c>seq[:k]</c> for a list of <paramref name="length"/> items (a negative <c>k</c> counts from the end).</summary>
    internal static int SliceEnd(long k, int length)
    {
        var end = k < 0 ? length + k : k;
        return (int)Math.Clamp(end, 0, length);
    }
}
