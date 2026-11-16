using TaxCredit.Application.Features.ClaimsArtifactsRules;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Claims;

namespace TaxCredit.Api.Endpoints.ClaimsArtifactsRules;

/// <summary>Separates an assessment write from the stored-only situation read.</summary>
public sealed class AssessmentEndpoints : IEndpointGroup
{
    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints)
    {
        endpoints.MapPost("/api/claims/assess", (Delegate)((HttpContext c) => FeatureHttp.Send(c, () => Command(c))));
        endpoints.MapGet("/api/v2/clients/{client_id}/situation", (Delegate)((HttpContext c) => FeatureHttp.Send(c,
            () => new GetClientSituation(FeatureHttp.Client(c), FeatureHttp.Year(c, "year")))));
    }

    private static AssessClient Command(HttpContext context)
    {
        var b = FeatureHttp.Body(context);
        var years = b.TryGetProperty("tax_years", out var y) && y.ValueKind != System.Text.Json.JsonValueKind.Null
            ? y.EnumerateArray().Select(v => v.ValueKind == System.Text.Json.JsonValueKind.String
                ? long.Parse(v.GetString()!, System.Globalization.CultureInfo.InvariantCulture) : v.GetInt64()).ToArray() : [];
        return new AssessClient(FeatureValues.Whole(b, "client_id"), FeatureValues.Text(b, "program_code"), years,
            ClaimEndpoints.Actor(context, "assessed_by", "engine"));
    }
}
