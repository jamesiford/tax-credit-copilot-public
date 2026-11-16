using System.Collections;
using System.Globalization;
using System.Numerics;
using System.Text.Json;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Converts transport trees without using the HTTP serializer for canonical evidence.</summary>
public static class FeatureValues
{
    internal static PyDict Copy(IEnumerable<KeyValuePair<string, object?>> values) =>
        values.Aggregate(new PyDict(), (map, pair) => map.Add(pair.Key, pair.Value));
    /// <summary>Reads the certified JSON tree, preserving integer and floating-point inputs.</summary>
    public static PyDict Document(JsonElement? body) =>
        body is { ValueKind: JsonValueKind.Object } value ? (PyDict)PyJson.Loads(value.GetRawText())! : new();

    /// <summary>Shapes ordered domain mappings as JSON objects, not key/value arrays.</summary>
    public static object? Wire(object? value) => value switch
    {
        PyDict map => map.ToDictionary(p => p.Key, p => Wire(p.Value), StringComparer.Ordinal),
        PyDateTime instant => instant.IsoFormat(),
        BigInteger number when number >= long.MinValue && number <= long.MaxValue => (long)number,
        BigInteger number => JsonSerializer.Deserialize<JsonElement>(number.ToString(CultureInfo.InvariantCulture)),
        IReadOnlyDictionary<string, object?> map => map.ToDictionary(p => p.Key, p => Wire(p.Value), StringComparer.Ordinal),
        IEnumerable sequence when value is not string => sequence.Cast<object?>().Select(Wire).ToArray(),
        _ => value,
    };

    /// <summary>Gets an optional text value.</summary>
    public static string? Text(PyDict body, string key, string? fallback = null) =>
        body.TryGetValue(key, out var value) && value is not null ? (string)value : fallback;

    /// <summary>Gets an integer that already passed transport validation.</summary>
    internal static long Integer(PyDict body, string key, long fallback = 0) =>
        body.TryGetValue(key, out var value) && value is not null
            ? checked((long)TaxCredit.Domain.Gold.GoldValues.ToInt(value)) : fallback;

    /// <summary>Gets an explicit boolean or its request default.</summary>
    public static bool Flag(PyDict body, string key, bool fallback = false) =>
        body.TryGetValue(key, out var value) ? value is true : fallback;

    /// <summary>Gets an object or an empty request default.</summary>
    public static PyDict Map(PyDict body, string key) => body.TryGetValue(key, out var value) && value is PyDict map ? map : new();

    /// <summary>Gets a request's integer list.</summary>
    public static IReadOnlyList<long> Years(PyDict body, string key) =>
        body.TryGetValue(key, out var value) && value is IEnumerable<object?> list
            ? list.Select(v => checked((long)TaxCredit.Domain.Gold.GoldValues.ToInt(v))).ToArray() : [];

    /// <summary>Uses the shared clock, omitting unused fractional precision like the source lifecycle.</summary>
    public static PyDateTime Now(IClock clock) => PyDateTime.FromIsoFormat(
        clock.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.FFFFFFzzz", CultureInfo.InvariantCulture));

    /// <summary>Attributes authenticated requests to the effective person.</summary>
    public static string Actor(IApiPrincipalAccessor principals, PyDict body, string field = "actor", string fallback = "anonymous") =>
        (principals.Current ?? ApiPrincipal.Anonymous).Attributed(Text(body, field), fallback);
}

/// <summary>A modeled feature refusal; transport retains the route family's error shape.</summary>
public sealed class DraftsRunsRefusalException(int status, object detail) : Exception("Drafts/runs request refused.")
{
    /// <summary>The modeled HTTP status.</summary>
    public int Status { get; } = status;
    /// <summary>Safe client-facing detail, never an upstream exception.</summary>
    public object Detail { get; } = detail;
}
