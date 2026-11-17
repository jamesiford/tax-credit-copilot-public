using System.Globalization;
using TaxCredit.Infrastructure.Persistence.GoldRead;

namespace TaxCredit.Infrastructure.Persistence.Tests.GoldRead;

public sealed class GoldRunTests(GoldFixture fixture) : IClassFixture<GoldFixture>
{
    [Fact]
    public void Latest_success_is_program_scoped_unsuperseded_and_independent_of_commanded_year()
    {
        const long client = 910002;
        using var session = fixture.Database.Open();
        var template = session.Query(1001, "SELECT * FROM tcc_ops.run_manifest WHERE {tenant}")[0];
        var columns = template.Keys.ToArray();
        var rows = new[]
        {
            Manifest(template, client, "success", "2026-01-15 09:00:00", "GA_JTC"),
            Manifest(template, client, "failed", "2026-01-15 11:00:00", "GA_JTC"),
            Manifest(template, client, "success", "2026-01-15 10:00:00", "OTHER"),
        };
        rows[0]["tax_year"] = 2020L;
        session.Insert(client, "tcc_ops.run_manifest", columns, rows.Select(r => (IReadOnlyList<object?>)columns.Select(c => r[c]).ToArray()).ToArray());
        try
        {
            Assert.Equal(rows[0]["run_id"], fixture.Reader.LatestRun(client, "GA_JTC")!["run_id"]);
            Assert.Equal(2020L, fixture.Reader.LatestRun(client, "GA_JTC")!["tax_year"]);
            Assert.Equal(rows[2]["run_id"], fixture.Reader.LatestRun(client)!["run_id"]);
            session.Execute(client, "UPDATE tcc_ops.run_manifest SET superseded_by_run_id = ? WHERE {tenant} AND run_id = ?", rows[2]["run_id"], rows[0]["run_id"]);
            Assert.Null(fixture.Reader.LatestRun(client, "GA_JTC"));
        }
        finally
        {
            session.Execute(client, "DELETE FROM tcc_ops.run_manifest WHERE {tenant}");
        }
    }

    [Fact]
    public void Running_manifests_expire_and_failed_or_completed_rows_do_not_claim_to_be_in_flight()
    {
        const long client = 910003;
        using var session = fixture.Database.Open();
        var template = session.Query(1001, "SELECT * FROM tcc_ops.run_manifest WHERE {tenant}")[0];
        var columns = template.Keys.ToArray();
        var fresh = Manifest(template, client, "running", "2026-01-15 11:59:00", "GA_JTC");
        var stale = Manifest(template, client, "running", "2026-01-14 11:59:00", "GA_JTC");
        var failed = Manifest(template, client, "failed", "2026-01-15 12:00:00", "GA_JTC");
        fresh["run_completed_at"] = null;
        stale["run_completed_at"] = null;
        failed["run_completed_at"] = null;
        session.Insert(client, "tcc_ops.run_manifest", columns, new[] { fresh, stale, failed }
            .Select(r => (IReadOnlyList<object?>)columns.Select(c => r[c]).ToArray()).ToArray());
        try
        {
            Assert.Equal(fresh["run_id"], fixture.Reader.RunInFlight(client)!["run_id"]);
            session.Execute(client, "UPDATE tcc_ops.run_manifest SET run_completed_at = ? WHERE {tenant} AND run_id = ?", "2026-01-15 12:00:00", fresh["run_id"]);
            Assert.Null(fixture.Reader.RunInFlight(client));
            var envelope = RunEnvelope.Create(null, new Dictionary<string, object?> { ["run_id"] = "coming" });
            Assert.Equal("not_calculated", envelope["calculation_state"]);
            Assert.Equal(true, envelope["newer_run_in_flight"]);
        }
        finally
        {
            session.Execute(client, "DELETE FROM tcc_ops.run_manifest WHERE {tenant}");
        }
    }

    private static Dictionary<string, object?> Manifest(IReadOnlyDictionary<string, object?> template,
        long client, string status, string started, string program)
    {
        var row = template.ToDictionary(p => p.Key, p => p.Value, StringComparer.Ordinal);
        row["client_id"] = client;
        row["run_id"] = Guid.NewGuid().ToString("N", CultureInfo.InvariantCulture);
        row["run_status"] = status;
        row["run_started_at"] = started;
        row["run_completed_at"] = started;
        row["program_code"] = program;
        row["superseded_by_run_id"] = null;
        return row;
    }
}
