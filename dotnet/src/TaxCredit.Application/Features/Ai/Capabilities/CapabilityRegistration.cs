using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Application.Features.Ai.Capabilities.Bindings;
using TaxCredit.Application.Features.Ai.Chat;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Claims;

namespace TaxCredit.Application.Features.Ai.Capabilities;

/// <summary>Per-host limits, never request-selected execution budgets.</summary>
public sealed class CapabilityOptions
{
    /// <summary>Only the wait is bounded; a timed-out commit may still finish.</summary>
    public TimeSpan Timeout { get; set; } = TimeSpan.FromSeconds(25);
    /// <summary>Non-writers' aggregate groups smaller than this are suppressed.</summary>
    public int MinimumGroupSize { get; set; } = 5;
    /// <summary>Expiring confirmations use the host clock rather than client timestamps.</summary>
    public TimeSpan ConfirmationLifetime { get; set; } = TimeSpan.FromMinutes(10);
}

/// <summary>The parent feature module calls this before building the host.</summary>
public static class CapabilityRegistration
{
    /// <summary>Missing siblings fail explicitly; an integration may replace either bridge with its actual application services.</summary>
    public static IServiceCollection AddCapabilityServices(this IServiceCollection services, Action<CapabilityOptions>? configure = null)
    {
        var options = new CapabilityOptions();
        configure?.Invoke(options);
        if (options.Timeout < TimeSpan.FromSeconds(1) || options.Timeout > TimeSpan.FromSeconds(600) ||
            options.MinimumGroupSize < 2 || options.ConfirmationLifetime <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(configure), "Capability limits are outside their supported bounds.");
        }
        services.TryAddSingleton(options);
        services.TryAddSingleton(TimeProvider.System);
        services.TryAddSingleton<IIdSource, CapabilityRandomSources>();
        services.TryAddSingleton<ISecretSource, CapabilityRandomSources>();
        services.TryAddSingleton<CapabilityCommitLocks>();
        // DI otherwise selects the injectable declaration constructor with an empty IEnumerable.
        services.TryAddSingleton(_ => new CapabilityCatalog());
        services.TryAddSingleton<ICapabilityReadBridge>(_ => new MissingCapabilityReadBridge());
        services.TryAddSingleton<ICapabilityWriteBridge>(_ => new MissingCapabilityWriteBridge());
        services.TryAddScoped<AiClientBook>();
        services.TryAddScoped(provider => new CapabilityDirectReads(provider.GetRequiredService<IClaimRepository>(),
            provider.GetRequiredService<AiClientBook>(), provider.GetRequiredService<IGoldReadPort>(),
            provider.GetRequiredService<IClientAuthorizer>()));
        services.TryAddScoped(provider => new CapabilityData(provider.GetRequiredService<IGoldDataQueryPort>(),
            provider.GetRequiredService<IGoldReadPort>(), provider.GetRequiredService<IWriterEntitlement>(),
            provider.GetRequiredService<CapabilityOptions>(), provider.GetRequiredService<TimeProvider>()));
        services.TryAddScoped(provider => new CapabilityWrites(provider.GetRequiredService<IChannelStateRepository>(),
            provider.GetRequiredService<IChannelAuditRepository>(), provider.GetRequiredService<IWriterPolicy>(),
            provider.GetRequiredService<ICapabilityWriteBridge>(), provider.GetRequiredService<CapabilityOptions>(),
            provider.GetRequiredService<TimeProvider>(), provider.GetRequiredService<IIdSource>(),
            provider.GetRequiredService<ISecretSource>(), provider.GetRequiredService<CapabilityCommitLocks>()));
        services.TryAddScoped(provider => new CapabilityDispatcher(provider.GetRequiredService<CapabilityDirectReads>(),
            provider.GetRequiredService<CapabilityData>(), provider.GetRequiredService<CapabilityWrites>(),
            provider.GetRequiredService<ICapabilityReadBridge>(), provider.GetRequiredService<IWriterEntitlement>(),
            provider.GetRequiredService<CapabilityCatalog>()));
        services.TryAddScoped(service => new CapabilityService(service.GetRequiredService<CapabilityCatalog>(),
            service.GetRequiredService<Ports.Auth.IApiPrincipalAccessor>(), service.GetRequiredService<Ports.Auth.IClientAuthorizer>(),
            service.GetRequiredService<CapabilityDispatcher>(), service.GetRequiredService<CapabilityOptions>(),
            service.GetService<Ports.Ai.IAiTelemetry>()));
        return services;
    }
}
