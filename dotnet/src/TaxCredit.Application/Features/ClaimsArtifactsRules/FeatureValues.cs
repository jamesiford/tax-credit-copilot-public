using System.Collections;
using System.Globalization;
using System.Numerics;
using System.Runtime.CompilerServices;
using System.Text.Json;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules;

/// <summary>Expected feature refusals retain the client's detail family, without exposing adapter diagnostics.</summary>
public sealed class FeatureRefusalException(int status, object detail) : Exception("Feature request refused.")
{
    /// <summary>The request outcome.</summary>
    public int Status { get; } = status;
    /// <summary>The safe string, object or validation detail.</summary>
    public object Detail { get; } = detail;
}

/// <summary>Converts certified value trees to ordinary wire objects without using the canonical evidence serializer.</summary>
public static class FeatureValues
{
    /// <summary>Keeps money text, numeric values and explicit nulls distinct.</summary>
    public static object? Wire(object? value) => value switch
    {
        PyDict map => map.ToDictionary(p => p.Key, p => Wire(p.Value), StringComparer.Ordinal),
        IReadOnlyDictionary<string, object?> map => map.ToDictionary(p => p.Key, p => Wire(p.Value), StringComparer.Ordinal),
        IDictionary map => map.Keys.Cast<string>().ToDictionary(key => key, key => Wire(map[key]), StringComparer.Ordinal),
        PyDateTime date => date.IsoFormat(),
        PyNumber number => number.IsInt ? (object)number.IntValue : number.FloatValue,
        PyDecimal money => money.ToString(),
        BigInteger number when number >= long.MinValue && number <= long.MaxValue => (long)number,
        IEnumerable sequence when value is not string => sequence.Cast<object?>().Select(Wire).ToArray(),
        not null when value.GetType().IsDefined(typeof(CompilerGeneratedAttribute), false) =>
            value.GetType().GetProperties().ToDictionary(p => p.Name, p => Wire(p.GetValue(value)), StringComparer.Ordinal),
        _ => value,
    };

    internal static PyDateTime Now(IClock clock)
    {
        var date = clock.UtcNow.UtcDateTime;
        return new PyDateTime(DateOnly.FromDateTime(date), date.Hour, date.Minute, date.Second,
            (int)(date.Ticks % TimeSpan.TicksPerSecond / 10), 0);
    }

    /// <summary>Reads a validated optional string without converting null to an empty assertion.</summary>
    public static string? Text(JsonElement body, string key) =>
        body.ValueKind == JsonValueKind.Object && body.TryGetProperty(key, out var item) && item.ValueKind != JsonValueKind.Null
            ? item.GetString() : null;

    /// <summary>Preserves the integer coercion accepted by the HTTP schema.</summary>
    public static long Whole(JsonElement body, string key) =>
        body.GetProperty(key) is var item && item.ValueKind == JsonValueKind.String
            ? long.Parse(item.GetString()!, CultureInfo.InvariantCulture) : item.GetInt64();

    /// <summary>Reads optional headcounts, never money.</summary>
    public static double? Number(JsonElement body, string key) =>
        body.TryGetProperty(key, out var item) && item.ValueKind != JsonValueKind.Null
            ? item.ValueKind == JsonValueKind.String ? double.Parse(item.GetString()!, CultureInfo.InvariantCulture) : item.GetDouble() : null;

    /// <summary>Retains supplied decimal scale before the claim domain applies its arithmetic.</summary>
    public static PyDecimal? Money(JsonElement body, string key)
    {
        if (!body.TryGetProperty(key, out var item) || item.ValueKind == JsonValueKind.Null) { return null; }
        return item.ValueKind == JsonValueKind.String ? PyDecimal.Parse(item.GetString()!)
            : item.GetRawText().Contains('e', StringComparison.OrdinalIgnoreCase)
                ? PyDecimal.FromFloatViaStr(item.GetDouble()) : PyDecimal.Parse(item.GetRawText());
    }
}
