using TaxCredit.Api.Wire;
using TaxCredit.Application.Features.ClaimsArtifactsRules;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Packages;
using TaxCredit.Application.Messaging;

namespace TaxCredit.Api.Endpoints.ClaimsArtifactsRules;

/// <summary>Only transport framing lives here; package publication and access audit are application operations.</summary>
public sealed class PackageEndpoints : IEndpointGroup
{
    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints)
    {
        endpoints.MapPost("/api/clients/{client_id}/packages", (Delegate)Create);
        endpoints.MapGet("/api/clients/{client_id}/artifacts/{artifact_id}", Download);
    }

    private static async Task<IResult> Create(HttpContext context)
    {
        var client = FeatureHttp.Client(context);
        var result = await FeatureHttp.Send(context, () => new CreatePackage(client,
            checked((int)FeatureHttp.Year(context, "tax_year")!.Value),
            FeatureHttp.Actor(context, fallback: "system:claim-package")), 201).ConfigureAwait(false);
        if (result is IValueHttpResult { Value: Dictionary<string, object?> metadata }
            && metadata.TryGetValue("artifact_id", out var id))
        {
            context.Response.Headers.Location = $"/api/clients/{client}/artifacts/{id}";
        }
        return result;
    }

    private static async Task<IResult> Download(HttpContext context, IMediator mediator)
    {
        try
        {
            var download = await mediator.Send(new DownloadArtifact(FeatureHttp.Client(context),
                FeatureHttp.Path(context, "artifact_id"), FeatureHttp.Principal(context)), context.RequestAborted).ConfigureAwait(false);
            context.Response.Headers.CacheControl = "no-store";
            context.Response.Headers["X-Content-SHA256"] = download.Sha256;
            context.Response.Headers.ContentDisposition = $"attachment; filename=\"{download.FileName}\"";
            return Results.Bytes(download.Data, download.ContentType);
        }
        catch (FeatureRefusalException refusal) { return ApiErrors.Detail(refusal.Status, refusal.Detail); }
    }
}
