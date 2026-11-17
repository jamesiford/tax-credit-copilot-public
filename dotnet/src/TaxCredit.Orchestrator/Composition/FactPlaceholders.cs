using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Features.Ai.Numeric;

namespace TaxCredit.Orchestrator.Composition;

/// <summary>A validated substitution and the raw text to check before trusting that substitution.</summary>
public sealed record PlaceholderExpansion(string Text, string Masked, FactIndex Index);

/// <summary>Failure codes never carry a guessed private path or the rejected model text.</summary>
public sealed class PlaceholderException : Exception
{
    /// <summary>Create a safe placeholder refusal.</summary>
    public PlaceholderException(string code) : base(code) { }
}

/// <summary>Only known, renderable fact paths may be masked before NumericGuard.CheckRaw.</summary>
public static partial class FactPlaceholders
{
    /// <summary>The exact copyable token handed to the narrator.</summary>
    public static string PlaceholderFor(string path, string? formatter = null) =>
        formatter is null ? "{{facts." + path + "}}" : "{{facts." + path + "|" + formatter + "}}";

    /// <summary>Resolve through Application formatting, refusing malformed, private, null or fenced tokens.</summary>
    public static PlaceholderExpansion Expand(string narration, FactIndex facts, FactIndex? modelFacts = null)
    {
        ArgumentNullException.ThrowIfNull(narration);
        ArgumentNullException.ThrowIfNull(facts);
        var shown = modelFacts ?? facts;
        var text = new StringBuilder();
        var masked = new StringBuilder();
        var cursor = 0;
        var index = facts;
        foreach (Match match in PlaceholderPattern().Matches(narration))
        {
            var path = match.Groups["path"].Value;
            var formatter = match.Groups["format"].Success ? match.Groups["format"].Value : null;
            if (InsideFence(narration, match.Index))
            {
                throw new PlaceholderException("placeholder_in_code_fence");
            }
            var rendered = Resolve(path, formatter, facts, shown, out var percent);
            if (percent)
            {
                index = index.WithPercent(path);
            }
            text.Append(narration.AsSpan(cursor, match.Index - cursor)).Append(rendered);
            masked.Append(narration.AsSpan(cursor, match.Index - cursor)).Append('█');
            cursor = match.Index + match.Length;
        }
        text.Append(narration.AsSpan(cursor));
        masked.Append(narration.AsSpan(cursor));
        if (masked.ToString().Contains("{{", StringComparison.Ordinal) ||
            masked.ToString().Contains("}}", StringComparison.Ordinal))
        {
            throw new PlaceholderException("malformed_placeholder");
        }
        return new(text.ToString(), masked.ToString(), index);
    }

    internal static string Formatter(string path, JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.String && DatePattern().IsMatch(value.GetString()!))
        {
            return "date";
        }
        var kind = value.ValueKind == JsonValueKind.String &&
            !IsNumeric(value.GetString()!) ? JsonValueKindHint.Text : JsonValueKindHint.Number;
        var inferred = NumericFormatting.InferFormatter(path, kind);
        if (kind == JsonValueKindHint.Number && path.Split('.')[^1] == "tax_year")
        {
            return "year";
        }
        return inferred == "number" && value.ValueKind == JsonValueKind.Number &&
            value.TryGetInt64(out _) ? "count" : inferred;
    }

    internal static bool IsNumeric(string value) => NumberPattern().IsMatch(value.Trim());

    private static string Resolve(string path, string? formatter, FactIndex facts, FactIndex shown, out bool percent)
    {
        if (!CompositionProjection.CanonicalPath(path) || facts.Ambiguous.Contains(path) || shown.Ambiguous.Contains(path))
        {
            throw new PlaceholderException("ambiguous_or_invalid_placeholder");
        }
        if (!shown.Leaves.ContainsKey(path) && facts.Leaves.ContainsKey(path))
        {
            throw new PlaceholderException("outside_model_view");
        }
        if (!shown.Leaves.TryGetValue(path, out var value) || !facts.Leaves.ContainsKey(path))
        {
            throw new PlaceholderException("unknown_placeholder");
        }
        if (value.ValueKind is JsonValueKind.Null or JsonValueKind.True or JsonValueKind.False)
        {
            throw new PlaceholderException("unrenderable_placeholder");
        }
        formatter ??= Formatter(path, value);
        percent = formatter is "percent" or "percent_points";
        var scalar = value.ValueKind == JsonValueKind.String ? value.GetString()! : value.GetRawText();
        var exponent = ExponentPattern().Match(scalar);
        if (scalar.Length > 20_000 || formatter is not ("text" or "date") && exponent.Success &&
            (!int.TryParse(exponent.Groups[1].Value, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var power) ||
                Math.Abs((long)power) > 5000))
        {
            throw new PlaceholderException("unrenderable_placeholder");
        }
        try
        {
            return CapabilityFormat.Render(System.Text.Json.Nodes.JsonNode.Parse(value.GetRawText()), formatter);
        }
        catch (Exception exception) when (exception is ArgumentException or FormatException or OverflowException or InvalidOperationException)
        {
            throw new PlaceholderException("invalid_placeholder_format");
        }
    }

    private static bool InsideFence(string text, int position)
    {
        string? opener = null;
        foreach (Match match in FencePattern().Matches(text))
        {
            if (match.Index > position)
            {
                break;
            }
            var fence = match.Groups[1].Value;
            if (opener is null)
            {
                opener = fence;
            }
            else if (fence == opener)
            {
                opener = null;
            }
        }
        return opener is not null;
    }

    [GeneratedRegex(@"\{\{\s*facts\.(?<path>[^{}|\s]+?)\s*(?:\|\s*(?<format>[A-Za-z_]+)\s*)?\}\}")]
    private static partial Regex PlaceholderPattern();

    [GeneratedRegex(@"^[ \t]*(`{3,}|~{3,})", RegexOptions.Multiline)]
    private static partial Regex FencePattern();

    [GeneratedRegex(@"^\d{4}-\d{2}-\d{2}(?:T|$)")]
    private static partial Regex DatePattern();

    [GeneratedRegex(@"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$")]
    private static partial Regex NumberPattern();

    [GeneratedRegex(@"[eE]([+-]?[0-9]+)$")]
    private static partial Regex ExponentPattern();
}
