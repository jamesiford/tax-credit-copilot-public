using System.Text.Json.Nodes;
using TaxCredit.Application.Messaging;

namespace TaxCredit.Application.Features.Ai.Capabilities;

/// <summary>Lists declared channel capabilities without attempting their dependencies.</summary>
public sealed record ListCapabilitiesQuery : IQuery<JsonObject>;

/// <summary>Caller identity comes from the authenticated request scope, never from arguments.</summary>
public sealed record InvokeCapabilityQuery(string Tool, JsonObject Args, string? IdempotencyKey = null,
    string? ConfirmationToken = null) : IQuery<JsonObject>;

/// <summary>Transport adapters dispatch this read through the ordinary mediator.</summary>
public sealed class ListCapabilitiesHandler(CapabilityService service)
{
    /// <summary>The catalogue remains readable without invoking missing tool dependencies.</summary>
    public ValueTask<JsonObject> Handle(ListCapabilitiesQuery request, CancellationToken cancellationToken) =>
        ValueTask.FromResult(service.List());
}

/// <summary>The catalogue decides whether an invocation is a read, preview or governed command.</summary>
public sealed class InvokeCapabilityHandler(CapabilityService service)
{
    /// <summary>Preserves the invocation boundary's authorization, limits and result envelope.</summary>
    public async ValueTask<JsonObject> Handle(InvokeCapabilityQuery request, CancellationToken cancellationToken) =>
        await service.InvokeAsync(request.Tool, request.Args, request.IdempotencyKey, request.ConfirmationToken, cancellationToken)
            .ConfigureAwait(false);
}
