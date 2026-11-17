using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;
using TaxCredit.Domain.Warehouse;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests;

public sealed class PersistenceRegistrationTests
{
    [Fact]
    [Trait("Category", "heavy")]
    public void Registration_connects_reads_writes_seed_and_paired_contracts_to_one_destination()
    {
        using var fixture = new PersistenceFixture(false);
        var services = new ServiceCollection();
        services.AddPersistence(fixture.Database, PersistenceFixture.Root,
            Path.Combine(PersistenceFixture.Root, "contract", "seed"));
        using var provider = services.BuildServiceProvider();
        Assert.Same(fixture.Database, provider.GetRequiredService<PersistenceDatabase>());
        Assert.Same(provider.GetRequiredService<IClaimRepository>(), provider.GetRequiredService<IClaimSink>());
        Assert.Same(provider.GetRequiredService<IManualOverrideRepository>(), provider.GetRequiredService<IBaseYearOverrides>());
        Assert.Same(provider.GetRequiredService<ILookupStore>(), provider.GetRequiredService<ILookupReader>());
        Assert.NotNull(provider.GetRequiredService<IGoldWriter>());
        Assert.NotNull(provider.GetRequiredService<IGoldReadPort>());
        Assert.NotNull(provider.GetRequiredService<IGoldDataQueryPort>());
        Assert.NotNull(provider.GetRequiredService<IRunManifestRepository>());
        Assert.NotNull(provider.GetRequiredService<IProgramDraftRepository>());
        Assert.NotNull(provider.GetRequiredService<IRunBatchRepository>());
        Assert.NotNull(provider.GetRequiredService<IFindingRepository>());
        Assert.NotNull(provider.GetRequiredService<IArtifactRepository>());
        Assert.NotNull(provider.GetRequiredService<IChannelStateRepository>());
        Assert.NotNull(provider.GetRequiredService<IChannelAuditRepository>());
        Assert.NotNull(provider.GetRequiredService<ISeedData>());
        Assert.NotNull(provider.GetRequiredService<IPersistenceUnitOfWork>());
        provider.GetRequiredService<SeedImporter>().Load("P1");
        Assert.NotNull(provider.GetRequiredService<IClaimSink>().Current(1001, "ga_jtc", 2025));
    }

    [Fact]
    public void Registration_refuses_a_second_destination_instead_of_splitting_the_stores()
    {
        using var first = new PersistenceFixture(false);
        using var second = new PersistenceFixture(false);
        var services = new ServiceCollection();
        var seedRoot = Path.Combine(PersistenceFixture.Root, "contract", "seed");
        services.AddPersistence(first.Database, PersistenceFixture.Root, seedRoot);
        Assert.Throws<InvalidOperationException>(() =>
            services.AddPersistence(second.Database, PersistenceFixture.Root, seedRoot));
        Assert.False(File.Exists(second.Path));
    }
}
