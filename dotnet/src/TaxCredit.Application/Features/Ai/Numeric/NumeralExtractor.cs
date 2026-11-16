using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace TaxCredit.Application.Features.Ai.Numeric;

/// <summary>Recognizes figures without normalizing Unicode lookalikes into trusted digits.</summary>
public static partial class NumeralExtractor
{
    /// <summary>The largest structural line-leading list number.</summary>
    public const int MaxListMarker = 99;
    /// <summary>The largest structural number immediately following "step".</summary>
    public const int MaxStep = 20;
    /// <summary>The largest ordinal exempt from fact matching.</summary>
    public const int MaxOrdinal = 10;

    /// <summary>Returns whole numeral surfaces and UTF-16 offsets, retaining every unsupported numeric rune.</summary>
    public static IReadOnlyList<Numeral> Extract(string text)
    {
        ArgumentNullException.ThrowIfNull(text);
        var found = new List<Numeral>();
        var offset = 0;
        foreach (var rune in text.EnumerateRunes())
        {
            if (!rune.IsAscii && Rune.GetUnicodeCategory(rune) is UnicodeCategory.DecimalDigitNumber
                or UnicodeCategory.OtherNumber or UnicodeCategory.LetterNumber)
            {
                found.Add(new(rune.ToString(), offset, offset + rune.Utf16SequenceLength, "non_ascii"));
            }

            offset += rune.Utf16SequenceLength;
        }

        var split = Split().Matches(text).Cast<Match>().ToArray();
        found.AddRange(split.Select(m => new Numeral(m.Value, m.Index, m.Index + m.Length, "non_ascii")));
        foreach (Match match in Token().Matches(text))
        {
            if (split.Any(s => s.Index <= match.Index && match.Index < s.Index + s.Length))
            {
                continue;
            }

            found.Add(match.Groups["date"].Success ? new(match.Value, match.Index, match.Index + match.Length, "date")
                : match.Groups["ty"].Success ? new(match.Value, match.Index, match.Index + match.Length, "year", match.Groups["year"].Value)
                : Number(text, match));
        }

        return found.OrderBy(n => n.Start).ThenBy(n => n.End).ToArray();
    }

    private static Numeral Number(string text, Match match)
    {
        var core = match.Groups["num"].Value;
        var value = ExactNumber.Parse(core.Replace(",", "", StringComparison.Ordinal));
        var (negative, currency, begin, paren) = Prefix(text, match.Index);
        var tail = match.Index + match.Length;
        var suffix = Suffix().Match(text[tail..]);
        var kind = currency ? "money" : "number";
        if (suffix.Success)
        {
            tail += suffix.Length;
            kind = suffix.Groups["percent"].Success ? "percent"
                : suffix.Groups["ordinal"].Success ? (core.Contains('.') ? kind : "ordinal") : "abbreviated";
            if (kind == "abbreviated")
            {
                value = ExactNumber.Scale(value, Power(suffix.Value.Trim().ToLowerInvariant()));
            }
        }

        if (paren >= 0 && tail < text.Length && text[tail] == ')')
        {
            negative = true;
            begin = paren;
            tail++;
        }

        value = value with { Negative = negative && !value.Coefficient.IsZero };
        var plain = !core.Contains('.') && !core.Contains(',') && !negative && !currency && kind == "number";
        if (plain && IsStructural(text, begin, tail, value))
        {
            kind = "structural";
        }

        return new(text[begin..tail], begin, tail, kind, ExactNumber.Plain(value));
    }

    private static bool IsStructural(string text, int begin, int end, TaxCredit.Domain.Numerics.PyDecimal value)
    {
        var line = text[(text.LastIndexOf('\n', Math.Max(0, begin - 1), begin) + 1)..begin];
        var small = TaxCredit.Domain.Numerics.PyDecimalOps.Compare(value, ExactNumber.Parse("99")) <= 0;
        if (small && end < text.Length && text[end] is '.' or ')' &&
            (end + 1 == text.Length || char.IsWhiteSpace(text[end + 1])) && ListLead().IsMatch(line))
        {
            return true;
        }

        return TaxCredit.Domain.Numerics.PyDecimalOps.Compare(value, ExactNumber.Parse("20")) <= 0
            && StepLead().IsMatch(text[..begin]);
    }

    private static (bool Negative, bool Currency, int Begin, int Paren) Prefix(string text, int start)
    {
        var window = Math.Max(0, start - 4);
        var match = NumberPrefix().Match(text[window..start]);
        var opened = match.Groups[1].Success;
        var sign = match.Groups[2];
        var before = opened ? '(' : sign.Success && window + sign.Index > 0 ? text[window + sign.Index - 1] : '\0';
        var signOk = sign.Success && !(char.IsLetterOrDigit(before) || ")]%".Contains(before));
        var negative = (signOk && sign.Value != "+") || match.Groups[4].Success;
        var begin = signOk ? window + sign.Index
            : match.Groups[3].Success ? window + match.Groups[3].Index
            : match.Groups[4].Success ? window + match.Groups[4].Index : start;
        return (negative, match.Groups[3].Success, begin, opened ? window + match.Groups[1].Index : -1);
    }

    private static int Power(string suffix) => suffix switch
    {
        "k" or "thousand" => 3,
        "m" or "mn" or "million" => 6,
        "b" or "bn" or "billion" => 9,
        _ => 12,
    };

    [GeneratedRegex(@"(?<date>(?<![0-9])[0-9]{4}-[0-9]{2}-[0-9]{2}(?![0-9])(?:T[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]+)?)?(?:Z|[+-][0-9]{2}:[0-9]{2})?)?)|(?<ty>(?<![A-Za-z])(?:TY|FY|CY)[ ]?(?<year>[0-9]{4})(?![0-9]))|(?<num>(?:[0-9]{1,3}(?:,[0-9]{3})+(?![0-9])|[0-9]+)(?:\.[0-9]+)?|(?<![0-9.])\.[0-9]+)")]
    private static partial Regex Token();

    [GeneratedRegex(@"[0-9][0-9\u00a0\u2007\u2009\u202f\u200a\u2008\u2002\u2003\u2004\u2005\u2006\u200b]*[\u00a0\u2007\u2009\u202f\u200a\u2008\u2002\u2003\u2004\u2005\u2006\u200b]+[0-9][0-9\u00a0\u2007\u2009\u202f\u200a\u2008\u2002\u2003\u2004\u2005\u2006\u200b]*")]
    private static partial Regex Split();

    [GeneratedRegex(@"(\()?([-−–+])?([$£€])?([-−–])?$")]
    private static partial Regex NumberPrefix();

    [GeneratedRegex(@"^(?:(?<percent>[ ]?(?:%|percent\b|per cent\b))|[ ]?(?:thousand|million|billion|trillion)\b|(?<ordinal>(?:st|nd|rd|th)\b)|(?:bn|mn|[kmbt])(?![A-Za-z]))", RegexOptions.IgnoreCase)]
    private static partial Regex Suffix();

    [GeneratedRegex(@"^\s*(?:[-*>\u2022]\s*)?$")]
    private static partial Regex ListLead();

    [GeneratedRegex(@"\bstep\s+$", RegexOptions.IgnoreCase)]
    private static partial Regex StepLead();
}
