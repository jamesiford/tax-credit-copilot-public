using TaxCredit.Api.Hosting;
using TaxCredit.Application.Features.DraftsRuns;

namespace TaxCredit.Api.Endpoints.DraftsRuns;

/// <summary>Feature-owned registrations are discovered before host construction.</summary>
public sealed class DraftsRunsModule : IFeatureModule
{
    /// <inheritdoc />
    public void ConfigureServices(IServiceCollection services, IConfiguration configuration)
    {
        services.AddScoped<BatchPlanner>();
        services.AddScoped<BatchAccess>();
    }
}
