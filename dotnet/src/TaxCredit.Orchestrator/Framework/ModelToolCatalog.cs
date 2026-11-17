using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;
using TaxCredit.Application.Features.Ai.Capabilities;

namespace TaxCredit.Orchestrator.Framework;

/// <summary>Projects the existing catalogue once; no definition closes over a caller or a turn.</summary>
public sealed class ModelToolCatalog
{
    private static readonly HashSet<string> Owned = new(StringComparer.Ordinal)
    {
        "client_id", "tax_year", "year", "base_year", "tax_years", "method",
        "magnitude", "hire_weekly_hours", "hire_hourly_rate",
    };
    private readonly Dictionary<string, JsonObject> _specs;

    /// <summary>The application catalogue is the authority, not a second literal list of tools.</summary>
    public ModelToolCatalog(CapabilityCatalog catalog)
    {
        _specs = catalog.ModelOffered().OfType<JsonObject>()
            .ToDictionary(spec => spec["name"]!.GetValue<string>(), StringComparer.Ordinal);
        Definitions = _specs.OrderBy(pair => pair.Key, StringComparer.Ordinal)
            .Select(pair => (AITool)new CatalogFunction(pair.Value)).ToArray();
    }

    /// <summary>Immutable framework definitions can be shared by all conversations.</summary>
    public IReadOnlyList<AITool> Definitions { get; }

    /// <summary>Returns a copy because callers must not mutate invocation policy.</summary>
    public JsonObject? Find(string name) => _specs.TryGetValue(name, out var spec)
        ? (JsonObject)spec.DeepClone() : null;

    /// <summary>Models may propose reader-owned values, but may never be required to guess them.</summary>
    public static JsonObject ModelSchema(JsonObject spec)
    {
        var schema = (JsonObject)spec["schema"]!.DeepClone();
        schema["properties"]!.AsObject().Remove("client_id");
        schema["required"] = new JsonArray(schema["required"]!.AsArray()
            .Select(node => node!.GetValue<string>()).Where(name => !Owned.Contains(name))
            .Select(name => (JsonNode?)JsonValue.Create(name)).ToArray());
        schema["additionalProperties"] = true;
        return schema;
    }

    private sealed class CatalogFunction(JsonObject spec) : AIFunction
    {
        public override string Name { get; } = spec["name"]!.GetValue<string>();
        public override string Description { get; } = spec["description"]!.GetValue<string>();
        public override JsonElement JsonSchema { get; } = JsonSerializer.SerializeToElement(ModelSchema(spec));

        protected override async ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments,
            CancellationToken cancellationToken)
        {
            var turn = arguments.Context?[FrameworkToolLoop.TurnKey] as IToolExecution
                ?? throw new InvalidOperationException("No attributed invocation context.");
            return await turn.ForwardAsync(Name, JsonSerializer.SerializeToNode(arguments)!.AsObject(),
                cancellationToken).ConfigureAwait(false);
        }
    }
}
