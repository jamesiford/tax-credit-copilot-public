using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Warehouse;
using TaxCredit.Infrastructure.Persistence.Operational;

namespace TaxCredit.Infrastructure.Persistence.Tests.Operational;

public sealed class ManifestOverrideTests
{
    private static readonly PyDateTime Now = PyDateTime.FromIsoFormat("2026-01-01T12:00:00+00:00");

    [Fact]
    public void LatestReadsOnlyUnsupersededSuccessInTheSelectedClientAndProgram()
    {
        using var store = new OperationalDatabase();
        var repository = Assert.IsAssignableFrom<IRunManifestRepository>(new RunManifestRepository(store.Database));
        Assert.Null(repository.Latest(11));
        repository.Record(Manifest("a", 11));
        repository.Record(Manifest("b", 22));
        repository.Record(Manifest("running", 11) with { RunStatus = "running" });
        repository.Record(Manifest("failed", 11) with { RunStatus = "failed" });
        repository.Record(Manifest("superseded", 11) with { SupersededByRunId = "a" });
        repository.Record(Manifest("other", 11) with { ProgramCode = "OTHER" });
        var reopened = new RunManifestRepository(store.Reopen());
        Assert.Equal(6, reopened.Count());
        Assert.Equal("a", reopened.Latest(11, "GA_JTC")!.RunId);
        Assert.Equal("b", reopened.Latest(22, "GA_JTC")!.RunId);
        Assert.Null(reopened.Latest(11, "ABSENT"));
        Assert.Equal(repository.Get("a"), reopened.Get("a"));
        Assert.Null(reopened.Get("missing"));
        Assert.Throws<InvalidOperationException>(() => reopened.Record(Manifest("a", 22)));
    }

    [Fact]
    public void OverridePairReadsLatestClearAndInvalidValuesWithoutCrossTenantLeakage()
    {
        using var store = new OperationalDatabase();
        var repository = new ManualOverrideRepository(store.Database);
        var pipeline = Assert.IsAssignableFrom<IBaseYearOverrides>(repository);
        repository.Record(Override("a", 11, "GA_JTC:local", "2021"));
        repository.Record(Override("a", 22, "GA_JTC:local", "2022"));
        repository.Record(Override("b", 11, "OTHER:local", "2020"));
        Assert.Equal(2021, pipeline.BaseYears(11, "GA_JTC")["local"]);
        Assert.Equal(2022, pipeline.BaseYears(22, "GA_JTC")["local"]);
        repository.Record(Override("c", 11, "GA_JTC:local", null));
        repository.Record(Override("d", 11, "GA_JTC:invalid", "not-a-year"));
        Assert.Empty(new ManualOverrideRepository(store.Reopen()).BaseYears(11, "GA_JTC"));
        Assert.Equal(4, repository.History(11).Count);
        Assert.Single(repository.History(22));
        Assert.Throws<InvalidOperationException>(() => repository.Record(Override("a", 11, "GA_JTC:local", "2025")));
    }

    internal static RunManifest Manifest(string id, long client) => new(id, client, "GA_JTC", 2023,
        new DateOnly(2023, 1, 1), new DateOnly(2023, 12, 31), Now, "success", sourceSnapshotId: "snapshot",
        step1AssumptionSetId: "step", step1AssumptionSha256: new string('a', 64), onezeroAssumptionSetId: "oz",
        onezeroAssumptionSha256: new string('b', 64), rulePackVersion: "pack", codeCommit: new string('c', 40),
        calculationId: new string('d', 64), runCompletedAt: Now, triggeredBy: "synthetic-actor");

    private static ManualOverride Override(string id, long client, string key, string? value) =>
        new(id, "run", client, "unit", key, "base_year", null, value, "reason", "synthetic decision", "author", Now);
}
