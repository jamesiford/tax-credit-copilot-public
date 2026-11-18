using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Hosting;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Infrastructure.Ai.Runtime;
using TaxCredit.Infrastructure.Auth;
using TaxCredit.Infrastructure.Persistence;
using TaxCredit.Infrastructure.Persistence.Operational;

namespace TaxCredit.ServiceDefaults.Hosting;

/// <summary>Called while the host's work gate excludes product requests and scheduling; no provider is rebuilt or mutated.</summary>
public sealed class RuntimeContractWork(IServiceProvider services, RuntimeConfiguration settings, RuntimeSources sources) : IContractWork
{
    /// <inheritdoc />
    public ValueTask<int> Drain(CancellationToken cancellationToken) =>
        services.GetRequiredService<RunWorkExecutor>().Drain(cancellationToken);

    /// <inheritdoc />
    public ValueTask Reset(string profile, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (settings.Get("CONTRACT_HOOKS") != "1") { throw new InvalidOperationException("Contract reset is disabled."); }
        var seed = profile switch
        {
            "P2" => "P2",
            "P1" or "G1" or "G1L" => "P1",
            _ => throw new ArgumentException("Unknown contract profile.", nameof(profile)),
        };
        var importer = services.GetRequiredService<SeedImporter>();
        var loaded = importer.Load(seed);
        var state = loaded.SourceState ?? throw new InvalidDataException("Contract reset requires exported deterministic source state.");
        if (state.UuidDraws < importer.DeterministicIdentityHighWater())
        {
            throw new InvalidDataException("Exported deterministic source state precedes stored identifiers.");
        }
        OperationalSchema.Initialize(services.GetRequiredService<Infrastructure.Persistence.Sql.PersistenceDatabase>());
        settings.Reset();
        settings.Apply(new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["DATA_SOURCE"] = seed == "P2" ? "lakehouse" : "csv",
        }, []);
        sources.Reset(state.UuidDraws, state.SecretDraws);
        services.GetRequiredService<RunWorkGate>().Reset();
        services.GetRequiredService<ArtifactGenerations>().Reset();
        services.GetRequiredService<IChannelStateRepository>().Grant(new WriterGrant(SyntheticPolicy.Writer, "Fixture writer",
            "writer", "contract-fixture", RuntimeCalculationRegistration.Instant(sources)));
        return EnvironmentChanged(cancellationToken);
    }

    /// <inheritdoc />
    public ValueTask EnvironmentChanged(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        RuntimeTrustRegistration.ValidateDynamic(settings);
        services.GetRequiredService<SeedAnalytics>().Reset();
        services.GetService<TaxCredit.Infrastructure.Sources.Cache.ClientProjectionCache>()?.Clear();
        services.GetRequiredService<RuntimeLimits>().Reset();
        services.GetRequiredService<RuntimeWriters>().Reset();
        services.GetRequiredService<ITokenBudget>().Reset();
        services.GetRequiredService<ModelRouter>().Reset();
        if (services.GetRequiredService<IAuthEvents>() is AuthEvents events) { events.Reset(); }
        if (services.GetService<IGroupMembershipProvider>() is GraphGroupMembershipProvider groups) { groups.Reset(); }
        services.GetRequiredService<ISigningKeyProvider>().Reset();
        services.GetRequiredService<RuntimeStatus>().Settle();
        return ValueTask.CompletedTask;
    }
}
