using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace TaxCredit.Api.Wire;

internal sealed class SchemaValidator(JsonElement definitions)
{
    internal List<ValidationIssue> Validate(JsonElement value, JsonElement schema, IReadOnlyList<object> location)
    {
        var issues = new List<ValidationIssue>();
        Check(value, schema, location, issues, 0);
        return issues;
    }

    private void Check(JsonElement value, JsonElement schema, IReadOnlyList<object> location, List<ValidationIssue> issues, int depth)
    {
        if (depth > 64)
        {
            throw new InvalidOperationException("Request schema recursion exceeds the host limit.");
        }

        if (schema.ValueKind == JsonValueKind.False)
        {
            issues.Add(new("value_error", location, "This value is not allowed.", value));
            return;
        }

        if (schema.ValueKind != JsonValueKind.Object)
        {
            return;
        }

        if (schema.TryGetProperty("$ref", out var reference))
        {
            schema = definitions.GetProperty(reference.GetString()!.Split('/')[^1]);
        }

        if (schema.TryGetProperty("anyOf", out var branches) || schema.TryGetProperty("oneOf", out branches))
        {
            CheckBranches(value, branches, location, issues, depth);
            return;
        }

        if (!CheckType(value, schema, location, issues))
        {
            return;
        }

        CheckConstraints(value, schema, location, issues);
        CheckChildren(value, schema, location, issues, depth);
    }

    private void CheckBranches(JsonElement value, JsonElement branches, IReadOnlyList<object> location, List<ValidationIssue> issues, int depth)
    {
        List<ValidationIssue>? best = null;
        foreach (var branch in branches.EnumerateArray())
        {
            var candidate = new List<ValidationIssue>();
            Check(value, branch, location, candidate, depth + 1);
            if (candidate.Count == 0)
            {
                return;
            }

            if (best is null || candidate.Count < best.Count)
            {
                best = candidate;
            }
        }

        issues.AddRange(best ?? [new("value_error", location, "No allowed schema accepts this value.", value)]);
    }

    private static bool CheckType(JsonElement value, JsonElement schema, IReadOnlyList<object> location, List<ValidationIssue> issues)
    {
        if (!schema.TryGetProperty("type", out var type))
        {
            return true;
        }

        var expected = type.GetString();
        var valid = expected switch
        {
            "object" => value.ValueKind == JsonValueKind.Object,
            "array" => value.ValueKind == JsonValueKind.Array,
            "string" => value.ValueKind == JsonValueKind.String,
            "null" => value.ValueKind == JsonValueKind.Null,
            "integer" => Number(value, out var n) && double.IsInteger(n),
            "number" => Number(value, out _),
            "boolean" => value.ValueKind is JsonValueKind.True or JsonValueKind.False,
            _ => true,
        };
        if (!valid)
        {
            var code = expected switch
            {
                "object" => "model_attributes_type",
                "integer" => "int_parsing",
                "number" => "float_parsing",
                "array" => "list_type",
                _ => expected + "_type",
            };
            issues.Add(new(code, location, $"Expected {expected}.", value));
        }

        return valid;
    }

    private void CheckChildren(JsonElement value, JsonElement schema, IReadOnlyList<object> location, List<ValidationIssue> issues, int depth)
    {
        if (value.ValueKind == JsonValueKind.Object && schema.TryGetProperty("properties", out var properties))
        {
            foreach (var property in properties.EnumerateObject())
            {
                if (value.TryGetProperty(property.Name, out var child))
                {
                    Check(child, property.Value, [.. location, property.Name], issues, depth + 1);
                }
                else if (schema.TryGetProperty("required", out var required) && required.EnumerateArray().Any(r => r.GetString() == property.Name))
                {
                    issues.Add(new("missing", [.. location, property.Name], "Field required.", value));
                }
            }

            if (schema.TryGetProperty("additionalProperties", out var additional) && additional.ValueKind == JsonValueKind.False)
            {
                foreach (var property in value.EnumerateObject().Where(p => !properties.TryGetProperty(p.Name, out _)))
                {
                    issues.Add(new("extra_forbidden", [.. location, property.Name], "Unexpected field.", property.Value));
                }
            }
        }
        else if (value.ValueKind == JsonValueKind.Array && schema.TryGetProperty("items", out var items))
        {
            var i = 0;
            foreach (var child in value.EnumerateArray())
            {
                Check(child, items, [.. location, i++], issues, depth + 1);
            }
        }
    }

    private static void CheckConstraints(JsonElement value, JsonElement schema, IReadOnlyList<object> location, List<ValidationIssue> issues)
    {
        if (schema.TryGetProperty("enum", out var choices) && !choices.EnumerateArray().Any(c => JsonElement.DeepEquals(c, value)))
        {
            issues.Add(new("literal_error", location, "Value is not one of the allowed choices.", value));
        }

        if (Number(value, out var number))
        {
            foreach (var (keyword, code, passes) in new (string, string, Func<double, bool>)[]
            {
                ("minimum", "greater_than_equal", bound => number >= bound),
                ("maximum", "less_than_equal", bound => number <= bound),
                ("exclusiveMinimum", "greater_than", bound => number > bound),
                ("exclusiveMaximum", "less_than", bound => number < bound),
            })
            {
                if (schema.TryGetProperty(keyword, out var bound) && !passes(bound.GetDouble()))
                {
                    issues.Add(new(code, location, $"Value violates {keyword}.", value));
                }
            }
        }

        if (value.ValueKind == JsonValueKind.String)
        {
            CheckString(value, schema, location, issues);
        }
        else if (value.ValueKind == JsonValueKind.Array)
        {
            CheckLength(value, schema, location, issues, value.GetArrayLength(), "minItems", "maxItems");
        }
    }

    private static void CheckString(JsonElement value, JsonElement schema, IReadOnlyList<object> location, List<ValidationIssue> issues)
    {
        var text = value.GetString()!;
        CheckLength(value, schema, location, issues, text.EnumerateRunes().Count(), "minLength", "maxLength");
        if (schema.TryGetProperty("pattern", out var pattern) && !Regex.IsMatch(text, pattern.GetString()!, RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1)))
        {
            issues.Add(new("string_pattern_mismatch", location, "Value does not match the required pattern.", value));
        }

        if (schema.TryGetProperty("format", out var format))
        {
            var valid = format.GetString() switch
            {
                "date" => DateOnly.TryParseExact(text, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out _),
                "date-time" => DateTimeOffset.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.None, out _),
                "uuid" => Guid.TryParse(text, out _),
                _ => true,
            };
            if (!valid)
            {
                issues.Add(new("value_error", location, "Value has an invalid format.", value));
            }
        }
    }

    private static void CheckLength(JsonElement value, JsonElement schema, IReadOnlyList<object> location, List<ValidationIssue> issues, int length, string min, string max)
    {
        if (schema.TryGetProperty(min, out var lower) && length < lower.GetInt32())
        {
            issues.Add(new(value.ValueKind == JsonValueKind.String ? "string_too_short" : "too_short", location, "Value is too short.", value));
        }

        if (schema.TryGetProperty(max, out var upper) && length > upper.GetInt32())
        {
            issues.Add(new(value.ValueKind == JsonValueKind.String ? "string_too_long" : "too_long", location, "Value is too long.", value));
        }
    }

    internal static bool Number(JsonElement value, out double number)
    {
        number = 0;
        return (value.ValueKind == JsonValueKind.Number && value.TryGetDouble(out number)
            || value.ValueKind == JsonValueKind.String && double.TryParse(value.GetString(), NumberStyles.Float, CultureInfo.InvariantCulture, out number))
            && double.IsFinite(number);
    }
}
