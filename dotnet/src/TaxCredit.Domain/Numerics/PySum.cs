using System.Numerics;

namespace TaxCredit.Domain.Numerics;

/// <summary>A Python number that is either an <c>int</c> or a <c>float</c>; <c>bool</c> counts as an int.</summary>
/// <param name="IsInt">True for an int.</param>
/// <param name="IntValue">The value when <paramref name="IsInt"/>.</param>
/// <param name="FloatValue">The value when not <paramref name="IsInt"/>.</param>
public readonly record struct PyNumber(bool IsInt, long IntValue, double FloatValue)
{
    /// <summary>Creates an int.</summary>
    public static PyNumber OfInt(long value) => new(true, value, 0);

    /// <summary>Creates a float.</summary>
    public static PyNumber OfFloat(double value) => new(false, 0, value);
}

/// <summary>
/// Python's built-in <c>sum()</c>, including CPython 3.12+'s compensated (Neumaier) float summation.
/// </summary>
/// <remarks>
/// Why not <c>+=</c> or LINQ <c>Sum()</c>: since Python 3.12 <c>sum()</c> of floats carries a running error
/// term and adds it once at the end, so <c>sum([0.1] * 10)</c> is exactly <c>1.0</c> while a naive loop gives
/// <c>0.9999999999999999</c>. Reproducing the engine's totals therefore requires the same algorithm, in the same
/// element order. Ints are added exactly until the first float appears, then take the same compensated path as floats.
/// Source: CPython <c>Python/bltinmodule.c</c> (<c>builtin_sum_impl</c>). Ints beyond the <see cref="long"/>
/// range are not supported (the engine sums small counts and weights).
/// </remarks>
public static class PySum
{
    /// <summary>Python <c>sum(items)</c> over mixed ints and floats.</summary>
    public static PyNumber Sum(IReadOnlyList<PyNumber> items)
    {
        ArgumentNullException.ThrowIfNull(items);
        BigInteger intAccumulator = BigInteger.Zero;
        var i = 0;
        for (; i < items.Count && items[i].IsInt; i++)
        {
            intAccumulator += items[i].IntValue;
        }

        if (i == items.Count)
        {
            return PyNumber.OfInt((long)intAccumulator);
        }

        // The first float: 0 + x performed as int + float, i.e. (double)int + x.
        var f = (double)intAccumulator + items[i].FloatValue;
        var c = 0.0;
        for (i++; i < items.Count; i++)
        {
            // Ints take the same compensated path as floats (verified against CPython 3.14 vectors).
            var x = items[i].IsInt ? items[i].IntValue : items[i].FloatValue;
            var t = f + x;
            c += Math.Abs(f) >= Math.Abs(x) ? (f - t) + x : (x - t) + f;
            f = t;
        }

        if (c != 0 && double.IsFinite(c))
        {
            f += c;
        }

        return PyNumber.OfFloat(f);
    }

    /// <summary>Python <c>sum(xs)</c> over floats (empty gives the int 0, returned here as 0.0).</summary>
    public static double Sum(IReadOnlyList<double> values)
    {
        ArgumentNullException.ThrowIfNull(values);
        var items = new PyNumber[values.Count];
        for (var i = 0; i < items.Length; i++)
        {
            items[i] = PyNumber.OfFloat(values[i]);
        }

        var result = Sum(items);
        return result.IsInt ? result.IntValue : result.FloatValue;
    }
}
