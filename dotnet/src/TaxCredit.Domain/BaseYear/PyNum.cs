using System.Numerics;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.BaseYear;

/// <summary>
/// Python's mixed <c>int</c>/<c>float</c> arithmetic for the few places the base-year engine lets an operand keep its type
/// (an override passed as <c>80</c> stays an <c>int</c>, so <c>round(80, 2)</c> is <c>80</c>, not <c>80.0</c>).
/// </summary>
/// <remarks>
/// Why a layer: <c>max(running_hwm, avg)</c> and <c>avg - base_avg</c> compare and subtract an int with a float EXACTLY (CPython compares
/// the true values), and the winner keeps its own type. Ints are limited to the <see cref="long"/> range (see findings BY-09).
/// </remarks>
public static class PyNum
{
    /// <summary>Python <c>float(n)</c>.</summary>
    /// <param name="n">The number.</param>
    /// <returns>Its double value (an int is converted with round-half-even, as CPython does).</returns>
    public static double ToDouble(PyNumber n) => n.IsInt ? n.IntValue : n.FloatValue;

    /// <summary>The tree value of <paramref name="n"/>: a <see cref="long"/> for an int, a <see cref="double"/> for a float.</summary>
    /// <param name="n">The number.</param>
    /// <returns>The boxed value.</returns>
    public static object Tree(PyNumber n) => n.IsInt ? (object)n.IntValue : n.FloatValue;

    /// <summary>The tree value of an optional number (<c>None</c> is <c>null</c>).</summary>
    /// <param name="n">The number, or <c>null</c>.</param>
    /// <returns>The boxed value or <c>null</c>.</returns>
    public static object? Tree(PyNumber? n) => n is { } v ? Tree(v) : null;

    /// <summary>Python <c>round(n, 2)</c>: an int is returned unchanged, a float is rounded half-even on its exact value.</summary>
    /// <param name="n">The number.</param>
    /// <returns>The rounded number, keeping its type.</returns>
    public static PyNumber Round2(PyNumber n) => n.IsInt ? n : PyNumber.OfFloat(PyRound.Round(n.FloatValue, 2));

    /// <summary>An int result of Python's <c>round(x)</c> as a tree value: <see cref="long"/> when it fits, else <see cref="BigInteger"/>.</summary>
    /// <param name="value">The integer.</param>
    /// <returns>The boxed value.</returns>
    public static object IntTree(BigInteger value) => value >= long.MinValue && value <= long.MaxValue ? (object)(long)value : value;

    /// <summary>Python <c>a - b</c> for a float <paramref name="a"/> and an int-or-float <paramref name="b"/>.</summary>
    /// <param name="a">The float.</param>
    /// <param name="b">The number subtracted.</param>
    /// <returns>The float difference.</returns>
    public static double Minus(double a, PyNumber b) => a - ToDouble(b);

    /// <summary>Python <c>f &gt; n</c> with an exact int-versus-float comparison (NaN compares false).</summary>
    /// <param name="f">The float.</param>
    /// <param name="n">The number.</param>
    /// <returns>Whether <paramref name="f"/> is greater.</returns>
    public static bool Greater(double f, PyNumber n) => Compare(f, n) is > 0;

    /// <summary>Python <c>f &lt;= n</c> with an exact int-versus-float comparison (NaN compares false).</summary>
    /// <param name="f">The float.</param>
    /// <param name="n">The number.</param>
    /// <returns>Whether <paramref name="f"/> is less than or equal.</returns>
    public static bool LessOrEqual(double f, PyNumber n) => Compare(f, n) is <= 0;

    /// <summary>Python <c>max(a, b)</c> where <paramref name="a"/> may be an int: <paramref name="b"/> only when strictly greater, so ties keep <paramref name="a"/>'s type.</summary>
    /// <param name="a">The first operand (wins ties).</param>
    /// <param name="b">The second operand.</param>
    /// <returns>The winner with its own type.</returns>
    public static PyNumber Max(PyNumber a, double b) => Greater(b, a) ? PyNumber.OfFloat(b) : a;

    private static int? Compare(double f, PyNumber n)
    {
        if (!n.IsInt)
        {
            var g = n.FloatValue;
            return double.IsNaN(f) || double.IsNaN(g) ? null : (f < g ? -1 : (f > g ? 1 : 0));
        }

        if (double.IsNaN(f))
        {
            return null;
        }

        if (double.IsInfinity(f))
        {
            return f > 0 ? 1 : -1;
        }

        var floor = Math.Floor(f);
        var cmp = new BigInteger(floor).CompareTo(new BigInteger(n.IntValue));
        return cmp != 0 ? cmp : (f > floor ? 1 : 0);
    }
}
