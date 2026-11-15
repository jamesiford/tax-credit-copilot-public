using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Pipeline;
using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure.Rules;

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

    /// <summary>
    /// Binds the rules-folder adapters to the Domain's ports: <see cref="IRulePackSource"/> over <paramref name="options"/>, and, when an ingested-config
    /// folder is configured, the captured ingestion hook, and the JSON Schema step of pack validation (<see cref="IJsonSchemaValidator"/>). The folder is configuration; no rule file is copied.
    /// </summary>
    /// <param name="services">The container.</param>
    /// <param name="options">Where the rules folder (and optionally the captured ingestion configs) are.</param>
    /// <returns>The same container, for chaining.</returns>
    public static IServiceCollection AddRulePackSource(this IServiceCollection services, RulePackOptions options)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(options);
        services.AddSingleton<IRulePackSource>(new JsonRulePackSource(options));
        services.AddSingleton<IJsonSchemaValidator>(_ => JsonSchemaPackValidator.FromOptions(options));
        if (options.IngestedConfigDirectory is { Length: > 0 } ingested)
        {
            services.AddSingleton<IIngestedConfigFiles>(new JsonIngestedConfigFiles(ingested));
            services.AddSingleton<IIngestedOneZeroSource>(sp => new CapturedIngestion(sp.GetRequiredService<IIngestedConfigFiles>()));
        }

        return services;
    }
}
