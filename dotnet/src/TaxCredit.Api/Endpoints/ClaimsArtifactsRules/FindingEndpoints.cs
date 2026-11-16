using TaxCredit.Application.Features.ClaimsArtifactsRules;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Findings;

namespace TaxCredit.Api.Endpoints.ClaimsArtifactsRules;

/// <summary>Keeps finding lifecycle independent of ingestion-QC and payroll execution.</summary>
public sealed class FindingEndpoints : IEndpointGroup
{
    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/api/findings/{client_id}/{tax_year}", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new ListFindings(FeatureHttp.Client(c), FeatureHttp.PathInteger(c, "tax_year"),
                FeatureHttp.Query(c, "state"), FeatureHttp.Query(c, "program_code")))));
        endpoints.MapPost("/api/findings/{finding_id}/resolve", (Delegate)((HttpContext c) => FeatureHttp.Send(c, () => Resolve(c))));
        endpoints.MapPost("/api/findings/{finding_id}/reopen", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new ReopenFinding(FeatureHttp.Path(c, "finding_id"), FeatureValues.Whole(FeatureHttp.Body(c), "client_id"),
                ClaimEndpoints.Actor(c, "decided_by")))));
        endpoints.MapGet("/api/findings/{client_id}/{finding_id}/history", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new GetFindingHistory(FeatureHttp.Client(c), FeatureHttp.Path(c, "finding_id")))));
    }

    private static ResolveFinding Resolve(HttpContext context)
    {
        var b = FeatureHttp.Body(context);
        return new ResolveFinding(FeatureHttp.Path(context, "finding_id"), FeatureValues.Whole(b, "client_id"),
            FeatureValues.Whole(b, "tax_year"), FeatureValues.Text(b, "resolution")!, FeatureValues.Text(b, "keep_worksite"),
            FeatureValues.Text(b, "note"), ClaimEndpoints.Actor(context, "decided_by"));
    }
}
