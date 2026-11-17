using System.Globalization;
using System.Numerics;

namespace TaxCredit.Domain.Numerics;

/// <summary>
/// Python <c>round()</c> on floats: correctly rounded, ties-to-even, decided on the <em>exact binary value</em>.
/// </summary>
/// <remarks>
/// Why not <c>Math.Round(double, int)</c>: .NET scales by a power of ten in floating point (<c>x * 10^n</c>),
/// rounds, and scales back, so a double like <c>2.675</c> (exactly 2.67499999999999982236431605997495353221893310546875)
/// can be rounded the wrong way when the scaled product lands on a tie. CPython instead rounds the exact
/// decimal expansion (<c>_Py_dg_dtoa</c> mode 3), so <c>round(2.675, 2) == 2.67</c>.
/// Here the double is decomposed into <c>m × 2^e</c>, scaled with <see cref="BigInteger"/> arithmetic and rounded
/// half-even; the decimal result is converted back with the correctly rounded <see cref="double.Parse(string)"/>.
/// Source: CPython <c>Objects/floatobject.c</c> (<c>double_round</c>).
/// </remarks>
public static class PyRound
{
    // CPython: ndigits beyond these bounds short-circuit (the result is x, or a signed zero).
    private const int NDigitsMax = 323;
    private const int NDigitsMin = -308;

    /// <summary>Python <c>round(x, ndigits)</c> for a float.</summary>
    public static double Round(double x, int ndigits)
    {
        if (!double.IsFinite(x) || x == 0)
        {
            return x;
        }

        if (ndigits > NDigitsMax)
        {
            return x;
        }

        if (ndigits < NDigitsMin)
        {
            return 0.0 * x;
        }

        var negative = x < 0;
        Decompose(Math.Abs(x), out var mantissa, out var exponent);
        var num = mantissa;
        var den = BigInteger.One;
        if (exponent >= 0)
        {
            num <<= exponent;
        }
        else
        {
            den <<= -exponent;
        }

        if (ndigits >= 0)
        {
            num *= BigInteger.Pow(10, ndigits);
        }
        else
        {
            den *= BigInteger.Pow(10, -ndigits);
        }

        var q = DivideHalfEven(num, den);
        if (q.IsZero)
        {
            return negative ? -0.0 : 0.0;
        }

        // q / 10^ndigits is the rounded decimal; parse it back with correct rounding.
        var text = q.ToString(CultureInfo.InvariantCulture) + "E" + (-ndigits).ToString(CultureInfo.InvariantCulture);
        var result = double.Parse(text, NumberStyles.Float, CultureInfo.InvariantCulture);
        if (double.IsInfinity(result))
        {
            throw new PyOverflowError("rounded value too large to represent");
        }

        return negative ? -result : result;
    }

    /// <summary>Python <c>round(x)</c> with no <c>ndigits</c>: the nearest integer, ties to even.</summary>
    /// <exception cref="PyValueError">For NaN.</exception>
    /// <exception cref="PyOverflowError">For infinity.</exception>
    public static BigInteger RoundToInteger(double x)
    {
        if (double.IsNaN(x))
        {
            throw new PyValueError("cannot convert float NaN to integer");
        }

        if (double.IsInfinity(x))
        {
            throw new PyOverflowError("cannot convert float infinity to integer");
        }

        if (x == 0)
        {
            return BigInteger.Zero;
        }

        Decompose(Math.Abs(x), out var mantissa, out var exponent);
        BigInteger q;
        if (exponent >= 0)
        {
            q = mantissa << exponent;
        }
        else
        {
            q = DivideHalfEven(mantissa, BigInteger.One << -exponent);
        }

        return x < 0 ? -q : q;
    }

    /// <summary>Python <c>round(v, ndigits)</c> for an integer with negative <paramref name="ndigits"/> (half-even).</summary>
    public static BigInteger RoundInteger(BigInteger v, int ndigits)
    {
        if (ndigits >= 0)
        {
            return v;
        }

        var p = BigInteger.Pow(10, -ndigits);
        var negative = v.Sign < 0;
        var q = DivideHalfEven(BigInteger.Abs(v), p) * p;
        return negative ? -q : q;
    }

    /// <summary>Divides non-negative <paramref name="num"/> by positive <paramref name="den"/>, rounding half to even.</summary>
    internal static BigInteger DivideHalfEven(BigInteger num, BigInteger den)
    {
        var q = BigInteger.DivRem(num, den, out var r);
        var twice = r * 2;
        var cmp = twice.CompareTo(den);
        if (cmp > 0 || (cmp == 0 && !q.IsEven))
        {
            q += 1;
        }

        return q;
    }

    private static void Decompose(double positive, out BigInteger mantissa, out int exponent)
    {
        var bits = BitConverter.DoubleToInt64Bits(positive);
        var biased = (int)((bits >> 52) & 0x7FF);
        var fraction = bits & 0xFFFFFFFFFFFFFL;
        if (biased == 0)
        {
            mantissa = fraction;
            exponent = -1074;
        }
        else
        {
            mantissa = fraction | (1L << 52);
            exponent = biased - 1075;
        }
    }
}
