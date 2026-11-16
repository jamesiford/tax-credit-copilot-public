namespace TaxCredit.Api.Wire;

/// <summary>A portable validation error: clients can identify the failing input without parsing English.</summary>
/// <param name="Type">The constraint or parsing failure.</param>
/// <param name="Loc">Body, query, path, header or cookie followed by the field path.</param>
/// <param name="Msg">A human-readable explanation.</param>
/// <param name="Input">The supplied value, or null for a missing field.</param>
public sealed record ValidationIssue(string Type, IReadOnlyList<object> Loc, string Msg, object? Input);
