using System.Globalization;
using System.Text;

namespace TaxCredit.Domain.Numerics;

/// <summary>
/// Python <c>float</c> text semantics: <c>repr()</c>/<c>str()</c> and <c>float(str)</c>, plus bit-level helpers.
/// </summary>
/// <remarks>
/// Why not the BCL: <c>double.ToString()</c> yields the shortest round-trip digits (same digits as Python's
/// <c>repr</c>) but a different layout (<c>1E-05</c>, <c>1E+16</c>, no trailing <c>.0</c>), and
/// <c>double.Parse</c> accepts things Python rejects (thousands separators, hex floats under some styles) and
/// rejects things Python accepts (underscores, Unicode digits and whitespace, <c>infinity</c>).
/// Source: CPython <c>Python/pystrtod.c</c> (<c>format_float_short</c>) and <c>Objects/floatobject.c</c>.
/// </remarks>
public static class PyFloat
{
    /// <summary>The IEEE-754 bit pattern of <paramref name="x"/>.</summary>
    public static long ToBits(double x) => BitConverter.DoubleToInt64Bits(x);

    /// <summary>The double with bit pattern <paramref name="bits"/>.</summary>
    public static double FromBits(long bits) => BitConverter.Int64BitsToDouble(bits);

    /// <summary>
    /// Bit-exact equality, except that all NaNs compare equal: .NET's <c>double.NaN</c> carries the sign bit
    /// while Python's does not, and Python cannot observe the difference through <c>repr</c> or arithmetic.
    /// </summary>
    public static bool SameBits(double a, double b) =>
        (double.IsNaN(a) && double.IsNaN(b)) || ToBits(a) == ToBits(b);

    /// <summary>Python <c>repr(x)</c> (identical to <c>str(x)</c> in Python 3).</summary>
    public static string Repr(double x)
    {
        if (double.IsNaN(x))
        {
            return "nan";
        }

        if (double.IsInfinity(x))
        {
            return x > 0 ? "inf" : "-inf";
        }

        var negative = double.IsNegative(x);
        if (x == 0)
        {
            return negative ? "-0.0" : "0.0";
        }

        ShortestDigits(Math.Abs(x), out var digits, out var decpt);
        var sb = new StringBuilder();
        if (negative)
        {
            sb.Append('-');
        }

        // repr switches to exponent form when the decimal point sits outside (-4, 16].
        if (decpt <= -4 || decpt > 16)
        {
            sb.Append(digits[0]);
            if (digits.Length > 1)
            {
                sb.Append('.').Append(digits, 1, digits.Length - 1);
            }

            var exp = decpt - 1;
            sb.Append('e').Append(exp < 0 ? '-' : '+');
            sb.Append(Math.Abs(exp).ToString("00", CultureInfo.InvariantCulture));
        }
        else if (decpt <= 0)
        {
            sb.Append("0.").Append('0', -decpt).Append(digits);
        }
        else if (decpt >= digits.Length)
        {
            sb.Append(digits).Append('0', decpt - digits.Length).Append(".0");
        }
        else
        {
            sb.Append(digits, 0, decpt).Append('.').Append(digits, decpt, digits.Length - decpt);
        }

        return sb.ToString();
    }

    /// <summary>
    /// Shortest decimal digit string that round-trips <paramref name="x"/> (positive, finite, non-zero) and the
    /// decimal point position: the value is <c>0.DIGITS × 10^decpt</c>.
    /// </summary>
    public static void ShortestDigits(double x, out string digits, out int decpt)
    {
        var s = x.ToString("R", CultureInfo.InvariantCulture);
        var exp = 0;
        var e = s.IndexOfAny(['E', 'e']);
        if (e >= 0)
        {
            exp = int.Parse(s.AsSpan(e + 1), NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture);
            s = s[..e];
        }

        var dot = s.IndexOf('.', StringComparison.Ordinal);
        var intPart = dot < 0 ? s : s[..dot];
        var frac = dot < 0 ? string.Empty : s[(dot + 1)..];
        var all = intPart + frac;
        decpt = intPart.Length + exp;
        var lead = 0;
        while (lead < all.Length - 1 && all[lead] == '0')
        {
            lead++;
            decpt--;
        }

        digits = all[lead..].TrimEnd('0');
        if (digits.Length == 0)
        {
            digits = "0";
        }
    }

    /// <summary>
    /// Python <c>float(text)</c>. Returns false where Python raises <c>ValueError</c>.
    /// Accepts surrounding Unicode whitespace, Unicode decimal digits, single underscores between digits,
    /// <c>inf</c>/<c>infinity</c>/<c>nan</c> in any case with an optional sign, and out-of-range exponents
    /// (which give <c>inf</c> or <c>0.0</c> rather than an error).
    /// </summary>
    public static bool TryParse(string text, out double value)
    {
        ArgumentNullException.ThrowIfNull(text);
        value = 0;
        var ascii = new StringBuilder(text.Length);
        for (var i = 0; i < text.Length; i++)
        {
            var c = text[i];
            if (c == '\0')
            {
                return false;
            }

            int cp = c;
            var width = 1;
            if (char.IsHighSurrogate(c) && i + 1 < text.Length && char.IsLowSurrogate(text[i + 1]))
            {
                cp = char.ConvertToUtf32(c, text[i + 1]);
                width = 2;
            }

            if (PyStr.IsSpaceCodePoint(cp))
            {
                ascii.Append(' ');
            }
            else if (cp < 128)
            {
                ascii.Append(c);
            }
            else
            {
                var d = CharUnicodeInfo.GetDecimalDigitValue(text, i);
                ascii.Append(d >= 0 ? (char)('0' + d) : '\u0001');
            }

            i += width - 1;
        }

        var s = ascii.ToString().Trim(' ');
        if (s.Length == 0 || !TryRemoveUnderscores(s, out s))
        {
            return false;
        }

        var body = s;
        var negative = false;
        if (body.Length > 0 && (body[0] == '+' || body[0] == '-'))
        {
            negative = body[0] == '-';
            body = body[1..];
        }

        if (body.Equals("inf", StringComparison.OrdinalIgnoreCase) || body.Equals("infinity", StringComparison.OrdinalIgnoreCase))
        {
            value = negative ? double.NegativeInfinity : double.PositiveInfinity;
            return true;
        }

        if (body.Equals("nan", StringComparison.OrdinalIgnoreCase))
        {
            value = double.NaN;
            return true;
        }

        if (!IsDecimalLiteral(body))
        {
            return false;
        }

        value = double.Parse(s, NumberStyles.Float, CultureInfo.InvariantCulture);
        return true;
    }

    private static bool TryRemoveUnderscores(string s, out string result)
    {
        result = s;
        if (!s.Contains('_', StringComparison.Ordinal))
        {
            return true;
        }

        var sb = new StringBuilder(s.Length);
        for (var i = 0; i < s.Length; i++)
        {
            if (s[i] != '_')
            {
                sb.Append(s[i]);
                continue;
            }

            if (i == 0 || i == s.Length - 1 || !IsAsciiDigit(s[i - 1]) || !IsAsciiDigit(s[i + 1]))
            {
                return false;
            }
        }

        result = sb.ToString();
        return true;
    }

    private static bool IsAsciiDigit(char c) => c is >= '0' and <= '9';

    /// <summary>digits [. [digits]] | . digits, then optional exponent.</summary>
    private static bool IsDecimalLiteral(string s)
    {
        var i = 0;
        var intDigits = 0;
        while (i < s.Length && IsAsciiDigit(s[i]))
        {
            i++;
            intDigits++;
        }

        var fracDigits = 0;
        if (i < s.Length && s[i] == '.')
        {
            i++;
            while (i < s.Length && IsAsciiDigit(s[i]))
            {
                i++;
                fracDigits++;
            }
        }

        if (intDigits + fracDigits == 0)
        {
            return false;
        }

        if (i < s.Length && (s[i] == 'e' || s[i] == 'E'))
        {
            i++;
            if (i < s.Length && (s[i] == '+' || s[i] == '-'))
            {
                i++;
            }

            var expDigits = 0;
            while (i < s.Length && IsAsciiDigit(s[i]))
            {
                i++;
                expDigits++;
            }

            if (expDigits == 0)
            {
                return false;
            }
        }

        return i == s.Length;
    }
}
