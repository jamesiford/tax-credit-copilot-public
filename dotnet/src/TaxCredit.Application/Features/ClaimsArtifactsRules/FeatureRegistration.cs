using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Packages;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Qc;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Rules;
using TaxCredit.Application.Rules;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules;

/// <summary>Feature collaborators join the ordinary host graph before Build.</summary>
public static class FeatureRegistration
{
    /// <summary>No second provider, byte store or repository is created by this feature.</summary>
    public static IServiceCollection AddClaimsArtifactsRules(this IServiceCollection services)
    {
        services.AddPackValidator();
        services.AddScoped<ClaimPackageBuilder>();
        services.AddScoped<RuleCatalogue>();
        services.AddScoped<CapturedRules>();
        services.AddScoped<IIngestionQcDecisions, IngestionQcDecisions>();
        return services;
    }
}
