using System.Text.Json.Serialization;

namespace TaxCredit.Application.Features.Ai.Numeric;

/// <summary>Exact decimal values are strings so audit serialization cannot introduce floating-point drift.</summary>
public sealed record Numeral(
    [property: JsonPropertyName("text")] string Text,
    [property: JsonPropertyName("start")] int Start,
    [property: JsonPropertyName("end")] int End,
    [property: JsonPropertyName("kind")] string Kind,
    [property: JsonPropertyName("value")] string? Value = null)
{
    /// <summary>Whether this token claims percentage points rather than an unscaled quantity.</summary>
    [JsonIgnore]
    public bool Percent => Kind == "percent";

    /// <summary>Whether exact spelling, not just numeric equality, is required.</summary>
    [JsonIgnore]
    public bool Abbreviated => Kind == "abbreviated";
}

/// <summary>Audit diagnostics identify a refusal, never repair the original narration.</summary>
public sealed record NumericViolation(
    [property: JsonPropertyName("numeral")] Numeral Numeral,
    [property: JsonPropertyName("reason")] string Reason,
    [property: JsonPropertyName("stage")] string Stage,
    [property: JsonPropertyName("nearest_fact")] string? NearestFact);

/// <summary>A machine-readable verdict over every numeral in the supplied text.</summary>
public sealed record GuardResult(
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("violations")] IReadOnlyList<NumericViolation> Violations)
{
    /// <summary>True only when every numeral was accepted.</summary>
    [JsonIgnore]
    public bool Passed => Status == "pass";
}
