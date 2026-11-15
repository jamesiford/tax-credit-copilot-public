using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Persistence.Operational;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.GoldWrite;

public sealed class ClientCalculationPersistenceTests
{
    [Fact]
    [Trait("Category", "heavy")]
    public void Every_successful_certified_pipeline_payload_is_persisted_without_changing_a_cell()
    {
        var scenarios = 0;
        long rows = 0;
        foreach (var record in GoldenPayload.Records("gold_payload.jsonl.gz"))
        {
            if (record.GetProperty("k").GetString() != "run" || !record.TryGetProperty("out", out _))
            {
                continue;
            }

            using var fixture = new PersistenceFixture();
            OperationalSchema.Initialize(fixture.Database);
            var claims = new ClaimRepository(fixture.Database);
            var overrides = new ManualOverrideRepository(fixture.Database);
            PipelineInputs.Seed(record, claims, overrides);
            var expected = GoldenPayload.Read(record);
            var writer = new GoldWriter(fixture.Database, PersistenceFixture.Root);
            var calculation = PipelineInputs.Create(record, claims, overrides, new CertifyingWriter(expected, writer));
            var runner = new PersistedClientCalculation(calculation, new PersistenceUnitOfWork(fixture.Database));
            var result = runner.Run(PipelineInputs.Command(record));
            Assert.Equal("success", result["run_status"]);
            Assert.Empty(writer.Validate());
            var reopened = PersistenceDatabase.Sqlite(fixture.Path);
            GoldWriterTests.StoredEquals(reopened, expected);
            using var read = reopened.Open();
            Assert.Equal("success", Assert.Single(read.Query(expected.ClientId,
                "SELECT run_status FROM tcc_ops.run_manifest WHERE {tenant} AND run_id=?", expected.RunId))["run_status"]);
            Assert.NotEmpty(read.Query(expected.ClientId, "SELECT claim_id FROM tcc_ops.program_claim WHERE {tenant}"));
            scenarios++;
            rows += expected.Tables.Sum(t => (long)t.Value.Count);
        }

        Assert.Equal(12, scenarios);
        Assert.Equal(390945L, rows);
    }

    [Fact]
    [Trait("Category", "heavy")]
    public void Assessment_failure_after_real_gold_and_claim_writes_cannot_publish_a_partial_run()
    {
        using var fixture = new PersistenceFixture();
        OperationalSchema.Initialize(fixture.Database);
        var record = GoldenPayload.Scenario("csv-ty2025-ga");
        var expected = GoldenPayload.Read(record);
        var claims = new ClaimRepository(fixture.Database);
        var writer = new GoldWriter(fixture.Database, PersistenceFixture.Root);
        var calculation = PipelineInputs.Create(record, new FailingClaims(claims),
            new ManualOverrideRepository(fixture.Database), new CertifyingWriter(expected, writer));
        var runner = new PersistedClientCalculation(calculation, new PersistenceUnitOfWork(fixture.Database));
        Assert.Throws<IOException>(() => runner.Run(PipelineInputs.Command(record)));
        using var read = fixture.Database.Open();
        Assert.Empty(read.Query(1001, "SELECT run_id FROM tcc_ops.run_manifest WHERE {tenant}"));
        Assert.Empty(read.Query(1001, "SELECT claim_id FROM tcc_ops.program_claim WHERE {tenant}"));
        foreach (var (name, _) in expected.Tables)
        {
            Assert.Empty(read.Query(1001, "SELECT run_id FROM tcc_gold." + name + " WHERE {tenant}"));
        }
    }

    private sealed class FailingClaims(IClaimSink inner) : IClaimSink
    {
        public ProgramClaim? Current(long clientId, string programCode, long taxYear) => inner.Current(clientId, programCode, taxYear);
        public void Record(ProgramClaim claim)
        {
            inner.Record(claim);
            throw new IOException("Injected assessment failure after the actual claim write.");
        }
    }
}
