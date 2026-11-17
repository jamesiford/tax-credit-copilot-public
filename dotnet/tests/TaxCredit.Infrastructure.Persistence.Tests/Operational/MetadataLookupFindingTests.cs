using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Findings;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Persistence.Operational;

namespace TaxCredit.Infrastructure.Persistence.Tests.Operational;

public sealed class MetadataLookupFindingTests
{
    private static readonly PyDateTime Now = RunBatchRepositoryTests.At(0);

    [Fact]
    public void LookupTenantAndGlobalRowsKeepDatesAndCloseRatherThanDelete()
    {
        using var store = new OperationalDatabase();
        var repository = new LookupStore(store.Database);
        var entry = new LookupEntry("pay_code_category", 11, "code", "LOCAL", "Regular", "author", "synthetic", true, new DateOnly(2999, 1, 1));
        repository.Put(entry, Now);
        repository.Put(entry with { ClientId = 22, ValueJson = "Bonus" }, Now);
        repository.Put(entry with { ClientId = 0, Key = "GLOBAL", ValueJson = "Overtime" }, Now);
        var rows = new LookupStore(store.Reopen()).Entries("pay_code_category", 11);
        Assert.Equal([11L, 0L], rows.Select(row => row.ClientId).ToArray());
        Assert.Equal(new DateOnly(2999, 1, 1), rows[0].EffectiveFrom);
        Assert.Equal("Regular", rows[0].ValueJson);
        repository.Put(entry with { ValueJson = "Commission" }, RunBatchRepositoryTests.At(1));
        Assert.Equal("Commission", repository.Entries("pay_code_category", 11)[0].ValueJson);
        Assert.True(repository.Remove("pay_code_category", 11, "code", "LOCAL", "reviewer", RunBatchRepositoryTests.At(2)));
        Assert.False(repository.Remove("pay_code_category", 11, "code", "LOCAL", "reviewer", Now));
        Assert.Equal(0, repository.Entries("pay_code_category", 11).Single().ClientId);
        Assert.Equal("Bonus", repository.Entries("pay_code_category", 22)[0].ValueJson);
        Assert.Equal(["put", "put", "remove"], repository.Audit(11).Select(row => row["action"]).ToArray());
        Assert.Single(repository.Audit(0));
        using var session = store.Database.Open();
        Assert.Equal(2, session.Query(11, "SELECT override_id FROM tcc_ops.lookup_override WHERE {tenant}").Count);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(123456)]
    public void FindingResolutionAndReopenAreDurableAttributedAndTenantScoped(int microsecond)
    {
        using var store = new OperationalDatabase();
        var repository = new FindingRepository(store.Database);
        var resolution = new FindingResolution
        {
            ClientId = 11,
            FindingId = "local-id",
            TaxYear = 2023,
            Resolution = "assign",
            DecidedBy = "author",
            DecidedAt = Now.IsoFormat(),
            Detail = new PyDict().Add("unit", "synthetic"),
            Note = "synthetic note",
        };
        repository.Record(resolution);
        repository.Record(resolution with { ClientId = 22, Resolution = "drop" });
        repository.Record(resolution with { Resolution = "accept", DecidedAt = RunBatchRepositoryTests.At(1).IsoFormat() });
        Assert.Single(repository.Live(11, 2023));
        Assert.Empty(repository.Live(11, 2024));
        Assert.Equal(2, repository.History(11, "local-id").Count);
        var reopenedAt = RunBatchRepositoryTests.At(2) with { Microsecond = microsecond };
        Assert.True(repository.Reopen(11, "local-id", "reviewer", reopenedAt));
        var restarted = new FindingRepository(store.Reopen());
        Assert.Empty(restarted.Live(11));
        Assert.Equal("drop", restarted.Live(22).Single().Resolution);
        Assert.Equal(2, restarted.History(11, "local-id").Count);
        Assert.Equal(reopenedAt.IsoFormat(), restarted.History(11, "local-id")[^1].SupersededAt);
        Assert.Equal(["resolve", "resolve", "reopen"], restarted.Audit(11, "local-id").Select(row => row.Action).ToArray());
        Assert.Equal("reviewer", restarted.Audit(11, "local-id")[^1].Actor);
        Assert.False(restarted.Reopen(11, "local-id", "reviewer", Now));
        Assert.Throws<ArgumentException>(() => restarted.Record(resolution with { Resolution = "invented" }));
    }

    [Fact]
    public void ArtifactSupersessionKeepsOtherYearsAndClientsAndRefusesDuplicatePath()
    {
        using var store = new OperationalDatabase();
        var repository = new ArtifactRepository(store.Database);
        var first = Artifact("first", 11, 2023);
        repository.Record(first);
        repository.Record(Artifact("other-year", 11, 2022));
        repository.Record(Artifact("other-client", 22, 2023));
        repository.Record(Artifact("second", 11, 2023));
        var restarted = new ArtifactRepository(store.Reopen());
        Assert.NotNull(restarted.Find("first")!.SupersededAt);
        Assert.Null(restarted.Find("other-year")!.SupersededAt);
        Assert.Null(restarted.Find("other-client")!.SupersededAt);
        Assert.Equal("second", restarted.Live(11, "claim_package", 2023).Single().ArtifactId);
        Assert.Equal(2, restarted.Live(11).Count);
        Assert.Single(restarted.Live(22));
        Assert.Null(restarted.Find("missing"));
        Assert.Throws<InvalidOperationException>(() => restarted.Record(first with { ArtifactId = "duplicate-path" }));
        Assert.Equal("second", restarted.Live(11, "claim_package", 2023).Single().ArtifactId);
        Assert.Throws<ArgumentException>(() => restarted.Record(first with { ArtifactId = "bad-prefix", BlobPath = "22/run/x" }));
    }

    [Fact]
    public void AccessAuditRecordsAllOutcomesIncludingUnknownMetadataWithoutServingAnotherClient()
    {
        using var store = new OperationalDatabase();
        var repository = new ArtifactRepository(store.Database);
        repository.Record(Artifact("artifact", 11, 2023));
        foreach (var outcome in new[] { "served", "denied", "missing" })
        {
            repository.RecordAccess(new ArtifactAccess(outcome, "artifact", 11, "synthetic-user", "synthetic-oid", Now, outcome));
        }

        repository.RecordAccess(new ArtifactAccess("absent", "never-created", 11, "synthetic-user", null, Now, "missing"));
        Assert.Equal(4, new ArtifactRepository(store.Reopen()).Accesses(11).Count);
        Assert.Empty(repository.Accesses(22));
        Assert.Throws<InvalidOperationException>(() => repository.RecordAccess(
            new ArtifactAccess("wrong-client", "artifact", 22, "synthetic-user", null, Now, "served")));
    }

    [Fact]
    public void RuleSourceMetadataIsGlobalAndDoesNotSupersedeClientPackages()
    {
        using var store = new OperationalDatabase();
        var repository = new ArtifactRepository(store.Database);
        repository.Record(Artifact("package", 11, 2023));
        var source = Artifact("source", 11, 2023) with { Kind = "rule_source", ClientId = null, RunId = null, ContainerName = "artifacts", BlobPath = "rules/source.pdf" };
        repository.Record(source);
        Assert.Equal(source, new ArtifactRepository(store.Reopen()).Find("source"));
        Assert.Equal("package", repository.Live(11).Single().ArtifactId);
    }

    private static ArtifactMetadata Artifact(string id, long client, long? year) => new()
    {
        ArtifactId = id,
        ClientId = client,
        Kind = "claim_package",
        ProgramCode = "GA_JTC",
        TaxYear = year,
        RunId = "run",
        ContainerName = "outputs",
        BlobPath = $"{client}/run/{id}.xlsx",
        FileName = id + ".xlsx",
        ContentType = "application/octet-stream",
        SizeBytes = 123,
        Sha256 = new string('a', 64),
        CreatedBy = "author",
        CreatedAt = Now,
        RetainUntil = new DateOnly(2033, 1, 1),
    };
}
