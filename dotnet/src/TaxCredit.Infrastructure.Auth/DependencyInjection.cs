using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth;

/// <summary>Registers services only; skeleton owns HTTP framing, ambient scope and route metadata.</summary>
public static class DependencyInjection
{
    /// <summary>Injected signing keys take precedence; production retrieval uses the supplied safe HttpClient.</summary>
    public static IServiceCollection AddTaxCreditAuth(this IServiceCollection services, AuthConfiguration configuration,
        HttpClient jwksClient, ApiRateLimitOptions? limits = null)
    {
        configuration.Validate();
        limits ??= new ApiRateLimitOptions();
        limits.Validate();
        if (services.LastOrDefault(d => d.ServiceType == typeof(AuthConfiguration))?.ImplementationInstance is AuthConfiguration prior
            && prior != configuration)
        {
            throw new ArgumentException("Authentication configuration cannot change beneath cached trust services.", nameof(configuration));
        }
        if (services.LastOrDefault(d => d.ServiceType == typeof(ApiRateLimitOptions))?.ImplementationInstance is ApiRateLimitOptions priorLimits
            && priorLimits != limits)
        {
            throw new ArgumentException("Rate configuration cannot change beneath existing buckets.", nameof(limits));
        }
        services.TryAddSingleton(configuration);
        services.TryAddSingleton(limits);
        services.TryAddSingleton(TimeProvider.System);
        services.TryAddSingleton<IAuthEvents, AuthEvents>();
        services.TryAddSingleton<IJwksTransport>(new HttpJwksTransport(jwksClient, configuration));
        services.TryAddSingleton<ISigningKeyProvider, CachedJwksProvider>();
        services.TryAddSingleton<IApiTokenValidator, EntraTokenValidator>();
        services.TryAddSingleton<IClientAuthorizer, AllClientsAuthorizer>();
        services.TryAddSingleton<IApiPrincipalAccessor, ApiPrincipalAccessor>();
        services.TryAddSingleton<IWriterEntitlement, DenyWriters>();
        services.TryAddSingleton(p => new WriterPolicy(p.GetRequiredService<IWriterEntitlement>(), configuration.EnforceWriterForUsers));
        services.TryAddSingleton<IWriterPolicy>(p => p.GetRequiredService<WriterPolicy>());
        services.TryAddSingleton<IApiRateLimiter>(p => new ApiRateLimiter(p.GetRequiredService<ApiRateLimitOptions>(), p.GetRequiredService<TimeProvider>()));
        services.TryAddSingleton<ApiTrustService>();
        services.TryAddSingleton<IApiTrustService>(p => p.GetRequiredService<ApiTrustService>());
        return services;
    }

    /// <summary>Selects writer sources once; all repository checks have fail-closed independent boundaries.</summary>
    public static IServiceCollection AddTaxCreditWriters(this IServiceCollection services,
        string source, IWriterEntitlement allowList, IGroupMembershipProvider? groups = null, string? groupId = null)
    {
        if (source is not ("allowlist" or "entra_group" or "either"))
        {
            throw new ArgumentException("Unknown CHANNEL_WRITER_SOURCE.", nameof(source));
        }
        if (source != "allowlist" && (groups is null || !Guid.TryParse(groupId, out _)))
        {
            throw new ArgumentException("Group writer sources require a provider and group GUID.", nameof(groupId));
        }
        if (source != "allowlist")
        {
            services.AddSingleton(p => new EntraGroupEntitlement(groupId!, groups!, p.GetRequiredService<IAuthEvents>(), p.GetRequiredService<TimeProvider>()));
        }
        services.Replace(ServiceDescriptor.Singleton<IWriterEntitlement>(p =>
        {
            var events = p.GetRequiredService<IAuthEvents>();
            if (source == "allowlist") { return new DenyOnFailure(allowList, "allowlist", events); }
            var group = p.GetRequiredService<EntraGroupEntitlement>();
            return source == "entra_group" ? group :
                new EitherEntitlement([("allowlist", allowList), ("entra_group", group)], events);
        }));
        return services;
    }

    private sealed class DenyWriters : IWriterEntitlement
    {
        public ValueTask<bool> IsWriterAsync(string userOid, CancellationToken cancellationToken = default) => ValueTask.FromResult(false);
    }
}
