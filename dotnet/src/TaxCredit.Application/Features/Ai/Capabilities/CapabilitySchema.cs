using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace TaxCredit.Application.Features.Ai.Capabilities;

/// <summary>Validates the catalogue's closed JSON-Schema vocabulary without coercing reader-owned values.</summary>
public static class CapabilitySchema
{
    /// <summary>Reports up to three path-bearing problems without coercing types or filling defaults.</summary>
    public static void Validate(JsonObject schema, JsonNode? value)
    {
        var errors = Errors(schema, value, "arguments").Take(3).ToArray();
        if (errors.Length != 0)
        {
            throw CapabilityException.Invalid(string.Join("; ", errors));
        }
    }

    private static IEnumerable<string> Errors(JsonObject schema, JsonNode? value, string path)
    {
        if (schema["oneOf"] is JsonArray alternatives &&
            alternatives.Count(node => !Errors(node!.AsObject(), value, path).Any()) != 1)
        {
            yield return $"{path}: must match exactly one allowed shape";
        }
        if (!MatchesType(schema["type"], value))
        {
            yield return $"{path}: incorrect JSON type";
            yield break;
        }
        if (schema["enum"] is JsonArray choices && !choices.Any(choice => Equal(choice, value)))
        {
            yield return $"{path}: value is not one of the allowed values";
        }
        foreach (var error in ObjectErrors(schema, value, path).Concat(ArrayErrors(schema, value, path))
            .Concat(ScalarErrors(schema, value, path)))
        {
            yield return error;
        }
    }

    private static IEnumerable<string> ObjectErrors(JsonObject schema, JsonNode? value, string path)
    {
        if (value is not JsonObject obj)
        {
            yield break;
        }
        foreach (var required in schema["required"]?.AsArray() ?? [])
        {
            if (!obj.ContainsKey(required!.GetValue<string>()))
            {
                yield return $"{path}: '{required.GetValue<string>()}' is a required property";
            }
        }
        var properties = schema["properties"] as JsonObject ?? [];
        foreach (var (name, entry) in obj.OrderBy(entry => entry.Key, StringComparer.Ordinal))
        {
            if (properties[name] is JsonObject child)
            {
                foreach (var error in Errors(child, entry, path == "arguments" ? name : $"{path}.{name}"))
                {
                    yield return error;
                }
            }
            else if (schema["additionalProperties"]?.GetValue<bool>() == false)
            {
                yield return $"{path}: unexpected property '{name}'";
            }
        }
    }

    private static IEnumerable<string> ArrayErrors(JsonObject schema, JsonNode? value, string path)
    {
        if (value is not JsonArray array)
        {
            yield break;
        }
        if (schema["maxItems"] is { } maximum && array.Count > maximum.GetValue<int>())
        {
            yield return $"{path}: too many items";
        }
        if (schema["items"] is not JsonObject items)
        {
            yield break;
        }
        for (var index = 0; index < array.Count; index++)
        {
            foreach (var error in Errors(items, array[index], $"{path}.{index}"))
            {
                yield return error;
            }
        }
    }

    private static IEnumerable<string> ScalarErrors(JsonObject schema, JsonNode? value, string path)
    {
        if (value is JsonValue scalar && scalar.GetValueKind() == JsonValueKind.String)
        {
            var text = scalar.GetValue<string>();
            var length = text.EnumerateRunes().Count();
            if (schema["minLength"] is { } min && length < min.GetValue<int>() ||
                schema["maxLength"] is { } max && length > max.GetValue<int>())
            {
                yield return $"{path}: string length is outside the allowed bounds";
            }
            if (schema["pattern"] is { } pattern && !Regex.IsMatch(text, pattern.GetValue<string>(),
                RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1)))
            {
                yield return $"{path}: string does not match the required pattern";
            }
        }
        if (value is not JsonValue number || number.GetValueKind() != JsonValueKind.Number)
        {
            yield break;
        }
        var actual = double.Parse(number.ToJsonString(), CultureInfo.InvariantCulture);
        if (schema["minimum"] is { } low && actual < low.GetValue<double>() ||
            schema["maximum"] is { } high && actual > high.GetValue<double>() ||
            schema["exclusiveMinimum"] is { } exclusive && actual <= exclusive.GetValue<double>())
        {
            yield return $"{path}: number is outside the allowed bounds";
        }
    }

    private static bool MatchesType(JsonNode? type, JsonNode? value) => type switch
    {
        null => true,
        JsonArray options => options.Any(option => MatchesType(option, value)),
        _ => type.GetValue<string>() switch
        {
            "null" => value is null,
            "object" => value is JsonObject,
            "array" => value is JsonArray,
            "string" => value?.GetValueKind() == JsonValueKind.String,
            "boolean" => value?.GetValueKind() is JsonValueKind.True or JsonValueKind.False,
            "number" => value?.GetValueKind() == JsonValueKind.Number,
            "integer" => IsInteger(value),
            _ => false,
        },
    };

    internal static bool IsInteger(JsonNode? value) => value?.GetValueKind() == JsonValueKind.Number &&
        decimal.TryParse(value.ToJsonString(), NumberStyles.Float, CultureInfo.InvariantCulture, out var number) &&
        decimal.Truncate(number) == number;

    private static bool Equal(JsonNode? left, JsonNode? right) => JsonNode.DeepEquals(left, right) ||
        left?.GetValueKind() == JsonValueKind.Number && right?.GetValueKind() == JsonValueKind.Number &&
        decimal.TryParse(left.ToJsonString(), NumberStyles.Float, CultureInfo.InvariantCulture, out var a) &&
        decimal.TryParse(right.ToJsonString(), NumberStyles.Float, CultureInfo.InvariantCulture, out var b) && a == b;
}
