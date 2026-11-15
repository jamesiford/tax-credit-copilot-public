using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Pipeline;

namespace TaxCredit.Infrastructure;

/// <summary>Binds the adapters to the ports the application layer declares.</summary>
public static class DependencyInjection
{
    /// <summary>Registers the infrastructure adapters.</summary>
    /// <param name="services">The container.</param>
    /// <returns>The same container, for chaining.</returns>
    public static IServiceCollection AddInfrastructure(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.AddSingleton<InMemoryAuditLog>();
        services.AddSingleton<IAuditLog>(sp => sp.GetRequiredService<InMemoryAuditLog>());
        return services;
    }
}
