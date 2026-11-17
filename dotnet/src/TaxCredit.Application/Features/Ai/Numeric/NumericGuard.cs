using System.Text.Json;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.Ai.Numeric;

/// <summary>ADR-008's two distinct gates: model-authored digits first, trusted substituted facts second.</summary>
public static class NumericGuard
{
    /// <summary>Checks substituted output against a trusted fact object, with no rounding allowance.</summary>
    public static GuardResult Check(string text, JsonElement facts, AllowedContext? allowedContext = null) =>
        Check(text, FactIndex.FromFacts(facts), allowedContext);

    /// <summary>Checks every figure against an existing index and explicit reader context.</summary>
    public static GuardResult Check(string text, FactIndex facts, AllowedContext? allowedContext = null,
        string stage = "final")
    {
        ArgumentNullException.ThrowIfNull(facts);
        var context = allowedContext ?? new AllowedContext();
        var violations = new List<NumericViolation>();
        foreach (var numeral in NumeralExtractor.Extract(text))
        {
            var reason = Judge(numeral, facts, context);
            if (reason is not null)
            {
                violations.Add(new(numeral, reason, stage,
                    numeral.Value is null ? null : facts.Nearest(ExactNumber.Parse(numeral.Value))));
            }
        }

        return new(violations.Count == 0 ? "pass" : "rejected", violations.AsReadOnly());
    }

    /// <summary>
    /// Matches application/numeric/guard.py check_raw: checks the supplied text against no facts.
    /// It does not recognize, validate, mask or substitute placeholders. The caller must first replace
    /// each validated placeholder with a nonnumeric boundary marker (Python's composer uses █), then
    /// call this method before substitution. Digits in unmasked placeholder paths are checked too.
    /// Call Check on the complete reply after trusted substitution.
    /// </summary>
    public static GuardResult CheckRaw(string text, AllowedContext? allowedContext = null) =>
        Check(text, FactIndex.FromFacts(JsonSerializer.SerializeToElement(new { })), allowedContext, "narration");

    private static string? Judge(Numeral numeral, FactIndex facts, AllowedContext context)
    {
        if (numeral.Kind == "structural")
        {
            return null;
        }

        if (numeral.Kind == "non_ascii")
        {
            return "a digit or numeric character that no formatter emits (non-ASCII, or split by a space)";
        }

        if (numeral.Kind == "date")
        {
            return facts.Dates.Contains(numeral.Text) || context.Surfaces.Contains(numeral.Text)
                ? null : "a date that is not in the facts";
        }

        if (numeral.Value is null)
        {
            return "a numeral with no value";
        }

        var value = ExactNumber.Parse(numeral.Value);
        if (numeral.Kind == "ordinal" && PyDecimalOps.Compare(value, ExactNumber.Parse("1")) >= 0
            && PyDecimalOps.Compare(value, ExactNumber.Parse("10")) <= 0)
        {
            return null;
        }

        if (numeral.Abbreviated)
        {
            return facts.Spellings.Contains(numeral.Text) || context.Surfaces.Contains(numeral.Text)
                ? null : "an abbreviation the formatter did not emit";
        }

        if (numeral.Percent)
        {
            return facts.PercentValues.Contains(value) || context.Percents.Contains(value)
                ? null : "a percentage that is not in the facts";
        }

        return facts.Values.Contains(value) || context.Values.Contains(value)
            ? null : "a figure that is not in the facts";
    }
}
