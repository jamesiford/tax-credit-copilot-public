using TaxCredit.Api.Wire;
using TaxCredit.Application.Features.DraftsRuns;
using TaxCredit.Application.Messaging;

namespace TaxCredit.Api.Endpoints.DraftsRuns;

/// <summary>HTTP parsing and mediator dispatch only; calculation stays behind the durable executor.</summary>
public sealed class BatchEndpoints : IEndpointGroup
{
    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        endpoints.MapPost("/api/v2/run-batches", Start);
        endpoints.MapGet("/api/v2/run-batches", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new ListBatchesQuery((int)FeatureResponses.Number(context, "limit", 25),
                FeatureResponses.Number(context, "offset", 0), FeatureResponses.Query(context, "status")), context.RequestAborted));
        endpoints.MapGet("/api/v2/run-batches/{batch_id}", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new GetBatchQuery(FeatureResponses.Route(context, "batch_id")), context.RequestAborted));
        endpoints.MapGet("/api/v2/run-batches/{batch_id}/items", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new ListBatchItemsQuery(FeatureResponses.Route(context, "batch_id"),
                FeatureResponses.Query(context, "status"), (int)FeatureResponses.Number(context, "limit", 50),
                FeatureResponses.Number(context, "offset", 0)), context.RequestAborted));
        endpoints.MapPost("/api/v2/run-batches/{batch_id}/cancel", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new CancelBatchCommand(FeatureResponses.Route(context, "batch_id")), context.RequestAborted));
        endpoints.MapPost("/api/v2/run-batches/{batch_id}/retry-failed", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new RetryBatchCommand(FeatureResponses.Route(context, "batch_id")), context.RequestAborted));
    }

    private static Task<IResult> Start(HttpContext context, IMediator mediator)
    {
        var body = RequestValidator.Body(context);
        IRequest<object> request = body is { } value && value.TryGetProperty("dry_run", out var dry) && dry.ValueKind == System.Text.Json.JsonValueKind.True
            ? new PreviewBatchQuery(body) : new StartBatchCommand(body);
        return FeatureResponses.Send(mediator, request, context.RequestAborted, 202);
    }
}
