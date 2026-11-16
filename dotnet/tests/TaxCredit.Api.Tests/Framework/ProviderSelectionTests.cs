using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Api.Hosting;
using TaxCredit.Application;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Application.Ports.Ai.Artifacts;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Infrastructure;
using TaxCredit.Infrastructure.Ai.Artifacts;
using TaxCredit.Infrastructure.Ai.Runtime;
using TaxCredit.Infrastructure.Persistence.Sql;
using TaxCredit.Infrastructure.Sources;
using TaxCredit.Infrastructure.Sources.Sql;
using TaxCredit.ServiceDefaults.Hosting;

namespace TaxCredit.Api.Tests.Framework;

public sealed class ProviderSelectionTests
{
    [Fact]
    public async Task Native_SQL_Blob_and_group_policy_select_real_adapters_without_opening_a_live_connection()
    {
        var configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["TCC_REPOSITORY_ROOT"] = Corpus.Root,
            ["ENVIRONMENT"] = "local",
            ["AUTH_MODE"] = "entra",
            ["TCC_CONTRACT_HOOKS"] = "0",
            ["TCC_PERSISTENCE_PROVIDER"] = "warehouse",
            ["FABRIC_SQL_SERVER"] = "synthetic.invalid",
            ["FABRIC_SQL_DATABASE"] = "synthetic",
            ["SOURCE_SQL_SERVER"] = "synthetic.invalid",
            ["SOURCE_SQL_DATABASE"] = "synthetic",
            ["DATA_SOURCE"] = "lakehouse",
            ["ARTIFACT_STORE"] = "blob",
            ["ARTIFACT_BLOB_ACCOUNT_URL"] = "https://synthetic.invalid/",
            ["CHANNEL_WRITER_SOURCE"] = "entra_group",
            ["CHANNEL_WRITER_GROUP_ID"] = "00000000-0000-0000-0000-000000000001",
            ["AUTH_TENANT_ID"] = "00000000-0000-0000-0000-0000000000aa",
            ["API_AUDIENCE"] = "api://11111111-2222-3333-4444-555555555555",
            ["CHANNEL_ENFORCE_WRITER_FOR_USERS"] = "true",
            ["FOUNDRY_PROJECT_ENDPOINT"] = "https://synthetic.invalid/",
        }).Build();
        var services = new ServiceCollection();
        services.AddApplication().AddInfrastructure().AddTaxCreditRuntime(configuration);
        new FeatureDiscovery(configuration).ConfigureServices(services, configuration);
        var groups = new FakeGroups();
        services.AddSingleton<IGroupMembershipProvider>(groups);
        using var provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true, ValidateOnBuild = true });
        using var scope = provider.CreateScope();
        Assert.IsType<SqlServerDialect>(scope.ServiceProvider.GetRequiredService<PersistenceDatabase>().Dialect);
        Assert.IsType<SqlAnalyticsTransport>(scope.ServiceProvider.GetRequiredService<IAnalyticsTransport>());
        Assert.IsType<SqlClientSource>(scope.ServiceProvider.GetRequiredService<IClientPayrollSource>());
        Assert.IsType<BlobArtifactByteStore>(scope.ServiceProvider.GetRequiredService<IArtifactByteStore>());
        var principal = new ApiPrincipal(Oid: RuntimeRequestsOid, Authenticated: true);
        await scope.ServiceProvider.GetRequiredService<IWriterPolicy>().CheckAsync(principal, principal.Actor, true);
        Assert.Equal(1, groups.Calls);
        Assert.All(provider.GetRequiredService<ModelRouter>().Statuses(), status => Assert.Equal(ProviderState.Unavailable, status.State));
    }

    private const string RuntimeRequestsOid = "00000000-0000-0000-0000-0000000000a2";

    private sealed class FakeGroups : IGroupMembershipProvider
    {
        internal int Calls { get; private set; }
        public ValueTask<bool> IsMemberAsync(string userOid, string groupId, CancellationToken cancellationToken = default)
        {
            Calls++;
            return ValueTask.FromResult(true);
        }
    }
}
