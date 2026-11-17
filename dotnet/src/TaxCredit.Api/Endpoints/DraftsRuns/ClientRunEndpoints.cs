using System.Globalization;
using TaxCredit.Api.Wire;
using TaxCredit.Application.Features.DraftsRuns;
using TaxCredit.Application.Messaging;

namespace TaxCredit.Api.Endpoints.DraftsRuns;

/// <summary>Client run and baseline transports dispatch to the ordinary mediator.</summary>
public sealed class ClientRunEndpoints : IEndpointGroup
{
    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints)
    {
        endpoints.MapPost("/api/v2/clients/{client_id}/runs", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new CalculateClientCommand(Client(context), RequestValidator.Body(context)), context.RequestAborted));
        endpoints.MapGet("/api/v2/clients/{client_id}/runs/latest", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new LatestClientRunQuery(Client(context)), context.RequestAborted));
        endpoints.MapPost("/api/v2/clients/{client_id}/units/{unit_id}/base-year", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new SetBaseYearCommand(Client(context), FeatureResponses.Route(context, "unit_id"),
                RequestValidator.Body(context)), context.RequestAborted));
        endpoints.MapGet("/api/v2/clients/{client_id}/units/{unit_id}/rebase", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new RebaseUnitQuery(Client(context), FeatureResponses.Route(context, "unit_id"),
                FeatureResponses.Number(context, "base_year", 0), FeatureResponses.Query(context, "method") ?? "min_max",
                FeatureResponses.Query(context, "state"), FeatureResponses.Query(context, "program_code")), context.RequestAborted));
    }

    private static long Client(HttpContext context) => long.Parse(FeatureResponses.Route(context, "client_id"), CultureInfo.InvariantCulture);
}
