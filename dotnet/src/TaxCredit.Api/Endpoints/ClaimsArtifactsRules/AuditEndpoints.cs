using TaxCredit.Application.Features.ClaimsArtifactsRules.Audit;

namespace TaxCredit.Api.Endpoints.ClaimsArtifactsRules;

/// <summary>The person-only audit read remains separate from gateway execution.</summary>
public sealed class AuditEndpoints : IEndpointGroup
{
    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints) =>
        endpoints.MapGet("/api/audit/channel", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new GetChannelAudit(FeatureHttp.Query(c, "user_oid")!, FeatureHttp.Query(c, "since"), FeatureHttp.Query(c, "until"),
                FeatureHttp.Query(c, "tool"), checked((int)(FeatureHttp.Year(c, "limit") ?? 200)), FeatureHttp.Principal(c)))));
}
