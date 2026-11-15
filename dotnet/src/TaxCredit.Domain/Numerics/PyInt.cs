using System.Globalization;
using System.Numerics;
using System.Text;

namespace TaxCredit.Domain.Numerics;

/// <summary>Python <c>int(text)</c> for base-10 strings.</summary>
/// <remarks>
/// Why not <c>int.Parse</c>: Python strips Unicode whitespace, accepts any Unicode decimal digit (<c>int("١٥") == 15</c>),
/// allows single underscores between digits and leading zeros, and is unbounded; <c>int.Parse</c> with
/// <see cref="NumberStyles.Integer"/> accepts only ASCII digits and ASCII white space and overflows at 32 bits.
/// Source: CPython <c>Objects/longobject.c</c> (<c>PyLong_FromUnicodeObject</c>).
/// </remarks>
public static class PyInt
{
    /// <summary>Parses like <c>int(text)</c>; false where Python raises <c>ValueError</c>.</summary>
    public static bool TryParse(string text, out BigInteger value)
    {
        ArgumentNullException.ThrowIfNull(text);
        value = BigInteger.Zero;
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
        var negative = false;
        if (s.Length > 0 && (s[0] == '+' || s[0] == '-'))
        {
            negative = s[0] == '-';
            s = s[1..];
        }

        if (s.Length == 0 || s[0] == '_' || s[^1] == '_' || s.Contains("__", StringComparison.Ordinal))
        {
            return false;
        }

        var digits = s.Replace("_", string.Empty, StringComparison.Ordinal);
        if (digits.Any(ch => ch is < '0' or > '9'))
        {
            return false;
        }

        value = BigInteger.Parse(digits, NumberStyles.None, CultureInfo.InvariantCulture);
        if (negative)
        {
            value = -value;
        }

        return true;
    }
}
