using System.Globalization;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.Ai.Numeric;

/// <summary>Lossless renderings shared by fact substitution and the guard's abbreviation allow-list.</summary>
public static class NumericFormatting
{
    /// <summary>Groups, pads or scales canonical digits without rounding a figure.</summary>
    public static string Format(string value, string formatter = "number")
    {
        if (formatter is not ("text" or "date" or "compact_money" or "money" or "count"
            or "headcount" or "year" or "percent" or "percent_points" or "number"))
        {
            throw new ArgumentException("Unknown numeric formatter.", nameof(formatter));
        }

        if (formatter == "text")
        {
            return value;
        }

        if (formatter == "date")
        {
            return DateOnly.ParseExact(value[..10], "yyyy-MM-dd", CultureInfo.InvariantCulture)
                .ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        }

        var number = ExactNumber.Parse(value);
        if (formatter == "compact_money")
        {
            return CompactVariants(number).FirstOrDefault() ?? Format(value, "money");
        }

        if (formatter is "year" or "count" && number.Exponent < 0)
        {
            throw new ArgumentException("The formatter requires a whole number.", nameof(value));
        }

        if (formatter == "year" && (PyDecimalOps.Compare(number, ExactNumber.Parse("1900")) < 0
            || PyDecimalOps.Compare(number, ExactNumber.Parse("2100")) > 0))
        {
            throw new ArgumentOutOfRangeException(nameof(value), "Not a tax year.");
        }

        if (formatter == "percent")
        {
            number = ExactNumber.Scale(number, 2);
        }

        var plain = ExactNumber.Plain(number with { Negative = false });
        var parts = plain.Split('.');
        var fraction = parts.Length == 2 ? parts[1] : "";
        if (formatter == "headcount" || (formatter == "money" && fraction.Length > 0))
        {
            fraction = fraction.PadRight(2, '0');
        }

        var whole = formatter == "year" ? parts[0] : Group(parts[0]);
        var body = whole + (fraction.Length > 0 ? "." + fraction : "");
        return (number.Negative ? "-" : "") + (formatter == "money" ? "$" : "") + body
            + (formatter is "percent" or "percent_points" ? "%" : "");
    }

    /// <summary>Infers presentation from the fact name, never its numeric magnitude.</summary>
    public static string InferFormatter(string path, JsonValueKindHint kind = JsonValueKindHint.Number)
    {
        var leaf = path.Split('.')[^1].ToLowerInvariant();
        if (kind == JsonValueKindHint.Text)
        {
            return "text";
        }

        return leaf.EndsWith("_usd", StringComparison.Ordinal) || leaf.EndsWith("_amount", StringComparison.Ordinal)
            || leaf.EndsWith("_dollars", StringComparison.Ordinal) ? "money"
            : leaf is "year" or "base_tax_year" or "lead_tax_year" || leaf.EndsWith("_tax_year", StringComparison.Ordinal) ? "year"
            : leaf.Contains("headcount", StringComparison.Ordinal) || leaf.EndsWith("_fte", StringComparison.Ordinal) ? "headcount"
            : leaf.EndsWith("_pct", StringComparison.Ordinal) || leaf.EndsWith("_percent", StringComparison.Ordinal) ? "percent_points"
            : "number";
    }

    internal static IEnumerable<string> CompactVariants(PyDecimal number)
    {
        foreach (var (power, shortUnit, longUnit) in new[] { (9, "B", "billion"), (6, "M", "million"), (3, "K", "thousand") })
        {
            if (PyDecimalOps.Compare(number with { Negative = false }, ExactNumber.Parse("1e" + power)) < 0)
            {
                continue;
            }

            var digits = ExactNumber.Plain(ExactNumber.Scale(number with { Negative = false }, -power));
            foreach (var spelling in new[] { $"${digits}{shortUnit}", $"{digits}{shortUnit}", $"${digits} {longUnit}", $"{digits} {longUnit}" })
            {
                yield return (number.Negative ? "-" : "") + spelling;
                if (number.Negative)
                {
                    yield return $"({spelling})";
                }
            }

            yield break;
        }
    }

    private static string Group(string whole) =>
        string.Concat(whole.Select((c, i) => (i > 0 && (whole.Length - i) % 3 == 0 ? "," : "") + c));
}

/// <summary>Disambiguates textual facts from numbers during bare placeholder rendering.</summary>
public enum JsonValueKindHint
{
    /// <summary>A canonical number.</summary>
    Number,
    /// <summary>Verbatim nonnumeric text.</summary>
    Text,
}
