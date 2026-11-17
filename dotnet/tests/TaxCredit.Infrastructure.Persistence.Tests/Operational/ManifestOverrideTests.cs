using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Warehouse;
using TaxCredit.Infrastructure.Persistence.Operational;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.Operational;

public sealed class ManifestOverrideTests
{
    private static readonly PyDateTime Now = PyDateTime.FromIsoFormat("2026-01-01T12:00:00+00:00");

    [Fact]
    public async Task Concurrent_appends_use_one_durable_sequence_and_a_clear_always_wins_after_them()
    {
        using var store = new OperationalDatabase();
        using var start = new Barrier(2);
        Task Write(int prefix) => Task.Run(() =>
        {
            var repository = new ManualOverrideRepository(store.Reopen());
            start.SignalAndWait();
            for (var n = 0; n < 8; n++) { repository.Record(Override($"{prefix}-{8 - n}", 11, "GA_JTC:local", (2020 + n).ToString(System.Globalization.CultureInfo.InvariantCulture))); }
        });
        await Task.WhenAll(Write(1), Write(2));
        new ManualOverrideRepository(store.Reopen()).Record(Override("0-clear", 11, "GA_JTC:local", null));
        var reopened = new ManualOverrideRepository(store.Reopen());
        Assert.Equal(17, reopened.History(11).Count);
        Assert.Equal("0-clear", reopened.History(11)[^1].OverrideId);
        Assert.Empty(reopened.BaseYears(11, "GA_JTC"));
        using var session = store.Database.Open();
        var orders = session.Query(11, "SELECT write_order FROM tcc_ops.manual_override WHERE {tenant} ORDER BY write_order");
        Assert.Equal(Enumerable.Range(1, 17).Select(n => (long)n), orders.Select(r => (long)r["write_order"]!));
    }

    [Fact]
    public void Local_legacy_upgrade_is_idempotent_and_does_not_change_timestamps_or_public_ids()
    {
        using var store = new OperationalDatabase();
        var repository = new ManualOverrideRepository(store.Database);
        repository.Record(Override("z", 11, "GA_JTC:local", "2020"));
        store.Database.Transact(session => session.ExecuteExempt(SqlExemption.Schema,
            "ALTER TABLE tcc_ops.manual_override DROP COLUMN write_order"));
        OperationalSchema.Initialize(store.Database);
        OperationalSchema.Initialize(store.Database);
        var rows = new ManualOverrideRepository(store.Reopen()).History(11);
        Assert.Equal("z", Assert.Single(rows).OverrideId);
        Assert.Equal(Now, rows[0].CreatedAt);
        new ManualOverrideRepository(store.Reopen()).Record(Override("a", 11, "GA_JTC:local", null));
        Assert.Empty(repository.BaseYears(11, "GA_JTC"));
    }

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

    [Fact]
    public void Identical_timestamps_follow_durable_append_order_across_connections_and_reopen()
    {
        using var store = new OperationalDatabase();
        var first = new ManualOverrideRepository(store.Database);
        var second = new ManualOverrideRepository(store.Reopen());
        first.Record(Override("z", 11, "GA_JTC:local", "2020"));
        second.Record(Override("y", 11, "GA_JTC:local", "2021"));
        Assert.Equal(2021, first.BaseYears(11, "GA_JTC")["local"]);
        first.Record(Override("x", 11, "GA_JTC:local", null));
        Assert.Empty(second.BaseYears(11, "GA_JTC"));
        second.Record(Override("w", 22, "GA_JTC:local", "2019"));
        second.Record(Override("v", 11, "GA_JTC:local", "2023"));
        var reopened = new ManualOverrideRepository(store.Reopen());
        Assert.Equal(2023, reopened.BaseYears(11, "GA_JTC")["local"]);
        Assert.Equal(2019, reopened.BaseYears(22, "GA_JTC")["local"]);
        Assert.Equal(["z", "y", "x", "v"], reopened.History(11).Select(r => r.OverrideId));
        Assert.All(reopened.History(11), row => Assert.Equal(Now, row.CreatedAt));
    }

    private static ManualOverride Override(string id, long client, string key, string? value) =>
        new(id, "run", client, "unit", key, "base_year", null, value, "reason", "synthetic decision", "author", Now);
}
