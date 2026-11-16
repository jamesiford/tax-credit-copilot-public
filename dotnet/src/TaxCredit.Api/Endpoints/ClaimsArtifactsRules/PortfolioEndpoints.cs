using TaxCredit.Application.Features.ClaimsArtifactsRules.Portfolio;

namespace TaxCredit.Api.Endpoints.ClaimsArtifactsRules;

/// <summary>Preserves the parameter-specific filter grammar, including stable unknown sorts.</summary>
public sealed class PortfolioEndpoints : IEndpointGroup
{
    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints) =>
        endpoints.MapGet("/api/v2/portfolio", (Delegate)((HttpContext c) => FeatureHttp.Send(c, () => new GetPortfolio(
            FeatureHttp.Year(c, "year"), FeatureHttp.Query(c, "program"), FeatureHttp.Query(c, "outcome"),
            FeatureHttp.Query(c, "scope"), FeatureHttp.Query(c, "near") is { } near ? near.ToLowerInvariant() is "true" or "1" or "yes" or "on" : null,
            FeatureHttp.Query(c, "status"), FeatureHttp.Query(c, "sort", "priority")!, FeatureHttp.Query(c, "order", "asc")!,
            checked((int)(FeatureHttp.Year(c, "limit") ?? 25)), checked((int)(FeatureHttp.Year(c, "offset") ?? 0))))));
}
