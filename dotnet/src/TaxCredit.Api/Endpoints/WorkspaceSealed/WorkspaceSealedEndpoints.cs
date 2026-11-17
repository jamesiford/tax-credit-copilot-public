using System.Net;
using TaxCredit.Api.Contract;
using TaxCredit.Api.Wire;
using TaxCredit.Application.Features.WorkspaceSealed;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.Api.Endpoints.WorkspaceSealed;

/// <summary>Only the missing-extract path exists; no reference module or private source is accessed.</summary>
public sealed class WorkspaceSealedEndpoints(RouteTable table) : IEndpointGroup
{
    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        foreach (var route in table.Operations.Where(r => r.Group == "workspace_sealed"))
        {
            endpoints.MapMethods(route.Path, [route.Method], Handle);
        }
    }

    private static async Task<IResult> Handle(HttpContext context, IMediator mediator, IRuntimeConfiguration configuration)
    {
        if (context.Connection.RemoteIpAddress is not { } address || !IPAddress.IsLoopback(address))
        {
            return ApiErrors.Detail(403, "Reference Dataset detail is local-only until Entra authentication is enabled.");
        }

        if (configuration.Get("DATA_SOURCE") is "lakehouse" or "flex"
            && (string.IsNullOrEmpty(configuration.Get("FABRIC_WORKSPACE")) || string.IsNullOrEmpty(configuration.Get("FABRIC_LAKEHOUSE"))))
        {
            const string reason = "the data source is the lakehouse but FABRIC_WORKSPACE and FABRIC_LAKEHOUSE are not set.";
            const string remedy = "Set FABRIC_WORKSPACE and FABRIC_LAKEHOUSE (and ONELAKE_ENDPOINT for a private-link workspace). Set DATA_SOURCE=csv only for the local test fixture.";
            return Results.Json(new { detail = $"source_lakehouse unavailable: {reason} {remedy}", dependency = "source_lakehouse", reason, remedy }, statusCode: 503);
        }

        var availability = await mediator.Send(new GetWorkspaceAvailabilityQuery(), context.RequestAborted).ConfigureAwait(false);
        return context.Request.Path.Value is "/api/workspace" or "/api/workspace/refresh"
            ? Results.Json(availability)
            : ApiErrors.Detail(503, availability.Reason);
    }
}
