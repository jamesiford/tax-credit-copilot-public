using TaxCredit.Domain.Claims;
using TaxCredit.Domain.DataMap;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Persistence.Operational;
using TaxCredit.Infrastructure.Persistence.Sql;
using Map = TaxCredit.Domain.DataMap.DataMap;

namespace TaxCredit.Infrastructure.Persistence.Tests.Sql;

/// <summary>A customer's data map renames every schema and some tables; nothing named tcc_* may be created or used.</summary>
public sealed class RenamedDataMapTests
{
    private static readonly PyDateTime Now = PyDateTime.FromIsoFormat("2026-01-02T03:04:05.123456+00:00");

    private static PhysicalNames Renamed()
    {
        var root = PersistenceFixture.Root;
        var json = File.ReadAllText(System.IO.Path.Combine(root, "docs", "data", "data-map.json"))
            .Replace("\"gold\": \"tcc_gold\"", "\"gold\": \"cust_numbers\"", StringComparison.Ordinal)
            .Replace("\"ops\": \"tcc_ops\"", "\"ops\": \"cust_ops\"", StringComparison.Ordinal)
            .Replace("\"table\": \"run_manifest\"", "\"table\": \"runs\"", StringComparison.Ordinal)
            .Replace("\"table\": \"program_claim\"", "\"table\": \"claims\"", StringComparison.Ordinal);
        var file = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "renamed-map-" + Guid.NewGuid().ToString("N") + ".json");
        File.WriteAllText(file, json);
        try
        {
            return new PhysicalNames(DataMapLoader.LoadFile(file));
        }
        finally
        {
            File.Delete(file);
        }
    }

    [Fact]
    public void Schema_statements_and_repositories_use_only_the_mapped_names()
    {
        var path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "renamed-" + Guid.NewGuid().ToString("N") + ".db");
        try
        {
            var database = PersistenceDatabase.Sqlite(path, names: Renamed());
            PersistenceSchema.Initialize(database, PersistenceFixture.Root);
            OperationalSchema.Initialize(database);
            var claim = ProgramClaim.Create(new ClaimSpec
            {
                ClientId = 11,
                ProgramCode = "ga_jtc",
                TaxYear = 2023,
                ClaimId = "c1",
                Status = ClaimStatus.Claimed,
                Provenance = Provenance.FiledByUs,
                IdentifiedUsd = "1.00",
                ClaimedUsd = "0.20",
                CertifiedUsd = "2.0000",
                AverageHeadcount = 75.5,
                BaseAverageHeadcount = 20,
                ThresholdJobs = 2,
                IsBaseYear = false,
                EntityId = 99,
                IdentifiedRunId = "run",
                AssumptionSetId = "a",
                RulePackVersion = "p",
                FiledOn = new DateOnly(2026, 1, 1),
                FilingReference = "x",
                DecidedBy = "d",
                DecidedAt = Now,
                DeclineReason = "",
                EffectiveFrom = Now,
            });
            new ClaimRepository(database).Record(claim);
            Assert.Equal(claim, new ClaimRepository(PersistenceDatabase.Sqlite(path, names: Renamed())).Current(11, "ga_jtc", 2023));

            using var session = database.Open();
            var tables = session.QueryExempt(SqlExemption.Schema, "SELECT name FROM sqlite_master WHERE type='table'")
                .Select(r => (string)r["name"]!).ToList();
            Assert.DoesNotContain(tables, t => t.StartsWith("tcc_", StringComparison.Ordinal));
            Assert.Contains("cust_ops_claims", tables);
            Assert.Contains("cust_ops_runs", tables);
            Assert.Contains("cust_numbers_unit_year_master", tables);
            Assert.Equal(38, tables.Count(t => t.StartsWith("cust_", StringComparison.Ordinal)));
        }
        finally
        {
            Microsoft.Data.Sqlite.SqliteConnection.ClearAllPools();
            File.Delete(path);
        }
    }
}
