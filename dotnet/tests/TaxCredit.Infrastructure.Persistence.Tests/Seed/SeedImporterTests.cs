using System.Text.Json.Nodes;
using Microsoft.Data.Sqlite;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.Seed;

public sealed class SeedImporterTests
{
    [Fact]
    public void P1_reset_is_repeatable_and_readable_after_reopening()
    {
        using var fixture = new PersistenceFixture();
        var first = fixture.Load("P1");
        Assert.Equal(11, first.TableCounts.Count);
        Assert.Equal(18111, first.TotalRows);
        Assert.Equal(9477, first.TableCounts["source/pay_periods.jsonl.gz"]);
        Assert.Equal(5281, first.TableCounts["gold/employee_period_fact.jsonl.gz"]);
        var second = fixture.Load("P1");
        Assert.Equal(first.TableCounts, second.TableCounts);
        var reopened = PersistenceDatabase.Sqlite(fixture.Path);
        using var read = reopened.Open();
        Assert.Equal(107L, Assert.Single(read.Query(1001,
            "SELECT COUNT(DISTINCT record_token) AS n FROM tcc_gold.employee_eligibility WHERE {tenant} AND tax_year=2025 AND method='min_max'"))["n"]);
        Assert.Equal(2, read.Query(1001, "SELECT claim_id,identified_usd FROM tcc_ops.program_claim WHERE {tenant}").Count);
        Assert.Single(read.Query(1001, "SELECT run_status FROM tcc_ops.run_manifest WHERE {tenant} AND run_status='success'"));
        var source = new SourceSeedData(reopened);
        Assert.Equal(9477, source.ReadTable("pay_periods").Count());
        Assert.Single(source.Tables());
    }

    [Fact]
    [Trait("Category", "heavy")]
    public void P1_to_P2_to_P1_accounts_for_every_table_and_population()
    {
        using var fixture = new PersistenceFixture();
        fixture.Load("P1");
        var p2 = fixture.Load("P2");
        Assert.Equal(20, p2.TableCounts.Count);
        Assert.Equal(390660, p2.TotalRows);
        Assert.Equal(197094, p2.TableCounts["source/Payroll.jsonl.gz"]);
        Assert.Equal(4, p2.TableCounts["source/EntityFiscalYearRules.jsonl.gz"]);
        Assert.Equal(22, p2.TableCounts["operational/program_claim.jsonl.gz"]);
        using (var read = fixture.Database.Open())
        {
            foreach (var (client, count) in new[] { (2001L, 202L), (2002L, 164L), (2003L, 137L), (2004L, 125L) })
            {
                Assert.Equal(count, Assert.Single(read.Query(client,
                    "SELECT COUNT(DISTINCT record_token) AS n FROM tcc_gold.employee_eligibility WHERE {tenant} AND tax_year=2025 AND method='min_max'"))["n"]);
            }
        }

        Assert.Equal(18111, fixture.Load("P1").TotalRows);
        using var restored = fixture.Database.Open();
        Assert.Empty(restored.Query(2001, "SELECT run_id FROM tcc_ops.run_manifest WHERE {tenant}"));
        Assert.DoesNotContain("Payroll", new SourceSeedData(fixture.Database).Tables().Keys);
    }

    [Theory]
    [InlineData("P3")]
    [InlineData("../P1")]
    [InlineData("")]
    public void Unknown_profiles_are_refused_without_altering_state(string profile)
    {
        using var fixture = new PersistenceFixture();
        Assert.Throws<ArgumentException>(() => fixture.Load(profile));
        using var read = fixture.Database.Open();
        Assert.Empty(read.Query(1001, "SELECT run_id FROM tcc_ops.run_manifest WHERE {tenant}"));
    }

    [Theory]
    [InlineData("content_sha256")]
    [InlineData("rows")]
    [InlineData("truncated")]
    public void Corruption_rolls_back_reset_and_keeps_prior_state(string damage)
    {
        using var fixture = new PersistenceFixture();
        fixture.Load("P1");
        var root = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "tcc-seed-" + Guid.NewGuid().ToString("N"));
        var profile = System.IO.Path.Combine(root, "P1");
        Directory.CreateDirectory(profile);
        try
        {
            var original = System.IO.Path.Combine(PersistenceFixture.Root, "contract", "seed", "P1");
            foreach (var file in Directory.EnumerateFiles(original, "*", SearchOption.AllDirectories))
            {
                var destination = System.IO.Path.Combine(profile, System.IO.Path.GetRelativePath(original, file));
                Directory.CreateDirectory(System.IO.Path.GetDirectoryName(destination)!);
                File.Copy(file, destination);
            }

            var manifestPath = System.IO.Path.Combine(profile, "manifest.json");
            var manifest = JsonNode.Parse(File.ReadAllText(manifestPath))!;
            var table = manifest["tables"]!["gold/unit_year_master.jsonl.gz"]!;
            if (damage == "truncated")
            {
                using var stream = File.OpenWrite(System.IO.Path.Combine(profile, "gold", "unit_year_master.jsonl.gz"));
                stream.SetLength(20);
            }
            else
            {
                table[damage] = damage == "rows" ? JsonValue.Create(9999) : JsonValue.Create(new string('0', 64));
                File.WriteAllText(manifestPath, manifest.ToJsonString());
            }

            Assert.Throws<InvalidDataException>(() => new SeedImporter(fixture.Database, root, PersistenceFixture.Root).Load("P1"));
            using var read = fixture.Database.Open();
            Assert.Equal(16, read.Query(1001, "SELECT worksite_id FROM tcc_gold.unit_year_master WHERE {tenant}").Count);
            Assert.Single(read.Query(1001, "SELECT run_id FROM tcc_ops.run_manifest WHERE {tenant} AND run_status='success'"));
        }
        finally
        {
            foreach (var file in Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories))
            {
                File.Delete(file);
            }

            foreach (var directory in Directory.EnumerateDirectories(root, "*", SearchOption.AllDirectories).OrderByDescending(d => d.Length))
            {
                Directory.Delete(directory);
            }

            Directory.Delete(root);
        }
    }

    [Fact]
    [Trait("Category", "heavy")]
    public void Insert_failure_rolls_back_the_entire_reset()
    {
        using var fixture = new PersistenceFixture();
        fixture.Load("P1");
        using (var session = fixture.Database.Open())
        {
            session.ExecuteExempt(SqlExemption.Schema,
                "CREATE TRIGGER seed_failure BEFORE INSERT ON tcc_gold_unit_year_master BEGIN SELECT RAISE(ABORT,'Injected insert failure'); END");
        }

        Assert.Throws<SqliteException>(() => fixture.Load("P1"));
        using var read = fixture.Database.Open();
        Assert.Equal(16, read.Query(1001, "SELECT worksite_id FROM tcc_gold.unit_year_master WHERE {tenant}").Count);
        Assert.Equal(5281L, Assert.Single(read.Query(1001, "SELECT COUNT(*) AS n FROM tcc_gold.employee_period_fact WHERE {tenant}"))["n"]);
        Assert.Equal(2, read.Query(1001, "SELECT claim_id FROM tcc_ops.program_claim WHERE {tenant}").Count);
    }

    [Fact]
    public void Forward_nullable_columns_are_applied_to_existing_local_tables()
    {
        using var fixture = new PersistenceFixture(initialize: false);
        using (var session = fixture.Database.Open())
        {
            session.ExecuteExempt(SqlExemption.Schema,
                "CREATE TABLE tcc_ops.program_engagement (client_id INTEGER NOT NULL,program_code TEXT NOT NULL,scope TEXT NOT NULL,effective_from TEXT NOT NULL,effective_to TEXT,note TEXT) STRICT");
        }

        PersistenceSchema.Initialize(fixture.Database, PersistenceFixture.Root);
        using var read = fixture.Database.Open();
        var columns = read.QueryExempt(SqlExemption.Schema, "PRAGMA table_info(tcc_ops_program_engagement)").Select(r => (string)r["name"]!);
        Assert.Contains("set_by", columns);
        Assert.Contains("set_at", columns);
    }

    [Fact]
    public void Changed_applied_migration_hashes_are_refused()
    {
        using var fixture = new PersistenceFixture();
        using (var session = fixture.Database.Open())
        {
            session.ExecuteExempt(SqlExemption.Schema, "UPDATE tcc_ops.schema_migration SET sha256=? WHERE version='0000'", new string('0', 64));
        }

        Assert.Throws<InvalidOperationException>(() => PersistenceSchema.Initialize(fixture.Database, PersistenceFixture.Root));
    }

    [Fact]
    public void Schema_preserves_nullability_precision_and_declared_columns()
    {
        using var fixture = new PersistenceFixture();
        var schema = PersistenceSchema.Read(PersistenceFixture.Root);
        Assert.Equal(19, schema["tcc_gold.employee_period_fact"].Count);
        Assert.Equal(34, schema["tcc_gold.unit_year_master"].Count);
        Assert.Equal(8, schema["tcc_ops.program_engagement"].Count);
        foreach (var (name, columns) in TaxCredit.Domain.Gold.GoldColumns.All)
        {
            Assert.Equal(columns, schema["tcc_gold." + name].Select(c => c.Name));
        }

        using (var session = fixture.Database.Open())
        {
            Assert.Equal(6, session.QueryExempt(SqlExemption.Schema, "SELECT version FROM tcc_ops.schema_migration").Count);
        }

        var column = Assert.Single(schema["tcc_gold.unit_year_master"], c => c.Name == "annual_credit_usd");
        Assert.Equal(19, column.Precision);
        Assert.Equal(4, column.Scale);
        Assert.Throws<InvalidOperationException>(() => column.ConvertValue("1.00001"));
        using var connection = new SqliteConnection("Data Source=" + fixture.Path + ";Pooling=False");
        connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = "PRAGMA table_info(tcc_gold_employee_period_fact)";
        using var rows = command.ExecuteReader();
        var seen = new List<string>();
        while (rows.Read())
        {
            seen.Add(rows.GetString(1));
            if (rows.GetString(1) == "pay_period_start")
            {
                Assert.Equal("TEXT", rows.GetString(2));
                Assert.Equal(1L, rows.GetInt64(3));
            }
        }

        Assert.Equal(schema["tcc_gold.employee_period_fact"].Select(c => c.Name), seen);
    }
}
