using System.Globalization;
using System.Text.Json;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.Ai.Numeric;

/// <summary>Indexes only the trusted fact projection supplied by the caller; it never broadens a model's lane.</summary>
public sealed class FactIndex
{
    private readonly Dictionary<string, JsonElement> leaves;
    private readonly HashSet<string> percentPaths;
    private readonly HashSet<string> ambiguous;
    internal HashSet<PyDecimal> Values { get; } = [];
    internal HashSet<PyDecimal> PercentValues { get; } = [];
    internal HashSet<string> Spellings { get; } = new(StringComparer.Ordinal);
    internal HashSet<string> Dates { get; } = new(StringComparer.Ordinal);
    /// <summary>Trusted scalar facts indexed by dotted path for placeholder resolution.</summary>
    public IReadOnlyDictionary<string, JsonElement> Leaves => leaves.AsReadOnly();
    /// <summary>Paths whose conflicting definitions make them unsafe placeholder targets.</summary>
    public IReadOnlySet<string> Ambiguous => ambiguous;

    private FactIndex(Dictionary<string, JsonElement> leaves, HashSet<string> percentPaths, HashSet<string> ambiguous)
    {
        this.leaves = leaves;
        this.percentPaths = percentPaths;
        this.ambiguous = ambiguous;
        foreach (var (path, leaf) in leaves)
        {
            Index(path, leaf);
        }
    }

    /// <summary>Flattens a trusted fact object, retaining exact JSON number text.</summary>
    public static FactIndex FromFacts(JsonElement facts, IEnumerable<string>? percentPaths = null) =>
        FromFacts([facts], percentPaths: percentPaths);

    /// <summary>Combines results, optionally namespacing each to prevent ambiguous placeholder paths.</summary>
    public static FactIndex FromFacts(IEnumerable<JsonElement> facts, IReadOnlyList<string>? names = null,
        IEnumerable<string>? percentPaths = null)
    {
        var leaves = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
        var ambiguous = new HashSet<string>(StringComparer.Ordinal);
        var position = 0;
        foreach (var item in facts)
        {
            var flat = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
            Flatten(names is null ? "" : names[position], item, flat);
            foreach (var (path, value) in flat)
            {
                if (leaves.TryGetValue(path, out var previous) && !JsonElement.DeepEquals(previous, value))
                {
                    ambiguous.Add(path);
                }

                leaves.TryAdd(path, value);
            }

            position++;
        }

        return new(leaves, new(percentPaths ?? [], StringComparer.Ordinal), ambiguous);
    }

    /// <summary>Returns a new index allowing percentage renderings only for the specified fact.</summary>
    public FactIndex WithPercent(string path) => new(new(leaves), new(percentPaths, StringComparer.Ordinal) { path }, new(ambiguous));

    internal string? Nearest(PyDecimal value)
    {
        if (Values.Count == 0)
        {
            return null;
        }

        var exponent = Math.Min(value.Exponent, Values.Min(v => v.Exponent));
        var nearest = Values.OrderBy(v => ExactNumber.Distance(v, value, exponent))
            .ThenBy(v => v, Comparer<PyDecimal>.Create(PyDecimalOps.Compare)).First();
        return ExactNumber.Plain(nearest);
    }

    internal static bool TryNumber(JsonElement value, out PyDecimal number)
    {
        number = default;
        return value.ValueKind switch
        {
            JsonValueKind.Number => ExactNumber.TryParse(value.GetRawText(), out number, exponent: true),
            JsonValueKind.String => ExactNumber.TryParse(value.GetString()!, out number),
            _ => false,
        };
    }

    private void Index(string path, JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.String)
        {
            foreach (var numeral in NumeralExtractor.Extract(value.GetString()!))
            {
                if (numeral.Kind == "date")
                {
                    Dates.Add(numeral.Text);
                    if (DateOnly.TryParseExact(numeral.Text[..10], "yyyy-MM-dd", CultureInfo.InvariantCulture,
                        DateTimeStyles.None, out var date))
                    {
                        Dates.Add(date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture));
                    }
                }
                else if (numeral.Value is not null && numeral.Kind is not ("structural" or "non_ascii"))
                {
                    Values.Add(ExactNumber.Parse(numeral.Value));
                    Spellings.Add(numeral.Text);
                }
            }
        }

        if (!TryNumber(value, out var number))
        {
            return;
        }

        Values.Add(number);
        Spellings.UnionWith(NumericFormatting.CompactVariants(number));
        var leaf = path.Split('.')[^1];
        if (percentPaths.Contains(path) || leaf.EndsWith("_pct", StringComparison.OrdinalIgnoreCase)
            || leaf.EndsWith("_percent", StringComparison.OrdinalIgnoreCase))
        {
            PercentValues.Add(number);
            PercentValues.Add(ExactNumber.Scale(number, 2));
        }
    }

    private static void Flatten(string prefix, JsonElement value, Dictionary<string, JsonElement> output)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            foreach (var property in value.EnumerateObject())
            {
                Flatten(prefix.Length == 0 ? property.Name : $"{prefix}.{property.Name}", property.Value, output);
            }
        }
        else if (value.ValueKind == JsonValueKind.Array)
        {
            var position = 0;
            foreach (var item in value.EnumerateArray())
            {
                var name = (position++).ToString(CultureInfo.InvariantCulture);
                Flatten(prefix.Length == 0 ? name : $"{prefix}.{name}", item, output);
            }
        }
        else
        {
            output[prefix] = value.Clone();
        }
    }
}
