using System.Globalization;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.GoldWrite;

public sealed class GoldWriterTests
{
    private static GoldRunPayload Payload => GoldenPayload.Read(GoldenPayload.Scenario("csv-ty2025-ga"));

    [Fact]
    public void Publication_survives_reopen_and_supersedes_only_its_client_program()
    {
        using var fixture = new PersistenceFixture();
        var writer = new GoldWriter(fixture.Database, PersistenceFixture.Root);
        var first = Payload;
        writer.WriteRun(first);
        writer.WriteRun(GoldenPayload.Reidentify(first, "other-client", client: 1002));
        writer.WriteRun(GoldenPayload.Reidentify(first, "other-program", program: "GA_ALT"));
        writer.WriteRun(GoldenPayload.Reidentify(first, "replacement"));
        Assert.Empty(writer.Validate());
        using var read = PersistenceDatabase.Sqlite(fixture.Path).Open();
        var manifests = read.Query(1001, "SELECT run_id,run_status,superseded_by_run_id FROM tcc_ops.run_manifest WHERE {tenant} ORDER BY run_id");
        Assert.Equal("replacement", Assert.Single(manifests, r => (string)r["run_id"]! == first.RunId)["superseded_by_run_id"]);
        Assert.Equal("success", Assert.Single(manifests, r => (string)r["run_id"]! == "other-program")["run_status"]);
        Assert.Equal(16, read.Query(1001, "SELECT run_id FROM tcc_gold.unit_year_master WHERE {tenant} AND program_code='GA_JTC' AND is_current=1 AND run_id='replacement'").Count);
        Assert.Equal(16, read.Query(1002, "SELECT run_id FROM tcc_gold.unit_year_master WHERE {tenant} AND is_current=1").Count);
        Assert.Equal(32, read.Query(1001, "SELECT run_id FROM tcc_gold.unit_year_master WHERE {tenant} AND program_code='GA_JTC'").Count);
    }

    [Theory]
    [Trait("Category", "heavy")]
    [InlineData("prior-current-retired")]
    [InlineData("employee_period_fact")]
    [InlineData("unit_credit_installment")]
    public void Failure_after_retirement_or_insertion_keeps_the_prior_run_visible(string checkpoint)
    {
        using var fixture = new PersistenceFixture();
        var first = Payload;
        new GoldWriter(fixture.Database, PersistenceFixture.Root).WriteRun(first);
        var replacement = GoldenPayload.Reidentify(first, "failed-replacement");
        var writer = new GoldWriter(fixture.Database, PersistenceFixture.Root, stage =>
        {
            if (stage == checkpoint)
            {
                throw new IOException("Injected publication failure.");
            }
        });
        Assert.Throws<IOException>(() => writer.WriteRun(replacement));
        using var read = fixture.Database.Open();
        Assert.Equal(16, read.Query(1001, "SELECT run_id FROM tcc_gold.unit_year_master WHERE {tenant} AND is_current=1 AND run_id=?", first.RunId).Count);
        Assert.Empty(read.Query(1001, "SELECT run_id FROM tcc_gold.employee_period_fact WHERE {tenant} AND run_id=?", replacement.RunId));
        var failed = Assert.Single(read.Query(1001, "SELECT run_status,run_completed_at FROM tcc_ops.run_manifest WHERE {tenant} AND run_id=?", replacement.RunId));
        Assert.Equal("failed", failed["run_status"]);
        Assert.Null(failed["run_completed_at"]);
        Assert.Empty(writer.Validate());
    }

    [Fact]
    public void A_whole_use_case_transaction_rolls_back_gold_and_assessment_side_effects()
    {
        using var fixture = new PersistenceFixture();
        var first = Payload;
        var writer = new GoldWriter(fixture.Database, PersistenceFixture.Root);
        writer.WriteRun(first);
        var unit = new PersistenceUnitOfWork(fixture.Database);
        Assert.Throws<InvalidOperationException>(() => unit.Execute<int>(() =>
        {
            writer.WriteRun(GoldenPayload.Reidentify(first, "assessment-failed"));
            using var session = fixture.Database.Open();
            session.Execute(1001, "UPDATE tcc_ops.run_manifest SET triggered_by='assessment' WHERE {tenant} AND run_id=?", first.RunId);
            throw new InvalidOperationException("Assessment failed after Gold.");
        }));
        using var read = fixture.Database.Open();
        Assert.Empty(read.Query(1001, "SELECT run_id FROM tcc_ops.run_manifest WHERE {tenant} AND run_id='assessment-failed'"));
        Assert.Equal("tests", Assert.Single(read.Query(1001, "SELECT triggered_by FROM tcc_ops.run_manifest WHERE {tenant} AND run_id=?", first.RunId))["triggered_by"]);
        Assert.Equal(16, read.Query(1001, "SELECT run_id FROM tcc_gold.unit_year_master WHERE {tenant} AND is_current=1").Count);
    }

    [Fact]
    public void Reused_identity_and_foreign_rows_are_refused_and_stranded_runs_are_reaped()
    {
        using var fixture = new PersistenceFixture();
        var writer = new GoldWriter(fixture.Database, PersistenceFixture.Root);
        var payload = Payload;
        writer.WriteRun(payload);
        Assert.Throws<InvalidOperationException>(() => writer.WriteRun(payload));
        Assert.Throws<GoldWriteFailed>(() => writer.WriteRun(payload with { ClientId = 1002 }));
        using (var session = fixture.Database.Open())
        {
            session.Execute(1001, "UPDATE tcc_ops.run_manifest SET run_status='running',run_completed_at=NULL WHERE {tenant} AND run_id=?", payload.RunId);
            session.Execute(1001, "UPDATE tcc_gold.unit_year_master SET is_current=0 WHERE {tenant}");
            session.Execute(1001, "UPDATE tcc_gold.unit_credit_installment SET is_current=0 WHERE {tenant}");
        }

        Assert.Equal(1, writer.ReapStranded(new DateTime(2026, 11, 16)));
        using var read = fixture.Database.Open();
        var reaped = Assert.Single(read.Query(1001, "SELECT run_status,run_completed_at FROM tcc_ops.run_manifest WHERE {tenant}"));
        Assert.Equal("failed", reaped["run_status"]);
        Assert.Null(reaped["run_completed_at"]);
    }

    [Fact]
    public void Section_nine_detects_corruption_even_without_enforced_warehouse_keys()
    {
        using var fixture = new PersistenceFixture();
        var writer = new GoldWriter(fixture.Database, PersistenceFixture.Root);
        writer.WriteRun(Payload);
        using (var session = fixture.Database.Open())
        {
            session.Execute(1001, "INSERT INTO tcc_gold.unit_year_master SELECT * FROM tcc_gold.unit_year_master WHERE {tenant} AND worksite_id='GA_ATL_HQ' AND tax_year=2025");
            session.Execute(1001, "UPDATE tcc_gold.unit_credit_installment SET claimable_usd='999999.0000' WHERE {tenant}");
            session.Execute(1001, "UPDATE tcc_gold.employee_eligibility SET method='invalid',run_id='orphan' WHERE {tenant}");
        }

        var failures = writer.Validate();
        Assert.Contains(failures, f => f.Query == "9.4 one current row per unit-year-method");
        Assert.Contains(failures, f => f.Query == "9.4c installment arithmetic holds");
        Assert.Contains(failures, f => f.Query == "9.6e eligibility method in domain");
        Assert.Contains(failures, f => f.Query == "9.7 no orphaned run references: employee_eligibility");
    }

    internal static void StoredEquals(PersistenceDatabase database, GoldRunPayload payload)
    {
        var schema = PersistenceSchema.Read(PersistenceFixture.Root);
        using var session = database.Open();
        foreach (var (name, expected) in payload.Tables)
        {
            var actual = session.Query(payload.ClientId, "SELECT " + string.Join(",", GoldColumns.All[name]) + " FROM tcc_gold." + name + " WHERE {tenant} AND run_id=? ORDER BY rowid", payload.RunId);
            Assert.Equal(expected.Count, actual.Count);
            for (var i = 0; i < expected.Count; i++)
            {
                foreach (var (column, cell) in expected[i].Columns.Zip(expected[i].Cells))
                {
                    var value = schema["gold." + name].First(c => c.Name == column).ConvertValue(cell);
                    var stored = value switch
                    {
                        DateOnly date => date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                        TaxCredit.Domain.Numerics.PyDateTime date => date.IsoFormat().Replace('T', ' '),
                        TaxCredit.Domain.Numerics.PyDecimal number => number.ToString(),
                        _ => value,
                    };
                    Assert.Equal(stored, actual[i][column]);
                }
            }
        }
    }
}
