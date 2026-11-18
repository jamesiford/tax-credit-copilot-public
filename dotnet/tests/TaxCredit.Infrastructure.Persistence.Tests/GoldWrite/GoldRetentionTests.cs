using System.Text.Json;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Persistence.GoldRead;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.GoldWrite;

public sealed class GoldRetentionTests
{
    private static readonly string[] Pruned = ["employee_period_fact", "onezero_matrix", "employee_eligibility"];
    private static readonly string[] Kept = ["unit_year_master", "unit_credit_installment", "unit_month_summary", "run_method_summary"];

    private static GoldRunPayload Run(string id, int minute, long client = 1001, string? program = null)
    {
        var payload = GoldenPayload.Reidentify(GoldenPayload.Read(GoldenPayload.Scenario("csv-ty2025-ga")), id, client, program);
        var manifest = payload.ManifestRow.ToArray();
        manifest[payload.ManifestColumns.ToList().IndexOf("run_started_at")] = PyDateTime.FromIsoFormat("2026-03-01T10:" + minute.ToString("00", System.Globalization.CultureInfo.InvariantCulture) + ":00");
        return payload with { ManifestRow = manifest };
    }

    private static int Count(PersistenceDatabase database, string table, string run, long client = 1001)
    {
        using var session = database.Open();
        return session.Query(client, "SELECT run_id FROM tcc_gold." + table + " WHERE {tenant} AND run_id=?", run).Count;
    }

    private static string Status(PersistenceDatabase database, string run)
    {
        using var session = database.Open();
        return (string)session.Query(1001, "SELECT run_status FROM tcc_ops.run_manifest WHERE {tenant} AND run_id=?", run).Single()["run_status"]!;
    }

    [Fact]
    public void Only_runs_beyond_the_newest_superseded_ones_lose_their_employee_rows_and_nothing_else_is_touched()
    {
        using var fixture = new PersistenceFixture();
        var writer = new GoldWriter(fixture.Database, PersistenceFixture.Root, retention: new GoldRetention(2));
        for (var i = 1; i <= 5; i++) { writer.WriteRun(Run("r" + i, i)); }
        foreach (var table in Pruned)
        {
            Assert.All(new[] { "r1", "r2" }, run => Assert.Equal(0, Count(fixture.Database, table, run)));
            Assert.All(new[] { "r3", "r4", "r5" }, run => Assert.True(Count(fixture.Database, table, run) > 0, table + " " + run));
        }

        foreach (var table in Kept)
        {
            Assert.All(new[] { "r1", "r2", "r3", "r4", "r5" }, run => Assert.True(Count(fixture.Database, table, run) > 0, table + " " + run));
        }

        Assert.Equal(["superseded", "superseded", "superseded", "superseded", "success"], new[] { "r1", "r2", "r3", "r4", "r5" }.Select(r => Status(fixture.Database, r)));
        Assert.Empty(writer.Validate());
    }

    [Fact]
    public void Retention_never_reaches_another_client_or_program()
    {
        using var fixture = new PersistenceFixture();
        var writer = new GoldWriter(fixture.Database, PersistenceFixture.Root, retention: new GoldRetention(1));
        writer.WriteRun(Run("other-client-1", 1, 1002));
        writer.WriteRun(Run("other-program-1", 1, program: "GA_ALT"));
        for (var i = 1; i <= 3; i++) { writer.WriteRun(Run("r" + i, i)); }
        Assert.Equal(0, Count(fixture.Database, "employee_period_fact", "r1"));
        Assert.True(Count(fixture.Database, "employee_period_fact", "r2") > 0);
        Assert.True(Count(fixture.Database, "employee_period_fact", "other-client-1", 1002) > 0);
        Assert.True(Count(fixture.Database, "employee_period_fact", "other-program-1") > 0);
    }

    [Fact]
    public void A_failed_prune_never_affects_the_published_run_and_a_later_publication_finishes_the_job()
    {
        var messages = new List<string>();
        var path = Path.Combine(Path.GetTempPath(), "tcc-retention-" + Guid.NewGuid().ToString("N") + ".db");
        try
        {
            var database = PersistenceDatabase.Sqlite(path, messages.Add);
            PersistenceSchema.Initialize(database, PersistenceFixture.Root);
            var writer = new GoldWriter(database, PersistenceFixture.Root, retention: new GoldRetention(1));
            writer.WriteRun(Run("r1", 1));
            writer.WriteRun(Run("r2", 2));
            using (var session = database.Open())
            {
                session.ExecuteExempt(SqlExemption.Schema, "CREATE TRIGGER refuse BEFORE DELETE ON tcc_gold_onezero_matrix BEGIN SELECT RAISE(ABORT,'refused'); END");
            }

            var counts = writer.WriteRun(Run("r3", 3));
            Assert.Contains(counts, c => c.Key == "employee_period_fact" && c.Value > 0);
            Assert.Contains(messages, m => m.Contains("housekeeping failed", StringComparison.Ordinal));
            Assert.Equal("success", Status(database, "r3"));
            Assert.All(Pruned, table => Assert.True(Count(database, table, "r3") > 0));
            Assert.All(Pruned, table => Assert.True(Count(database, table, "r1") > 0, "the failed pass is atomic per run: " + table));
            Assert.Empty(writer.Validate());
            using (var session = database.Open())
            {
                session.ExecuteExempt(SqlExemption.Schema, "DROP TRIGGER refuse");
            }

            writer.WriteRun(Run("r4", 4));
            Assert.All(Pruned, table => Assert.Equal(0, Count(database, table, "r1") + Count(database, table, "r2")));
            Assert.All(Pruned, table => Assert.True(Count(database, table, "r3") > 0));
        }
        finally
        {
            File.Delete(path);
        }
    }

    [Fact]
    public void Pruning_waits_for_the_outer_commit_and_never_follows_a_rollback()
    {
        using var fixture = new PersistenceFixture();
        var writer = new GoldWriter(fixture.Database, PersistenceFixture.Root, retention: new GoldRetention(1));
        var unit = new PersistenceUnitOfWork(fixture.Database);
        writer.WriteRun(Run("r1", 1));
        writer.WriteRun(Run("r2", 2));
        Assert.Throws<InvalidOperationException>(() => unit.Execute<int>(() =>
        {
            writer.WriteRun(Run("r3", 3));
            throw new InvalidOperationException("The surrounding use case failed after Gold.");
        }));
        Assert.True(Count(fixture.Database, "employee_period_fact", "r1") > 0);
        Assert.Equal(0, Count(fixture.Database, "employee_period_fact", "r3"));
        unit.Execute(() =>
        {
            writer.WriteRun(Run("r3", 3));
            Assert.True(Count(fixture.Database, "employee_period_fact", "r1") > 0);
            return 0;
        });
        Assert.Equal(0, Count(fixture.Database, "employee_period_fact", "r1"));
        Assert.True(Count(fixture.Database, "employee_period_fact", "r2") > 0);
    }

    [Fact]
    public void Every_read_of_the_current_run_is_identical_with_and_without_retention()
    {
        using var kept = new PersistenceFixture();
        using var pruned = new PersistenceFixture();
        var all = new GoldWriter(kept.Database, PersistenceFixture.Root);
        var trimmed = new GoldWriter(pruned.Database, PersistenceFixture.Root, retention: new GoldRetention(1));
        GoldRunPayload last = Run("r4", 4);
        for (var i = 1; i <= 4; i++)
        {
            last = Run("r" + i, i);
            all.WriteRun(last);
            trimmed.WriteRun(last);
        }

        Assert.Equal(0, Count(pruned.Database, "employee_period_fact", "r1"));
        var token = last.EmployeeEligibility[0]["record_token"].AsText;
        var site = last.UnitYearMaster[0]["worksite_id"].AsText;
        var year = (int)last.UnitYearMaster[0]["tax_year"].AsInt;
        Assert.Equal(Reads(kept.Database, token, site, year), Reads(pruned.Database, token, site, year));
    }

    private static string Reads(PersistenceDatabase database, string token, string site, int year)
    {
        var gold = new GoldReader(database);
        var run = gold.LatestRun(1001)!;
        var runId = (string)run["run_id"]!;
        var options = new RiskOptions(35, 636);
        var results = new List<object?>
        {
            run, gold.UnitYears(1001, "min_max"), gold.UnitYears(1001, "pay_period"), gold.UnitPage(1001, "min_max"),
        };
        foreach (var method in new[] { "min_max", "pay_period" })
        {
            results.AddRange(gold.UnitMonths(1001, site, year, method, runId), gold.MonthSummaries(1001, method, runId),
                gold.UnitEmployees(1001, site, year, method, runId), gold.UnitNearThreshold(1001, site, year, method, runId),
                gold.UnitDrill(1001, site, year, method), gold.HeadcountSeries(1001, year, method), gold.ClientYearSeries(1001, method),
                gold.OnezeroMatrix(1001, year, method), gold.AtRisk(1001, year, method, options), gold.ProximityCandidates(1001, year, method, options),
                gold.Employee(token, 1001, year, runId), gold.EmployeeUnits(token, 1001, year, runId, method));
        }

        results.Add(gold.CohortPeriods(1001, year, runId, [token]));
        results.Add(gold.EligibilityPopulation(1001, year, 35, 636));
        results.Add(gold.EmployeeDrill(1001, year, token));
        return JsonSerializer.Serialize(results);
    }

    [Fact]
    public void The_setting_reads_a_count_or_all_and_refuses_nonsense()
    {
        Assert.Equal(GoldRetention.Default, GoldRetention.FromSettings(_ => null));
        Assert.Equal(GoldRetention.Off, GoldRetention.FromSettings(_ => "all"));
        Assert.Equal(new GoldRetention(4), GoldRetention.FromSettings(_ => "4"));
        Assert.Throws<InvalidOperationException>(() => GoldRetention.FromSettings(_ => "0"));
        Assert.Throws<InvalidOperationException>(() => GoldRetention.FromSettings(_ => "-1"));
        Assert.Throws<InvalidOperationException>(() => GoldRetention.FromSettings(_ => "many"));
    }
}
