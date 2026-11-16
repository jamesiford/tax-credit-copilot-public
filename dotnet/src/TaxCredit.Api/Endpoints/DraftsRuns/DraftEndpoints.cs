using System.Globalization;
using System.Numerics;
using TaxCredit.Api.Wire;
using TaxCredit.Application.Features.DraftsRuns;
using TaxCredit.Application.Messaging;

namespace TaxCredit.Api.Endpoints.DraftsRuns;

/// <summary>Draft and catalogue transports expose only proposals, not runtime installation.</summary>
public sealed class DraftEndpoints : IEndpointGroup
{
    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/api/v2/programs", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new ProgramCatalogueQuery(), context.RequestAborted));
        endpoints.MapGet("/api/v2/programs/{code}", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new ProgramCatalogueQuery(FeatureResponses.Route(context, "code")), context.RequestAborted));
        endpoints.MapGet("/api/v2/program-drafts", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new ListDraftsQuery(FeatureResponses.Query(context, "status"),
                (int)FeatureResponses.Number(context, "limit", 50),
                BigInteger.Parse(FeatureResponses.Query(context, "offset") ?? "0", CultureInfo.InvariantCulture)), context.RequestAborted));
        endpoints.MapPost("/api/v2/program-drafts", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new CreateDraftCommand(RequestValidator.Body(context)), context.RequestAborted, 201));
        endpoints.MapGet("/api/v2/program-drafts/{draft_id}", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new GetDraftQuery(Id(context)), context.RequestAborted));
        endpoints.MapPut("/api/v2/program-drafts/{draft_id}/documents", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new EditDraftCommand(Id(context), RequestValidator.Body(context)), context.RequestAborted));
        endpoints.MapPost("/api/v2/program-drafts/{draft_id}/validate", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new ValidateDraftCommand(Id(context), RequestValidator.Body(context)), context.RequestAborted));
        endpoints.MapPost("/api/v2/program-drafts/{draft_id}/request-review", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new RequestDraftReviewCommand(Id(context), RequestValidator.Body(context)), context.RequestAborted));
        endpoints.MapPost("/api/v2/program-drafts/{draft_id}/review", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new ReviewDraftCommand(Id(context), RequestValidator.Body(context)), context.RequestAborted));
        endpoints.MapPost("/api/v2/program-drafts/{draft_id}/preview", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new PreviewDraftQuery(Id(context), RequestValidator.Body(context)), context.RequestAborted));
        endpoints.MapPost("/api/v2/program-drafts/{draft_id}/withdraw", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new WithdrawDraftCommand(Id(context), RequestValidator.Body(context)), context.RequestAborted));
        endpoints.MapPost("/api/v2/program-drafts/{draft_id}/export", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new ExportDraftCommand(Id(context), RequestValidator.Body(context)), context.RequestAborted, context: context));
        endpoints.MapGet("/api/v2/program-drafts/{draft_id}/export/manifest", (HttpContext context, IMediator mediator) =>
            FeatureResponses.Send(mediator, new DraftManifestQuery(Id(context)), context.RequestAborted));
    }

    private static string Id(HttpContext context) => FeatureResponses.Route(context, "draft_id");
}
