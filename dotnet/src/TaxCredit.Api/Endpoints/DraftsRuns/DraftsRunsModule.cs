using TaxCredit.Api.Hosting;
using TaxCredit.Application.Features.DraftsRuns;
using TaxCredit.Application.Messaging;

namespace TaxCredit.Api.Endpoints.DraftsRuns;

/// <summary>Feature-owned registrations are discovered before host construction.</summary>
public sealed class DraftsRunsModule : IFeatureModule
{
    /// <inheritdoc />
    public void ConfigureServices(IServiceCollection services, IConfiguration configuration)
    {
        services.AddScoped<BatchPlanner>();
        services.AddScoped<BatchSelection>();
        services.AddScoped<BatchAccess>();
        services.AddScoped<DraftLifecycle>();
        services.AddScoped<DraftValidation>();
        services.AddScoped<DraftCustomerData>();
        services.AddScoped<SyntheticPreviewSample>();
        services.AddScoped<TaxCredit.Domain.Programs.PackValidator>();
        // Authorization and source adapters must both use the current request's configuration.
        services.AddScoped<IMediator, Mediator>();
    }
}
