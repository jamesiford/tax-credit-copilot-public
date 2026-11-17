using TaxCredit.Application.Features.ClaimsArtifactsRules;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Claims;

namespace TaxCredit.Api.Endpoints.ClaimsArtifactsRules;

/// <summary>Translates HTTP scope and attributed bodies into audited claim use cases.</summary>
public sealed class ClaimEndpoints : IEndpointGroup
{
    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/api/claims/coverage/{client_id}", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new GetClientCoverage(FeatureHttp.Client(c), FeatureHttp.Query(c, "program_code"), Years(c)))));
        endpoints.MapGet("/api/claims/coverage", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new GetPortfolioCoverage(FeatureHttp.Year(c, "tax_year")))));
        endpoints.MapGet("/api/claims/cell/{client_id}/{program_code}/{tax_year}", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new GetCellHistory(FeatureHttp.Client(c), FeatureHttp.Path(c, "program_code"), FeatureHttp.PathInteger(c, "tax_year")))));
        endpoints.MapPost("/api/claims", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new RecordClaim(FeatureHttp.Body(c), Actor(c, "decided_by")), 201)));
        endpoints.MapPost("/api/claims/cell/{client_id}/{program_code}/{tax_year}/transition", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new TransitionClaim(FeatureHttp.Client(c), FeatureHttp.Path(c, "program_code"), FeatureHttp.PathInteger(c, "tax_year"),
                FeatureHttp.Body(c), Actor(c, "decided_by")))));
        endpoints.MapPut("/api/claims/engagement", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => Engagement(c))));
        endpoints.MapGet("/api/claims/lifecycle", (Delegate)((HttpContext c) => FeatureHttp.Send(c, () => new GetLifecycle())));
    }

    internal static string Actor(HttpContext context, string field, string fallback = "anonymous") =>
        FeatureHttp.Actor(context, FeatureValues.Text(FeatureHttp.Body(context), field), fallback);

    private static SetEngagement Engagement(HttpContext context)
    {
        var b = FeatureHttp.Body(context);
        return new SetEngagement(FeatureValues.Whole(b, "client_id"), FeatureValues.Text(b, "program_code")!,
            FeatureValues.Text(b, "scope")!, FeatureValues.Text(b, "note"), FeatureHttp.Actor(context));
    }

    private static long[] Years(HttpContext context) => context.Request.Query.TryGetValue("tax_years", out var years) && years.Count > 0
        ? years.Select(y => long.Parse(y!, System.Globalization.CultureInfo.InvariantCulture)).ToArray()
        : FeatureHttp.Year(context, "tax_year") is { } year && year != 0 ? [year] : [];
}
