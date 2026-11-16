using TaxCredit.Api.Hosting;
using TaxCredit.Application.Features.ReadsCalc.Calculations;
using TaxCredit.Application.Features.ReadsCalc.Ingestion;
using TaxCredit.Application.Features.ReadsCalc.Portfolio;
using TaxCredit.Application.Features.ReadsCalc.Scope;
using TaxCredit.Application.Features.ReadsCalc.Stored;
using TaxCredit.Domain.Canonical;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Api.Endpoints.ReadsCalc;

/// <summary>Registers inward views during normal host discovery, not from a test-only composition root.</summary>
public sealed class ReadsCalcModule : IFeatureModule
{
    /// <inheritdoc />
    public void ConfigureServices(IServiceCollection services, IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.AddScoped<StoredEligibility>();
        services.AddScoped<ReadStatutes>();
        services.AddScoped<Func<ClientRunResolver>>(provider => provider.GetRequiredService<ClientRunResolver>);
        services.AddScoped<StoredMatrix>();
        services.AddScoped<StoredUnits>();
        services.AddScoped<StoredEmployees>();
        services.AddScoped<ProximityViews>();
        services.AddScoped<RestOfYearReading>();
        services.AddScoped<ScopeViews>();
        services.AddScoped<QcAnnotations>();
        services.AddScoped<IngestionViews>();
        services.AddScoped<ReadsCalculationViews>();
        services.AddScoped<IIngestedConfigSource, IngestedPayCodes>();
        services.AddScoped<CanonicalMapper>();
        services.AddReadsCalcPortfolio();
    }
}
