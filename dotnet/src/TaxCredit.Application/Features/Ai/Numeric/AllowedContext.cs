using System.Globalization;
using System.Text.Json;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.Ai.Numeric;

/// <summary>Only reader-supplied text and explicit resolved scope belong here, never employee rows.</summary>
public sealed class AllowedContext
{
    internal HashSet<PyDecimal> Values { get; } = [];
    internal HashSet<PyDecimal> Percents { get; } = [];
    internal HashSet<string> Surfaces { get; } = new(StringComparer.Ordinal);

    /// <summary>Builds explicit reader context; booleans and noncanonical numeric objects are refused.</summary>
    public static AllowedContext Build(IEnumerable<string>? texts = null, IEnumerable<int>? years = null,
        IEnumerable<object>? numbers = null)
    {
        var context = new AllowedContext();
        foreach (var year in years ?? [])
        {
            context.Values.Add(ExactNumber.Parse(year.ToString(CultureInfo.InvariantCulture)));
        }

        foreach (var number in numbers ?? [])
        {
            var element = JsonSerializer.SerializeToElement(number);
            if (!FactIndex.TryNumber(element, out var value))
            {
                throw new ArgumentException("Context numbers must be finite canonical decimal values.", nameof(numbers));
            }

            context.Values.Add(value);
        }

        foreach (var numeral in (texts ?? []).SelectMany(text => NumeralExtractor.Extract(text ?? "")))
        {
            if (numeral.Kind is "structural" or "non_ascii")
            {
                continue;
            }

            if (numeral.Kind == "date" || numeral.Abbreviated)
            {
                context.Surfaces.Add(numeral.Text);
            }

            if (numeral.Value is not null)
            {
                (numeral.Percent ? context.Percents : context.Values).Add(ExactNumber.Parse(numeral.Value));
            }
        }

        return context;
    }
}
