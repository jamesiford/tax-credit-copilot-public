using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Infrastructure.Auth;

namespace TaxCredit.ServiceDefaults.Hosting;

internal static class RuntimeTrustRegistration
{
    internal static void ValidateDynamic(RuntimeConfiguration settings)
    {
        _ = Configuration(settings);
        ApiRateLimitOptions.Parse(settings.Get("RATE_LIMIT_PER_MINUTE"));
        if (settings.Get("DATA_SOURCE") is not ("csv" or "lakehouse" or "flex")
            || settings.Get("CHANNEL_WRITER_SOURCE") is not ("allowlist" or "entra_group" or "either"))
        {
            throw new InvalidOperationException("Unsupported runtime source or writer configuration.");
        }
        if (settings.Get("CHANNEL_WRITER_SOURCE") != "allowlist" && !Guid.TryParse(settings.Get("CHANNEL_WRITER_GROUP_ID"), out _))
        {
            throw new InvalidOperationException("Group writer policy requires CHANNEL_WRITER_GROUP_ID.");
        }
    }

    internal static void AddRuntimeTrust(this IServiceCollection services, RuntimeConfiguration settings)
    {
        ValidateDynamic(settings);
        var initial = Configuration(settings);
        var clients = new RuntimeAuthClients();
        services.AddSingleton(_ => clients);
        services.AddTaxCreditAuth(initial, clients.Jwks);
        services.TryAddSingleton<IAuthAccessTokenProvider, RuntimeGraphTokens>();
        services.TryAddSingleton<IGroupMembershipProvider>(p => new GraphGroupMembershipProvider(clients.Graph,
            p.GetRequiredService<IAuthAccessTokenProvider>(), p.GetRequiredService<TimeProvider>()));
        foreach (var type in new[] { typeof(AuthConfiguration), typeof(IApiTokenValidator), typeof(ApiTrustService),
            typeof(IApiTrustService), typeof(IClientAuthorizer), typeof(IWriterPolicy), typeof(WriterPolicy), typeof(IWriterEntitlement) })
        {
            services.RemoveAll(type);
        }
        services.AddScoped(_ => Configuration(settings));
        services.AddScoped<IApiTokenValidator>(p =>
        {
            _ = p.GetRequiredService<RuntimeAuthClients>();
            return ActivatorUtilities.CreateInstance<EntraTokenValidator>(p);
        });
        services.AddScoped<ApiTrustService>();
        services.AddScoped<IApiTrustService>(p => p.GetRequiredService<ApiTrustService>());
        services.AddScoped<IClientAuthorizer>(_ => Clients(settings));
        services.AddSingleton<RuntimeWriters>();
        services.AddSingleton<IWriterEntitlement>(p => p.GetRequiredService<RuntimeWriters>());
        services.AddScoped<IWriterPolicy>(p => new WriterPolicy(p.GetRequiredService<IWriterEntitlement>(),
            RuntimeRegistration.Flag(settings, "CHANNEL_ENFORCE_WRITER_FOR_USERS")));
        services.AddScoped<TaxCredit.Application.Pipeline.IAuthorizer, RuntimeAuthorizer>();
        services.AddSingleton<RuntimeLimits>();
        services.AddSingleton<IApiRateLimiter>(p => p.GetRequiredService<RuntimeLimits>());
        if (settings.Get("CONTRACT_HOOKS") == "1")
        {
            services.AddSingleton<ISigningKeyProvider, ContractKeys>();
        }
    }

    private static AuthConfiguration Configuration(RuntimeConfiguration settings)
    {
        var fixture = settings.Get("CONTRACT_HOOKS") == "1";
        var config = new AuthConfiguration
        {
            Mode = settings.Get("AUTH_MODE") ?? "entra",
            Environment = settings.Get("ENVIRONMENT"),
            TenantId = settings.Get("AUTH_TENANT_ID") ?? (fixture ? SyntheticPolicy.Tenant : ""),
            ApiAudience = settings.Get("API_AUDIENCE") ?? (fixture ? "api://" + SyntheticPolicy.Audience : ""),
            EnforceWriterForUsers = RuntimeRegistration.Flag(settings, "CHANNEL_ENFORCE_WRITER_FOR_USERS"),
        };
        config.Validate();
        return config;
    }

    private static IClientAuthorizer Clients(RuntimeConfiguration settings)
    {
        if (settings.Get("ENVIRONMENT") == "local" && settings.Get("AUTH_MODE") == "none") { return new LocalOrDeny(true); }
        if (settings.Get("CLIENT_ALLOWLIST") is { Length: > 0 } text)
        {
            var map = JsonSerializer.Deserialize<Dictionary<string, long[]>>(text)
                ?? throw new InvalidOperationException("CLIENT_ALLOWLIST must be an object.");
            return new AllowListClientAuthorizer(map.ToDictionary(p => p.Key, p => (IEnumerable<long>)p.Value, StringComparer.Ordinal));
        }

        if (settings.Get("CONTRACT_HOOKS") == "1") { return SyntheticPolicy.Clients(); }
        return new LocalOrDeny(settings.Get("ENVIRONMENT") == "local" && settings.Get("AUTH_MODE") == "none");
    }

    private sealed class LocalOrDeny(bool local) : IClientAuthorizer
    {
        public ValueTask<bool> IsAuthorizedAsync(ApiPrincipal principal, long clientId, CancellationToken cancellationToken = default) =>
            ValueTask.FromResult(local && !principal.Authenticated);
    }

}

internal sealed class RepositoryWriters(IChannelStateRepository repository) : IWriterEntitlement
{
    public ValueTask<bool> IsWriterAsync(string userOid, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return ValueTask.FromResult(repository.IsWriter(userOid));
    }
}

internal sealed class ContractKeys(IContractSigningKey key) : ISigningKeyProvider
{
    public ValueTask<RSAParameters> GetKeyAsync(string keyId, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        using var rsa = RSA.Create();
        rsa.ImportSubjectPublicKeyInfo(key.ExportPublicKey(), out _);
        return ValueTask.FromResult(rsa.ExportParameters(false));
    }
    public void Reset() { }
}
