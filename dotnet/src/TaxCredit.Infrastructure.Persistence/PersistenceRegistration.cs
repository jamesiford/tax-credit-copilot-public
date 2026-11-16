using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;
using TaxCredit.Domain.Warehouse;
using TaxCredit.Infrastructure.Persistence.GoldRead;
using TaxCredit.Infrastructure.Persistence.Operational;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence;

/// <summary>One configured destination binds every store, preventing disconnected Gold/claims/manifests.</summary>
public static class PersistenceRegistration
{
    /// <summary>Registers persistence; deployed schema administration remains the Python operator's responsibility.</summary>
    public static IServiceCollection AddPersistence(this IServiceCollection services, PersistenceDatabase database,
        string repositoryRoot, string seedRoot, Func<long, bool>? authorizeEmployeeQuery = null)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(database);
        ArgumentException.ThrowIfNullOrWhiteSpace(repositoryRoot);
        ArgumentException.ThrowIfNullOrWhiteSpace(seedRoot);
        if (services.Any(s => s.ServiceType == typeof(PersistenceDatabase)))
        {
            throw new InvalidOperationException("Persistence already has a configured destination.");
        }

        if (database.Dialect is SqliteDialect)
        {
            PersistenceSchema.Initialize(database, repositoryRoot);
            OperationalSchema.Initialize(database);
        }

        services.AddSingleton(database);
        services.AddSingleton<GoldWriter>(s => new GoldWriter(s.GetRequiredService<PersistenceDatabase>(), repositoryRoot));
        services.AddSingleton<IGoldWriter>(s => s.GetRequiredService<GoldWriter>());
        services.AddSingleton<IGoldReadPort, GoldReader>();
        services.AddSingleton<IGoldDataQueryPort>(s =>
            new GoldDataQuery(s.GetRequiredService<PersistenceDatabase>(), authorizeEmployeeQuery));
        services.AddSingleton<IPersistenceUnitOfWork, PersistenceUnitOfWork>();
        services.AddTransient<IClientCalculationRunner, PersistedClientCalculation>();
        services.AddSingleton<SeedImporter>(s => new SeedImporter(s.GetRequiredService<PersistenceDatabase>(), seedRoot, repositoryRoot));
        services.AddSingleton<ISeedData, SourceSeedData>();
        RegisterOperations(services);
        return services;
    }

    private static void RegisterOperations(IServiceCollection services)
    {
        services.AddSingleton<ClaimRepository>();
        services.AddSingleton<IClaimRepository>(s => s.GetRequiredService<ClaimRepository>());
        services.AddSingleton<IClaimSink>(s => s.GetRequiredService<ClaimRepository>());
        services.AddSingleton<ManualOverrideRepository>();
        services.AddSingleton<IManualOverrideRepository>(s => s.GetRequiredService<ManualOverrideRepository>());
        services.AddSingleton<IBaseYearOverrides>(s => s.GetRequiredService<ManualOverrideRepository>());
        services.AddSingleton<IRunManifestRepository, RunManifestRepository>();
        services.AddSingleton<IProgramDraftRepository, ProgramDraftRepository>();
        services.AddSingleton<IRunBatchRepository, RunBatchRepository>();
        services.AddSingleton<IFindingRepository, FindingRepository>();
        services.AddSingleton<LookupStore>();
        services.AddSingleton<ILookupStore>(s => s.GetRequiredService<LookupStore>());
        services.AddSingleton<ILookupReader>(s => s.GetRequiredService<LookupStore>());
        services.AddSingleton<IArtifactRepository, ArtifactRepository>();
        services.AddSingleton<IChannelStateRepository, ChannelStateRepository>();
        services.AddSingleton<IChannelAuditRepository, ChannelAuditRepository>();
    }
}
