using System.Text.Json;

namespace TaxCredit.Application.Features.Ai.Numeric;

/// <summary>Page-summary entry point; intentionally separate from the exact channel numeral guard.</summary>
public static class PageFigureCheck
{
    /// <summary>Reports distinct unsupported spellings at their displayed precision without altering prose.</summary>
    public static IReadOnlyList<string> UnsupportedFigures(string? text, JsonElement brief) =>
        SummaryNumericGuard.UnsupportedFigures(text, brief);
}
