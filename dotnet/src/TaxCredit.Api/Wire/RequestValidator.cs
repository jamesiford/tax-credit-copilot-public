using System.Globalization;
using System.Text.Json;
using TaxCredit.Api.Contract;

namespace TaxCredit.Api.Wire;

/// <summary>Validates before a handler binds, preventing missing inputs from silently becoming zero or false.</summary>
public sealed class RequestValidator(RouteTable table)
{
    /// <summary>The parsed body available to a handler after successful validation.</summary>
    public static JsonElement? Body(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        return context.Items.TryGetValue(typeof(RequestValidator), out var body) ? (JsonElement?)body : null;
    }

    /// <summary>Checks all declared locations and the request schema without invoking business code.</summary>
    public async Task<IReadOnlyList<ValidationIssue>> Validate(HttpContext context, RouteOperation operation)
    {
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(operation);
        var issues = new List<ValidationIssue>();
        var validator = new SchemaValidator(table.Schemas);
        foreach (var (location, parameters) in operation.Parameters)
        {
            foreach (var parameter in parameters)
            {
                CheckParameter(context, parameter, location, validator, issues);
            }
        }

        if (operation.RequestBodySchema.TryGetProperty("application/json", out var body))
        {
            await CheckBody(context, operation, body.GetProperty("schema"), validator, issues).ConfigureAwait(false);
        }

        CheckSafetyBounds(context, operation, issues);
        return issues;
    }

    private static void CheckSafetyBounds(HttpContext context, RouteOperation operation, List<ValidationIssue> issues)
    {
        var name = operation.Path switch
        {
            "/api/simulate/portfolio/{tax_year}" => "magnitude",
            "/api/progress/{tax_year}" => "within",
            _ => null,
        };
        if (name is not null && double.TryParse(context.Request.Query[name].LastOrDefault(), NumberStyles.Float, CultureInfo.InvariantCulture, out var value)
            && (name == "within" && value < 0 || name == "magnitude" && Math.Abs(value) > 10000))
        {
            issues.Add(new("value_error", ["query", name], "Value is outside the supported computation range.", value));
        }
    }

    private static void CheckParameter(HttpContext context, ParameterSpec parameter, string location, SchemaValidator validator, List<ValidationIssue> issues)
    {
        var values = location switch
        {
            "path" => new Microsoft.Extensions.Primitives.StringValues(Convert.ToString(context.Request.RouteValues.GetValueOrDefault(parameter.Name), CultureInfo.InvariantCulture)),
            "query" => context.Request.Query[parameter.Name],
            "header" => context.Request.Headers[parameter.Name],
            "cookie" => new Microsoft.Extensions.Primitives.StringValues(context.Request.Cookies[parameter.Name]),
            _ => default,
        };
        if (values.Count == 0)
        {
            if (parameter.Required)
            {
                issues.Add(new("missing", [location, parameter.Name], "Field required.", null));
            }

            return;
        }

        var schema = parameter.Schema;
        if (parameter.Annotation.StartsWith("list[", StringComparison.Ordinal))
        {
            var array = values.Select(v => ParseScalar(v ?? "", parameter.Annotation[5..^1])).ToArray();
            issues.AddRange(validator.Validate(JsonSerializer.SerializeToElement(array), schema, [location, parameter.Name]));
            return;
        }

        var value = ParseScalar(values[^1] ?? "", parameter.Annotation);
        issues.AddRange(validator.Validate(value, schema, [location, parameter.Name]));
        // The storage adapters cannot represent ids outside Int64. Refuse rather than overflow later (F-3).
        if (parameter.Annotation.StartsWith("int", StringComparison.Ordinal) && !long.TryParse(values[^1], NumberStyles.Integer, CultureInfo.InvariantCulture, out _))
        {
            if (!issues.Any(i => i.Loc.SequenceEqual(new object[] { location, parameter.Name })))
            {
                issues.Add(new("int_parsing", [location, parameter.Name], "Expected an integer within the supported range.", value));
            }
        }
    }

    private static JsonElement ParseScalar(string text, string annotation)
    {
        if (annotation.StartsWith("bool", StringComparison.Ordinal))
        {
            return text.ToUpperInvariant() switch
            {
                "TRUE" or "1" or "ON" or "YES" => JsonSerializer.SerializeToElement(true),
                "FALSE" or "0" or "OFF" or "NO" => JsonSerializer.SerializeToElement(false),
                _ => JsonSerializer.SerializeToElement(text),
            };
        }

        if (annotation.StartsWith("int", StringComparison.Ordinal) && long.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out var integer))
        {
            return JsonSerializer.SerializeToElement(integer);
        }

        if (annotation.StartsWith("float", StringComparison.Ordinal) && double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out var number) && double.IsFinite(number))
        {
            return JsonSerializer.SerializeToElement(number);
        }

        return JsonSerializer.SerializeToElement(text);
    }

    private static async Task CheckBody(HttpContext context, RouteOperation operation, JsonElement schema, SchemaValidator validator, List<ValidationIssue> issues)
    {
        context.Request.EnableBuffering();
        using var reader = new StreamReader(context.Request.Body, leaveOpen: true);
        var text = await reader.ReadToEndAsync(context.RequestAborted).ConfigureAwait(false);
        context.Request.Body.Position = 0;
        if (string.IsNullOrWhiteSpace(text))
        {
            if (operation.BodyRequired)
            {
                issues.Add(new("missing", ["body"], "Field required.", null));
            }

            return;
        }

        try
        {
            using var document = JsonDocument.Parse(text);
            var value = document.RootElement.Clone();
            context.Items[typeof(RequestValidator)] = value;
            issues.AddRange(validator.Validate(value, schema, ["body"]));
        }
        catch (JsonException)
        {
            issues.Add(new("json_invalid", ["body"], "The body must contain valid JSON.", null));
        }
    }
}
