using System.Numerics;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Triggers;

/// <summary>Python's exact comparison of a float with an int-or-float (CPython compares the true values; NaN compares false with everything).</summary>
internal static class PyNumCompare
{
    /// <summary>Python <c>f &gt;= n</c>.</summary>
    /// <param name="f">The float.</param>
    /// <param name="n">The number.</param>
    /// <returns>Whether <paramref name="f"/> is at least <paramref name="n"/>.</returns>
    public static bool AtLeast(double f, PyNumber n) => Compare(f, n) is >= 0;

    /// <summary>Python <c>f &lt; n</c>.</summary>
    /// <param name="f">The float.</param>
    /// <param name="n">The number.</param>
    /// <returns>Whether <paramref name="f"/> is below <paramref name="n"/>.</returns>
    public static bool Below(double f, PyNumber n) => Compare(f, n) is < 0;

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
