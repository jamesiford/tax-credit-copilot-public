using System.Text;

namespace TaxCredit.Domain.Numerics;

/// <summary>
/// Python <c>str</c> semantics the engine relies on: <c>upper()</c>, <c>strip()</c>, <c>isspace()</c> and
/// code point ordering. Mirrors CPython's full Unicode behaviour using tables generated from the oracle
/// (<see cref="PyUnicodeTables"/>).
/// </summary>
/// <remarks>
/// Why not the BCL: <c>string.ToUpperInvariant()</c> applies only simple (1:1) case mapping, so
/// <c>"ß".upper()</c> is <c>"SS"</c> in Python and stays <c>"ß"</c> in .NET; <c>string.Trim()</c> uses a
/// different whitespace set (it ignores U+001C..U+001F, which Python treats as whitespace);
/// <c>string.CompareOrdinal</c> orders UTF-16 code units, which sorts astral characters before U+E000..U+FFFF,
/// the opposite of Python's code point order. Source: Python <c>Objects/unicodeobject.c</c>.
/// </remarks>
public static class PyStr
{
    /// <summary>Python <c>s.upper()</c> using full case mapping (multi-character expansions included).</summary>
    public static string Upper(string s)
    {
        ArgumentNullException.ThrowIfNull(s);
        var sb = new StringBuilder(s.Length);
        for (var i = 0; i < s.Length; i++)
        {
            var cp = CodePointAt(s, i, out var width);
            i += width - 1;
            var idx = Array.BinarySearch(PyUnicodeTables.UpperKeys, cp);
            if (idx < 0)
            {
                AppendCodePoint(sb, cp);
                continue;
            }

            for (var j = PyUnicodeTables.UpperOffsets[idx]; PyUnicodeTables.UpperData[j] != -1; j++)
            {
                AppendCodePoint(sb, PyUnicodeTables.UpperData[j]);
            }
        }

        return sb.ToString();
    }

    /// <summary>Python <c>c.isspace()</c> for a single code point.</summary>
    public static bool IsSpaceCodePoint(int codePoint) => Array.BinarySearch(PyUnicodeTables.Whitespace, codePoint) >= 0;

    /// <summary>Python <c>s.isspace()</c>: non-empty and every character is whitespace.</summary>
    public static bool IsSpace(string s)
    {
        ArgumentNullException.ThrowIfNull(s);
        if (s.Length == 0)
        {
            return false;
        }

        for (var i = 0; i < s.Length; i++)
        {
            var cp = CodePointAt(s, i, out var width);
            i += width - 1;
            if (!IsSpaceCodePoint(cp))
            {
                return false;
            }
        }

        return true;
    }

    /// <summary>Python <c>s.strip()</c> with no argument (strips Unicode whitespace both ends).</summary>
    public static string Strip(string s)
    {
        ArgumentNullException.ThrowIfNull(s);
        var start = 0;
        while (start < s.Length)
        {
            var cp = CodePointAt(s, start, out var width);
            if (!IsSpaceCodePoint(cp))
            {
                break;
            }

            start += width;
        }

        var end = s.Length;
        while (end > start)
        {
            var cp = CodePointBefore(s, end, out var width);
            if (!IsSpaceCodePoint(cp))
            {
                break;
            }

            end -= width;
        }

        return s[start..end];
    }

    /// <summary>Three-way comparison by Unicode code point, matching Python's <c>&lt;</c> / <c>==</c> on <c>str</c>.</summary>
    public static int Compare(string a, string b)
    {
        ArgumentNullException.ThrowIfNull(a);
        ArgumentNullException.ThrowIfNull(b);
        int i = 0, j = 0;
        while (i < a.Length && j < b.Length)
        {
            var ca = CodePointAt(a, i, out var wa);
            var cb = CodePointAt(b, j, out var wb);
            if (ca != cb)
            {
                return ca < cb ? -1 : 1;
            }

            i += wa;
            j += wb;
        }

        var remainingA = a.Length - i;
        var remainingB = b.Length - j;
        return remainingA == remainingB ? 0 : (remainingA < remainingB ? -1 : 1);
    }

    /// <summary>An <see cref="IComparer{T}"/> over <see cref="Compare"/>.</summary>
    public static IComparer<string> Comparer { get; } = System.Collections.Generic.Comparer<string>.Create(Compare);

    /// <summary>Python <c>len(s)</c>: the number of code points (not UTF-16 units).</summary>
    public static int Length(string s)
    {
        ArgumentNullException.ThrowIfNull(s);
        var n = 0;
        for (var i = 0; i < s.Length; i++)
        {
            CodePointAt(s, i, out var width);
            i += width - 1;
            n++;
        }

        return n;
    }

    /// <summary>Python <c>s[:count]</c>: the first <paramref name="count"/> code points.</summary>
    public static string Prefix(string s, int count)
    {
        ArgumentNullException.ThrowIfNull(s);
        var taken = 0;
        var i = 0;
        while (i < s.Length && taken < count)
        {
            CodePointAt(s, i, out var width);
            i += width;
            taken++;
        }

        return s[..i];
    }

    private static int CodePointAt(string s, int index, out int width)
    {
        var c = s[index];
        if (char.IsHighSurrogate(c) && index + 1 < s.Length && char.IsLowSurrogate(s[index + 1]))
        {
            width = 2;
            return char.ConvertToUtf32(c, s[index + 1]);
        }

        width = 1;
        return c;
    }

    /// <summary>Python <c>repr(s)</c>: quote choice, backslash escapes, and <c>\x</c>/<c>\u</c>/<c>\U</c> for non-printable characters.</summary>
    /// <remarks>
    /// Non-printable is Python's <c>str.isprintable</c> rule (categories Cc, Cf, Cs, Co, Cn, Zl, Zp, Zs other than the space).
    /// The BCL's Unicode data may be newer than CPython 3.12's (15.0), so a character assigned after 15.0 can differ.
    /// </remarks>
    /// <param name="s">The text.</param>
    /// <returns>The quoted representation.</returns>
    public static string Repr(string s)
    {
        ArgumentNullException.ThrowIfNull(s);
        var quote = s.Contains('\'', StringComparison.Ordinal) && !s.Contains('"', StringComparison.Ordinal) ? '"' : '\'';
        var sb = new StringBuilder().Append(quote);
        for (var i = 0; i < s.Length; i++)
        {
            var cp = CodePointAt(s, i, out var width);
            i += width - 1;
            if (cp == quote || cp == '\\')
            {
                sb.Append('\\').Append((char)cp);
            }
            else if (cp is '\t' or '\n' or '\r')
            {
                sb.Append(cp == '\t' ? "\\t" : cp == '\n' ? "\\n" : "\\r");
            }
            else if (cp < ' ' || cp == 0x7f)
            {
                sb.Append("\\x").Append(cp.ToString("x2", System.Globalization.CultureInfo.InvariantCulture));
            }
            else if (cp < 0x7f || IsPrintable(cp))
            {
                AppendCodePoint(sb, cp);
            }
            else
            {
                sb.Append(cp <= 0xff ? "\\x" + cp.ToString("x2", System.Globalization.CultureInfo.InvariantCulture)
                    : cp <= 0xffff ? "\\u" + cp.ToString("x4", System.Globalization.CultureInfo.InvariantCulture)
                    : "\\U" + cp.ToString("x8", System.Globalization.CultureInfo.InvariantCulture));
            }
        }

        return sb.Append(quote).ToString();
    }

    private static bool IsPrintable(int cp) => System.Globalization.CharUnicodeInfo.GetUnicodeCategory(cp) is not (
        System.Globalization.UnicodeCategory.Control or System.Globalization.UnicodeCategory.Format or System.Globalization.UnicodeCategory.Surrogate
        or System.Globalization.UnicodeCategory.PrivateUse or System.Globalization.UnicodeCategory.OtherNotAssigned
        or System.Globalization.UnicodeCategory.LineSeparator or System.Globalization.UnicodeCategory.ParagraphSeparator
        or System.Globalization.UnicodeCategory.SpaceSeparator);

    private static int CodePointBefore(string s, int endExclusive, out int width)
    {
        var c = s[endExclusive - 1];
        if (char.IsLowSurrogate(c) && endExclusive >= 2 && char.IsHighSurrogate(s[endExclusive - 2]))
        {
            width = 2;
            return char.ConvertToUtf32(s[endExclusive - 2], c);
        }

        width = 1;
        return c;
    }

    private static void AppendCodePoint(StringBuilder sb, int cp)
    {
        if (cp >= 0x10000)
        {
            sb.Append(char.ConvertFromUtf32(cp));
        }
        else
        {
            sb.Append((char)cp);
        }
    }
}
