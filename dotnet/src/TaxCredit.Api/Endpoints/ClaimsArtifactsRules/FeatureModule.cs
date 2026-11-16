using TaxCredit.Api.Hosting;
using TaxCredit.Application.Features.ClaimsArtifactsRules;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Rules;

namespace TaxCredit.Api.Endpoints.ClaimsArtifactsRules;

/// <summary>Discovered registration replaces only this feature's exact route stubs.</summary>
public sealed class FeatureModule : IFeatureModule
{
    /// <inheritdoc />
    public void ConfigureServices(IServiceCollection services, IConfiguration configuration)
    {
        services.AddClaimsArtifactsRules();
        services.AddScoped<IRuleFileMetadata, RuleFileMetadata>();
    }
}
