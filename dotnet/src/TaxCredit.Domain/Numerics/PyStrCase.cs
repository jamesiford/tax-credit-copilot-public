using System.Globalization;
using System.Text;

namespace TaxCredit.Domain.Numerics;

/// <summary>Python <c>str.lower()</c>: the full Unicode lower-casing (U+0130 expands, a final sigma becomes <c>ς</c>).</summary>
/// <remarks>
/// Why a type of its own: <c>PyStr</c> ports <c>upper()</c> from generated tables; lower-casing is delegated per code point to the
/// BCL's simple mapping and only the two context-free or contextual rules the BCL lacks are added. "Cased" and "case ignorable"
/// (the final-sigma context) are approximated with Unicode general categories plus the Word_Break mid-letter punctuation.
/// </remarks>
public static class PyStrCase
{
    private const int CapitalDotI = 0x130;
    private const int CapitalSigma = 0x3A3;
    private const int FinalSigma = 0x3C2;
    private const int SmallSigma = 0x3C3;

    private static readonly HashSet<int> CaseIgnorablePunctuation =
    [
        0x27, 0x2E, 0x3A, 0xB7, 0x387, 0x55F, 0x5F4, 0x2018, 0x2019, 0x2024, 0x2027, 0xFE13, 0xFE52, 0xFE55, 0xFF07, 0xFF0E, 0xFF1A,
    ];

    /// <summary>Python <c>s.lower()</c>.</summary>
    /// <param name="s">The text.</param>
    /// <returns>The lower-cased text.</returns>
    public static string Lower(string s)
    {
        ArgumentNullException.ThrowIfNull(s);
        var points = CodePoints(s);
        var sb = new StringBuilder(s.Length);
        for (var i = 0; i < points.Count; i++)
        {
            var cp = points[i];
            if (cp == CapitalDotI)
            {
                sb.Append('i').Append('\u0307');
            }
            else if (cp == CapitalSigma)
            {
                sb.Append(char.ConvertFromUtf32(IsFinalSigma(points, i) ? FinalSigma : SmallSigma));
            }
            else if (cp is >= 0xD800 and <= 0xDFFF)
            {
                sb.Append((char)cp);
            }
            else if (IsPastUnicode15(cp))
            {
                sb.Append(char.ConvertFromUtf32(cp));
            }
            else
            {
                sb.Append(char.ConvertFromUtf32(Rune.ToLowerInvariant(new Rune(cp)).Value));
            }
        }

        return sb.ToString();
    }

    // The BCL carries Unicode 16 case pairs; CPython 3.12 (Unicode 15.0) leaves these characters unchanged.
    private static bool IsPastUnicode15(int cp) => cp is 0x1C89 or 0xA7CB or 0xA7CC or 0xA7DA or 0xA7DC or (>= 0x10D50 and <= 0x10D65);

    private static List<int> CodePoints(string s)
    {
        var points = new List<int>(s.Length);
        for (var i = 0; i < s.Length; i++)
        {
            if (char.IsHighSurrogate(s[i]) && i + 1 < s.Length && char.IsLowSurrogate(s[i + 1]))
            {
                points.Add(char.ConvertToUtf32(s[i], s[i + 1]));
                i++;
            }
            else
            {
                points.Add(s[i]);
            }
        }

        return points;
    }

    // Python's rule: a cased letter before (skipping case-ignorables) and none after.
    private static bool IsFinalSigma(List<int> points, int index)
    {
        var before = index - 1;
        while (before >= 0 && IsCaseIgnorable(points[before]))
        {
            before--;
        }

        if (before < 0 || !IsCased(points[before]))
        {
            return false;
        }

        var after = index + 1;
        while (after < points.Count && IsCaseIgnorable(points[after]))
        {
            after++;
        }

        return after >= points.Count || !IsCased(points[after]);
    }

    private static bool IsCased(int cp) => cp is not (>= 0xD800 and <= 0xDFFF)
        && CharUnicodeInfo.GetUnicodeCategory(cp) is UnicodeCategory.UppercaseLetter or UnicodeCategory.LowercaseLetter or UnicodeCategory.TitlecaseLetter;

    private static bool IsCaseIgnorable(int cp) => CaseIgnorablePunctuation.Contains(cp)
        || (cp is not (>= 0xD800 and <= 0xDFFF)
            && CharUnicodeInfo.GetUnicodeCategory(cp) is UnicodeCategory.NonSpacingMark or UnicodeCategory.EnclosingMark
                or UnicodeCategory.Format or UnicodeCategory.ModifierLetter or UnicodeCategory.ModifierSymbol);
}
