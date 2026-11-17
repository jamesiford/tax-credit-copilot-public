using TaxCredit.Api.Contract;
using TaxCredit.Application.Features.Framework;
using TaxCredit.Application.Messaging;

namespace TaxCredit.Api.Endpoints.Framework;

/// <summary>Public probes and schema documentation need no principal or business data.</summary>
public sealed class FrameworkEndpoints : IEndpointGroup
{
    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        endpoints.MapGet("/api/health", async (IMediator mediator, CancellationToken ct) =>
            Results.Json(await mediator.Send(new GetHealthQuery(), ct).ConfigureAwait(false)));
        endpoints.MapGet("/api/ready", async (IMediator mediator, CancellationToken ct) =>
            Results.Json(await mediator.Send(new GetReadinessQuery(), ct).ConfigureAwait(false)));
        endpoints.MapMethods("/openapi.json", ["GET", "HEAD"], () => Results.Json(RouteTable.OpenApi()));
        endpoints.MapMethods("/docs", ["GET", "HEAD"], () => Documentation("API documentation"));
        endpoints.MapMethods("/redoc", ["GET", "HEAD"], () => Documentation("API reference"));
        endpoints.MapMethods("/docs/oauth2-redirect", ["GET", "HEAD"], () => Results.Content(
            "<!doctype html><html lang=\"en\"><title>Authentication redirect</title><body>This host uses bearer authentication; no browser OAuth client is configured.</body></html>", "text/html; charset=utf-8"));
    }

    private static IResult Documentation(string title) => Results.Content(
        $"<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><title>{title}</title><body><h1>Tax Credit Copilot API</h1><p>OpenAPI describes the API operations and their request and response schemas.</p><a href=\"/openapi.json\">OpenAPI schema inventory</a></body></html>",
        "text/html; charset=utf-8");
}
