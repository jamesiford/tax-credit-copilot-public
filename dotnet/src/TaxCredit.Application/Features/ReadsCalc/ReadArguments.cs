using System.Globalization;
using System.Text.Json;
using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Application.Features.ReadsCalc;

/// <summary>Validated transport selections, kept independent of HTTP for capability consumers.</summary>
public sealed class ReadArguments(IReadOnlyDictionary<string, string?> parameters, JsonElement? body = null)
{
    /// <summary>Normalized path and query scalar selections for other inward entry points.</summary>
    public IReadOnlyDictionary<string, string?> Parameters => parameters;

    /// <summary>The parsed request document, when this is a read-only POST.</summary>
    public JsonElement? Body { get; } = body;

    /// <summary>Returns the last scalar value, as the API contract requires.</summary>
    public string? Text(string name, string? fallback = null) =>
        parameters.GetValueOrDefault(name) ?? (Body is { } document && document.TryGetProperty(name, out var value)
            && value.ValueKind != JsonValueKind.Null ? value.ToString() : fallback);

    /// <summary>Reads an integer selection without silently truncating it.</summary>
    public int WholeNumber(string name, int fallback = 0) => Text(name) is { } value
        ? int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var result) ? result
            : throw new ReadRefusalException(422, "Integer selection is outside the supported range.")
        : fallback;

    /// <summary>An omitted integer is distinct from zero.</summary>
    public int? OptionalInt(string name) => Text(name) is null ? null : WholeNumber(name);

    /// <summary>Storage identity validation is deliberately not a global integer clamp.</summary>
    public long? Client(string name = "account_id")
    {
        if (Text(name) is not { } value) { return null; }
        if (long.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var id) && id <= 0)
        {
            throw new ReadRefusalException(404, "No payroll or accepted run exists for this client.");
        }
        return ClientIdentity.Parse(value);
    }

    /// <summary>Reads finite computation arguments only.</summary>
    public double Number(string name, double fallback = 0) => Text(name) is { } value
        ? double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out var result) && double.IsFinite(result) ? result
            : throw new ReadRefusalException(422, "A finite number is required.")
        : fallback;

    /// <summary>An omitted numeric bound must not narrow a cohort.</summary>
    public double? OptionalNumber(string name) => Text(name) is null ? null : Number(name);

    /// <summary>Boolean spellings follow the captured request binder.</summary>
    public bool Flag(string name) => Text(name)?.ToLowerInvariant() is "true" or "1" or "on" or "yes";

    /// <summary>One of the two independently certified readings.</summary>
    public string Method()
    {
        var method = Text("method", "min_max")!;
        return method is "min_max" or "pay_period" ? method : throw new ReadRefusalException(422, "method must be min_max | pay_period");
    }

    /// <summary>A checkpoint is a calendar date, never an ambient local timestamp.</summary>
    public DateOnly Date(string name, DateOnly fallback) => Text(name) is { } value
        ? DateOnly.TryParseExact(value, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var result) ? result
            : throw new ReadRefusalException(422, "Use an ISO calendar date.")
        : fallback;
}

/// <summary>A deliberate application refusal, translated into the JSON detail family by the API.</summary>
public sealed class ReadRefusalException(int statusCode, string message) : Exception(message)
{
    /// <summary>The semantic HTTP outcome, without a framework dependency.</summary>
    public int StatusCode { get; } = statusCode;
}
