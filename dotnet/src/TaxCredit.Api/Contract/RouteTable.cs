using System.Text.Json;
using System.Text.Json.Serialization;

namespace TaxCredit.Api.Contract;

/// <summary>The generated operation contract; it is data, not a second business implementation.</summary>
public sealed record RouteOperation
{
    /// <summary>The HTTP method.</summary>
    public required string Method { get; init; }
    /// <summary>The path template without coercing route constraints.</summary>
    public required string Path { get; init; }
    /// <summary>The Python operation name.</summary>
    public required string Name { get; init; }
    /// <summary>The original endpoint for tracing ownership.</summary>
    public required string Endpoint { get; init; }
    /// <summary>Whether Python declares a response model.</summary>
    public bool Typed { get; init; }
    /// <summary>The independently owned replay group.</summary>
    public required string Group { get; init; }
    /// <summary>Declared parameters by location.</summary>
    public required IReadOnlyDictionary<string, IReadOnlyList<ParameterSpec>> Parameters { get; init; }
    /// <summary>The request schema by media type.</summary>
    public required JsonElement RequestBodySchema { get; init; }
    /// <summary>Whether an absent body is invalid.</summary>
    public bool BodyRequired { get; init; }
}

/// <summary>A binding contract enriched with bounds from the captured OpenAPI inventory.</summary>
public sealed record ParameterSpec
{
    /// <summary>The external parameter name.</summary>
    public required string Name { get; init; }
    /// <summary>Whether the parameter must be supplied.</summary>
    public bool Required { get; init; }
    /// <summary>The canonical Python annotation.</summary>
    public required string Annotation { get; init; }
    /// <summary>Type, enum and bound constraints.</summary>
    public required JsonElement Schema { get; init; }
}

/// <summary>Loads the checked-in registry without any runtime dependency on the Python checkout.</summary>
public sealed class RouteTable
{
    private sealed record Document(IReadOnlyList<RouteOperation> Routes, JsonElement Schemas);
    private static readonly JsonSerializerOptions Options = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        DefaultIgnoreCondition = JsonIgnoreCondition.Never,
    };

    /// <summary>The complete set of operations, including deferred gateway operations.</summary>
    public IReadOnlyList<RouteOperation> Operations { get; }

    /// <summary>The definitions referenced by request schemas.</summary>
    public JsonElement Schemas { get; }

    /// <summary>Creates the registry from its generated resource.</summary>
    public RouteTable()
    {
        using var stream = typeof(RouteTable).Assembly.GetManifestResourceStream("TaxCredit.Api.Contract.routes.generated.json")
            ?? throw new InvalidOperationException("Generated route table is absent.");
        var document = JsonSerializer.Deserialize<Document>(stream, Options)
            ?? throw new InvalidOperationException("Generated route table is invalid.");
        Operations = document.Routes;
        Schemas = document.Schemas;
    }

    /// <summary>Reads the public, captured OpenAPI schema inventory.</summary>
    public static JsonElement OpenApi()
    {
        using var stream = typeof(RouteTable).Assembly.GetManifestResourceStream("TaxCredit.Api.Contract.openapi.generated.json")
            ?? throw new InvalidOperationException("Generated OpenAPI document is absent.");
        using var document = JsonDocument.Parse(stream);
        return document.RootElement.Clone();
    }
}
