using TaxCredit.Application.Features.ClaimsArtifactsRules;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Rules;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Api.Endpoints.ClaimsArtifactsRules;

/// <summary>Exposes captured provenance and honest retrieval refusals through ordinary mediator dispatch.</summary>
public sealed class RuleEndpoints : IEndpointGroup
{
    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/api/rules", (Delegate)((HttpContext c) => FeatureHttp.Send(c, () => new ListRules())));
        endpoints.MapPost("/api/rules/{code}/verify", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new VerifyRules(FeatureHttp.Path(c, "code"), ClaimEndpoints.Actor(c, "verified_by"), FeatureValues.Text(FeatureHttp.Body(c), "note")))));
        endpoints.MapGet("/api/rules/ingested/{state}", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new GetIngestedRules(FeatureHttp.Path(c, "state"), FeatureHttp.Year(c, "tax_year")))));
        endpoints.MapGet("/api/rules/ingested/{state}/refresh", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new RefreshRules(FeatureHttp.Path(c, "state"), FeatureHttp.Query(c, "live", "false")!.ToLowerInvariant() is "true" or "1" or "yes" or "on",
                FeatureHttp.Actor(c)))));
        endpoints.MapGet("/api/rules/ingested/{state}/proposals", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new GetRuleProposals(FeatureHttp.Path(c, "state"), FeatureHttp.Year(c, "tax_year") ?? 2025))));
        endpoints.MapPost("/api/rules/ingested/{state}/apply", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new ApplyRules(FeatureHttp.Path(c, "state"), FeatureValues.Whole(FeatureHttp.Body(c), "tax_year"),
                ClaimEndpoints.Actor(c, "confirmed_by", "Tax practitioner"), FeatureValues.Text(FeatureHttp.Body(c), "note")))));
        endpoints.MapGet("/api/rules/ingested/{state}/changelog", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new GetRuleChangelog(FeatureHttp.Path(c, "state")))));
    }
}

internal sealed class RuleFileMetadata(IRulePackSource source) : IRuleFileMetadata
{
    public DateTimeOffset ModifiedAt(string fileName)
    {
        if (!source.IsFile(fileName) || Path.GetFileName(fileName) != fileName) { throw new FileNotFoundException("Known rule file is missing."); }
        return new DateTimeOffset(File.GetLastWriteTimeUtc(Path.Combine(source.RulesDirectory, fileName)));
    }
}
