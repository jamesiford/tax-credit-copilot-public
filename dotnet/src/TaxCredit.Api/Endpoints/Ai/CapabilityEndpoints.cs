using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Api.Wire;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Messaging;

namespace TaxCredit.Api.Endpoints.Ai;

/// <summary>Capability refusals keep their machine-readable envelope distinct from body-binding errors.</summary>
public sealed class CapabilityEndpoints : IEndpointGroup
{
    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        endpoints.MapGet("/api/capabilities", async ([FromKeyedServices(AiFeatureModule.MediatorKey)] IMediator mediator, CancellationToken cancellationToken) =>
            Results.Json(await mediator.Send(new ListCapabilitiesQuery(), cancellationToken).ConfigureAwait(false)));
        endpoints.MapPost("/api/capabilities/{tool}", Invoke);
    }

    private static async Task<IResult> Invoke(string tool, HttpContext http,
        [FromKeyedServices(AiFeatureModule.MediatorKey)] IMediator mediator)
    {
        var body = RequestValidator.Body(http)!.Value;
        var args = body.TryGetProperty("args", out var value) ? JsonNode.Parse(value.GetRawText())!.AsObject() : new JsonObject();
        var query = new InvokeCapabilityQuery(tool, args, Optional(body, "idempotency_key"), Optional(body, "confirmation_token"));
        try { return Results.Json(await mediator.Send(query, http.RequestAborted).ConfigureAwait(false)); }
        catch (CapabilityException error) { return Results.Json(error.Body(), statusCode: error.StatusCode); }
    }

    private static string? Optional(JsonElement body, string name) =>
        body.TryGetProperty(name, out var value) && value.ValueKind != JsonValueKind.Null ? value.GetString() : null;
}
