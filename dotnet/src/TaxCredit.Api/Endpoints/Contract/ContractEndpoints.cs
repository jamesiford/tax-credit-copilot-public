using System.Text.Json;
using TaxCredit.Api.Hosting;
using TaxCredit.Api.Wire;
using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.Api.Endpoints.Contract;

/// <summary>Replay controls are registered only by an explicit startup flag, never by an HTTP environment change.</summary>
public sealed class ContractEndpoints(IConfiguration configuration) : IEndpointGroup
{
    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        if (configuration["TCC_CONTRACT_HOOKS"] != "1")
        {
            return;
        }

        endpoints.MapPost("/__contract__/drain", async (IContractWork work, CancellationToken ct) => Results.Json(new { drained = await work.Drain(ct).ConfigureAwait(false) }));
        endpoints.MapPost("/__contract__/mint", Mint);
        endpoints.MapPost("/__contract__/env", ChangeEnvironment);
        endpoints.MapPost("/__contract__/reset", Reset);
    }

    private static async Task<IResult> Mint(HttpContext context, ITokenMinter minter)
    {
        var spec = await Read(context).ConfigureAwait(false);
        return spec is null ? InvalidBody() : Results.Json(new { token = minter.Mint(spec.Value) });
    }

    private static async Task<IResult> ChangeEnvironment(HttpContext context, RuntimeConfiguration configuration, IContractWork work)
    {
        var spec = await Read(context).ConfigureAwait(false);
        if (spec is null)
        {
            return InvalidBody();
        }

        var set = new Dictionary<string, string>(StringComparer.Ordinal);
        if (spec.Value.TryGetProperty("set", out var values) && values.ValueKind != JsonValueKind.Null)
        {
            if (values.ValueKind != JsonValueKind.Object)
            {
                return InvalidBody();
            }

            foreach (var property in values.EnumerateObject())
            {
                set[property.Name] = property.Value.ToString();
            }
        }

        var unset = Strings(spec.Value, "unset");
        if (unset is null)
        {
            return InvalidBody();
        }

        configuration.Apply(set, unset);
        await work.EnvironmentChanged(context.RequestAborted).ConfigureAwait(false);
        return Results.Json(new { set = set.Keys.Order(StringComparer.Ordinal), unset = unset.Order(StringComparer.Ordinal) });
    }

    private static async Task<IResult> Reset(HttpContext context, RuntimeConfiguration configuration, RuntimeSources sources, IContractWork work)
    {
        var spec = await Read(context).ConfigureAwait(false);
        if (spec is null)
        {
            return InvalidBody();
        }

        var profile = spec.Value.TryGetProperty("profile", out var value) ? value.GetString()
            : context.Request.Query["profile"].FirstOrDefault() ?? configuration.Get("TCC_CONTRACT_PROFILE") ?? "P1";
        if (profile is not ("P1" or "P2" or "G1" or "G1L"))
        {
            return ApiErrors.Detail(422, "Unknown contract profile.");
        }

        configuration.Reset();
        sources.Reset();
        await work.Reset(profile, context.RequestAborted).ConfigureAwait(false);
        return Results.Json(new { reset = true, profile });
    }

    private static string[]? Strings(JsonElement spec, string name)
    {
        if (!spec.TryGetProperty(name, out var value) || value.ValueKind == JsonValueKind.Null)
        {
            return [];
        }

        return value.ValueKind == JsonValueKind.Array && value.EnumerateArray().All(v => v.ValueKind == JsonValueKind.String)
            ? value.EnumerateArray().Select(v => v.GetString()!).ToArray() : null;
    }

    private static async Task<JsonElement?> Read(HttpContext context)
    {
        try
        {
            using var reader = new StreamReader(context.Request.Body);
            var text = await reader.ReadToEndAsync(context.RequestAborted).ConfigureAwait(false);
            using var document = JsonDocument.Parse(string.IsNullOrWhiteSpace(text) ? "{}" : text);
            return document.RootElement.ValueKind == JsonValueKind.Object ? document.RootElement.Clone() : null;
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private static IResult InvalidBody() => ApiErrors.Detail(422, new[] { new ValidationIssue("model_attributes_type", ["body"], "Expected a JSON object.", null) });
}
