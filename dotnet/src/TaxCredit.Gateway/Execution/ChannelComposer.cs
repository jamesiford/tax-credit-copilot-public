using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Features.Ai.Numeric;

namespace TaxCredit.Gateway.Execution;

/// <summary>A checked reply never repairs a narrator's figure or silently trusts a formatter.</summary>
public sealed record ComposedReply(string Text, GuardResult Guard, bool NarrationUsed, bool BlocksVerified);

/// <summary>Reusable channel composition; this host itself never asks a model to generate a tool result.</summary>
public static class ChannelComposer
{
    private static readonly Regex Placeholder = new(@"\{\{\s*facts\.([^{}|\s]+?)\s*(?:\|\s*([A-Za-z_]+)\s*)?\}\}",
        RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1));
    private static readonly Regex Fence = new(@"^[ \t]*(```|~~~)", RegexOptions.Multiline | RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1));
    private static readonly Regex Date = new(@"\A\d{4}-\d{2}-\d{2}", RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1));
    private static readonly Regex Number = new(@"\A[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\z", RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1));

    /// <summary>Checks raw words, substitutes only validated trusted paths, then independently checks the complete reply.</summary>
    public static ComposedReply Compose(string blocks, string? narration, FactIndex facts,
        AllowedContext? context = null, string disclaimer = CapabilityResult.Disclaimer)
    {
        ArgumentNullException.ThrowIfNull(facts);
        var index = facts;
        var violations = new List<NumericViolation>();
        if (!string.IsNullOrWhiteSpace(narration))
        {
            try
            {
                var (masked, rendered, withPercent) = Substitute(narration, facts);
                index = withPercent;
                violations.AddRange(NumericGuard.CheckRaw(masked, context).Violations);
                violations.AddRange(NarrationPolicy.Review(masked, rendered));
                if (violations.Count == 0)
                {
                    var full = Join(rendered.Trim(), blocks, disclaimer);
                    var final = NumericGuard.Check(full, index, context);
                    if (final.Passed) { return new(full, final, true, true); }
                    violations.AddRange(final.Violations);
                }
            }
            catch (Exception error) when (error is ArgumentException or FormatException or OverflowException)
            {
                violations.Add(new(new("invalid placeholder", 0, 0, "placeholder"),
                    "A placeholder is malformed, ambiguous, missing, null or not exactly renderable.", "narration", null));
            }
        }
        var fallback = Join(blocks, disclaimer);
        var check = NumericGuard.Check(fallback, index, context);
        if (check.Passed) { return new(fallback, Verdict(violations), false, true); }
        violations.AddRange(check.Violations);
        return new(Join("The figures in this answer could not be verified against the engine's output, so none are shown.", disclaimer),
            Verdict(violations), false, false);
    }

    private static (string Masked, string Rendered, FactIndex Index) Substitute(string narration, FactIndex index)
    {
        var masked = new StringBuilder();
        var rendered = new StringBuilder();
        var cursor = 0;
        foreach (Match match in Placeholder.Matches(narration))
        {
            var path = match.Groups[1].Value;
            if (InFence(narration, match.Index) || index.Ambiguous.Contains(path) ||
                !index.Leaves.TryGetValue(path, out var value) || value.ValueKind is JsonValueKind.Null or JsonValueKind.True or JsonValueKind.False)
            { throw new ArgumentException("Unusable placeholder.", nameof(narration)); }
            var formatter = match.Groups[2].Success ? match.Groups[2].Value : Infer(path, value);
            var text = NumericFormatting.Format(value.ValueKind == JsonValueKind.String ? value.GetString()! : value.GetRawText(), formatter);
            if (formatter is "percent" or "percent_points") { index = index.WithPercent(path); }
            masked.Append(narration, cursor, match.Index - cursor).Append('\u2588');
            rendered.Append(narration, cursor, match.Index - cursor).Append(text);
            cursor = match.Index + match.Length;
        }
        masked.Append(narration, cursor, narration.Length - cursor);
        rendered.Append(narration, cursor, narration.Length - cursor);
        var raw = masked.ToString();
        if (raw.Contains("{{", StringComparison.Ordinal) || raw.Contains("}}", StringComparison.Ordinal))
        { throw new ArgumentException("Malformed placeholder.", nameof(narration)); }
        return (raw, rendered.ToString(), index);
    }

    private static string Infer(string path, JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.String && Date.IsMatch(value.GetString()!)) { return "date"; }
        var kind = value.ValueKind == JsonValueKind.String && !Number.IsMatch(value.GetString()!)
            ? JsonValueKindHint.Text : JsonValueKindHint.Number;
        return NumericFormatting.InferFormatter(path, kind);
    }
    private static bool InFence(string text, int position)
    {
        string? open = null;
        foreach (Match fence in Fence.Matches(text[..position]))
        { if (open is null) { open = fence.Groups[1].Value; } else if (open == fence.Groups[1].Value) { open = null; } }
        return open is not null;
    }
    private static GuardResult Verdict(List<NumericViolation> violations) => new(violations.Count == 0 ? "pass" : "rejected", violations.AsReadOnly());
    private static string Join(params string[] parts) => string.Join("\n\n", parts.Where(p => !string.IsNullOrWhiteSpace(p)));
}
