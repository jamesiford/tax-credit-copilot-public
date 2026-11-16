using System.Text.Json;
using System.Text.RegularExpressions;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.Ai.Numeric;

/// <summary>Page summaries permit displayed precision; this is deliberately not ADR-008's exact gate.</summary>
public static partial class SummaryNumericGuard
{
    /// <summary>
    /// Matches tools/page_brief.py: binary64 displayed-precision comparison, including its 1e-9 allowance.
    /// This advisory portal check is deliberately looser than NumericGuard's exact decimal comparison.
    /// </summary>
    public static IReadOnlyList<string> UnsupportedFigures(string? text, JsonElement brief)
    {
        var known = BriefText(brief).SelectMany(Figures).Select(figure => figure.Value).ToArray();
        var missing = new List<string>();
        foreach (var (raw, value, precision) in Figures(text ?? ""))
        {
            if (value <= 12 && double.IsInteger(value))
            {
                continue;
            }

            if (known.Any(k => WithinPrecision(value, k, precision)))
            {
                continue;
            }

            if (!missing.Contains(raw, StringComparer.Ordinal))
            {
                missing.Add(raw);
            }
        }

        return missing.AsReadOnly();
    }

    private static IEnumerable<string> BriefText(JsonElement value)
    {
        switch (value.ValueKind)
        {
            case JsonValueKind.Object:
                foreach (var property in value.EnumerateObject())
                {
                    yield return property.Name;
                    foreach (var text in BriefText(property.Value))
                    {
                        yield return text;
                    }
                }

                break;
            case JsonValueKind.Array:
                foreach (var text in value.EnumerateArray().SelectMany(BriefText))
                {
                    yield return text;
                }

                break;
            case JsonValueKind.String:
                yield return value.GetString()!;
                break;
            case JsonValueKind.Number:
                yield return value.GetRawText();
                break;
        }
    }

    private static bool WithinPrecision(double value, double known, double precision) =>
        Math.Abs(value - known) <= precision / 2 + 1e-9;

    private static IEnumerable<(string Raw, double Value, double Precision)> Figures(string text)
    {
        foreach (Match match in Figure().Matches(text))
        {
            var digits = match.Groups[1].Value.Replace(",", "", StringComparison.Ordinal);
            if (!PyFloat.TryParse(digits, out var value))
            {
                continue;
            }

            var decimals = digits.Contains('.') ? digits.Length - digits.IndexOf('.') - 1 : 0;
            var scale = match.Groups[2].Value.ToLowerInvariant() switch { "k" => 1000, "m" => 1000000, _ => 1 };
            yield return (match.Value.Trim(), value * scale, scale * Math.Pow(10, -decimals));
        }
    }

    [GeneratedRegex(@"(?<![\d.,])\$?(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?\b")]
    private static partial Regex Figure();
}
