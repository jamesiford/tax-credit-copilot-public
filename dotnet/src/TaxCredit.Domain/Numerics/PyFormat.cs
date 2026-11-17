using System.Numerics;
using System.Text;

namespace TaxCredit.Domain.Numerics;

/// <summary>
/// Python's float format-spec mini-language for the three specs the What-If detail strings use: <c>g</c>, <c>,.Nf</c> and <c>+.Nf</c>.
/// </summary>
/// <remarks>
/// Why not <c>double.ToString("F2")</c>: CPython rounds the exact binary value half to even (<c>f"{0.125:.2f}"</c> is <c>0.12</c>) and
/// .NET's formatter breaks that tie away from zero. The value is therefore decomposed into <c>m × 2^e</c> and rounded with
/// <see cref="BigInteger"/> arithmetic, like <see cref="PyRound"/>. Source: CPython <c>Python/pystrtod.c</c> (<c>format_float_short</c>).
/// </remarks>
public static class PyFormat
{
    private const int GeneralPrecision = 6;

    /// <summary>Python <c>f"{x:g}"</c> (precision 6, trailing zeros removed, exponent form when the decimal exponent is below -4 or at least 6).</summary>
    /// <param name="x">The value.</param>
    /// <returns>The text.</returns>
    public static string General(double x)
    {
        if (!double.IsFinite(x))
        {
            return NonFinite(x, plus: false);
        }

        var negative = double.IsNegative(x);
        if (x == 0)
        {
            return negative ? "-0" : "0";
        }

        var (num, den) = Ratio(Math.Abs(x));
        var exp10 = DecimalExponent(num, den);
        var digits = Scaled(num, den, GeneralPrecision - 1 - exp10);
        if (digits == BigInteger.Pow(10, GeneralPrecision))
        {
            exp10++;
            digits /= 10;
        }

        var text = digits.ToString();
        string body;
        if (exp10 >= -4 && exp10 < GeneralPrecision)
        {
            body = exp10 >= 0
                ? text[..(exp10 + 1)] + "." + text[(exp10 + 1)..]
                : "0." + new string('0', -exp10 - 1) + text;
            body = TrimFraction(body);
        }
        else
        {
            var mantissa = TrimFraction(text[..1] + "." + text[1..]);
            body = mantissa + "e" + (exp10 < 0 ? "-" : "+") + Math.Abs(exp10).ToString("00", System.Globalization.CultureInfo.InvariantCulture);
        }

        return (negative ? "-" : string.Empty) + body;
    }

    /// <summary>Python <c>f"{x:,.Nf}"</c> or <c>f"{x:+.Nf}"</c> (and the plain <c>.Nf</c>): fixed notation, correctly rounded.</summary>
    /// <param name="x">The value.</param>
    /// <param name="decimals">Digits after the point.</param>
    /// <param name="grouping">Insert thousands separators (the <c>,</c> option).</param>
    /// <param name="plus">Always show a sign (the <c>+</c> option).</param>
    /// <returns>The text.</returns>
    public static string Fixed(double x, int decimals, bool grouping = false, bool plus = false)
    {
        if (!double.IsFinite(x))
        {
            return NonFinite(x, plus);
        }

        var (num, den) = Ratio(Math.Abs(x));
        var digits = Scaled(num, den, decimals).ToString().PadLeft(decimals + 1, '0');
        var whole = digits[..^decimals];
        if (grouping)
        {
            whole = Group(whole);
        }

        var sign = double.IsNegative(x) ? "-" : (plus ? "+" : string.Empty);
        return sign + whole + (decimals > 0 ? "." + digits[^decimals..] : string.Empty);
    }

    // Python prints inf and nan in lower case; nan never carries a minus sign.
    private static string NonFinite(double x, bool plus)
    {
        if (double.IsNaN(x))
        {
            return plus ? "+nan" : "nan";
        }

        return double.IsNegative(x) ? "-inf" : (plus ? "+inf" : "inf");
    }

    private static string Group(string whole)
    {
        var sb = new StringBuilder();
        for (var i = 0; i < whole.Length; i++)
        {
            if (i > 0 && (whole.Length - i) % 3 == 0)
            {
                sb.Append(',');
            }

            sb.Append(whole[i]);
        }

        return sb.ToString();
    }

    private static string TrimFraction(string text) => text.Contains('.') ? text.TrimEnd('0').TrimEnd('.') : text;

    // |x| as an exact fraction num/den.
    private static (BigInteger Num, BigInteger Den) Ratio(double abs)
    {
        var bits = BitConverter.DoubleToInt64Bits(abs);
        var biased = (int)((bits >> 52) & 0x7FF);
        var mantissa = bits & 0xFFFFFFFFFFFFFL;
        if (biased == 0)
        {
            biased = 1;
        }
        else
        {
            mantissa |= 1L << 52;
        }

        var e = biased - 1075;
        return e >= 0 ? (new BigInteger(mantissa) << e, BigInteger.One) : (new BigInteger(mantissa), BigInteger.One << -e);
    }

    // The X with 10^X <= num/den < 10^(X+1), decided exactly.
    private static int DecimalExponent(BigInteger num, BigInteger den)
    {
        var x = (int)Math.Floor(BigInteger.Log10(num) - BigInteger.Log10(den));
        while (AtLeastPowerOfTen(num, den, x + 1))
        {
            x++;
        }

        while (!AtLeastPowerOfTen(num, den, x))
        {
            x--;
        }

        return x;
    }

    private static bool AtLeastPowerOfTen(BigInteger num, BigInteger den, int x) =>
        x >= 0 ? num >= BigInteger.Pow(10, x) * den : num * BigInteger.Pow(10, -x) >= den;

    // round-half-even(num / den * 10^k), k may be negative.
    private static BigInteger Scaled(BigInteger num, BigInteger den, int k)
    {
        var n = k >= 0 ? num * BigInteger.Pow(10, k) : num;
        var d = k >= 0 ? den : den * BigInteger.Pow(10, -k);
        var q = BigInteger.DivRem(n, d, out var rem);
        var twice = rem * 2;
        return twice > d || (twice == d && !q.IsEven) ? q + 1 : q;
    }
}
