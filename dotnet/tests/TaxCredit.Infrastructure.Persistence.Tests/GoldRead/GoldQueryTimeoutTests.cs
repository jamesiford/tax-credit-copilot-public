using System.Diagnostics;
using System.Globalization;
using Microsoft.Data.Sqlite;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Infrastructure.Persistence.GoldRead;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.GoldRead;

public sealed class GoldQueryTimeoutTests
{
    [Fact]
    public void Governed_query_actively_interrupts_SQLite_and_never_returns_partial_rows()
    {
        var folder = Path.Combine(Directory.GetCurrentDirectory(), ".gold-query-timeout-" + Guid.NewGuid().ToString("N", CultureInfo.InvariantCulture));
        Directory.CreateDirectory(folder);
        try
        {
            var settings = new SqliteConnectionStringBuilder { DataSource = Path.Combine(folder, "slow.sqlite"), Pooling = false };
            Prepare(settings.ConnectionString);
            var database = new PersistenceDatabase(() =>
            {
                var connection = new SqliteConnection(settings.ConnectionString);
                connection.CreateFunction<string, string>("slow_value", value =>
                {
                    Thread.Sleep(100);
                    return value;
                });
                return connection;
            }, new SqliteDialect());
            var service = new GoldDataQuery(database, timeoutSeconds: 1);
            var question = new GoldQuerySpec { Dataset = "run_manifest", ClientId = 1001, Select = ["run_id"] };
            var elapsed = Stopwatch.StartNew();
            Assert.Equal("query_timeout", Assert.Throws<GoldQueryException>(() => service.Run(question)).Code);
            Assert.True(elapsed.Elapsed < TimeSpan.FromSeconds(5));
            using var cancelled = new CancellationTokenSource();
            cancelled.Cancel();
            Assert.Equal("query_cancelled", Assert.Throws<GoldQueryException>(() => service.Run(question, cancelled.Token)).Code);
            Assert.Empty(service.Run(question with { TaxYears = [2030] }).Rows);
        }
        finally
        {
            Directory.Delete(folder, true);
        }
    }

    private static void Prepare(string connectionString)
    {
        using var connection = new SqliteConnection(connectionString);
        connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = "CREATE TABLE manifest_rows(client_id INTEGER,run_id TEXT,tax_year INTEGER); " +
            "WITH RECURSIVE numbers(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM numbers WHERE n<100) " +
            "INSERT INTO manifest_rows SELECT 1001,CAST(n AS TEXT),2025 FROM numbers; " +
            "CREATE VIEW tcc_ops_run_manifest AS SELECT client_id,slow_value(run_id) AS run_id,tax_year FROM manifest_rows;";
        command.ExecuteNonQuery();
    }
}
