using System.Data;
using System.Globalization;
using Microsoft.Data.SqlClient;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.Sql;

/// <summary>
/// A throwaway database on a SQL Server-family instance named by <c>TCC_SQLSERVER_TEST</c> (a connection string without a catalog, for example
/// <c>Server=(localdb)\MSSQLLocalDB;Integrated Security=true;TrustServerCertificate=true</c>). It carries the deployed bootstrap DDL and forward
/// migrations, so it exercises the same statements and the same bulk protocol as the Warehouse and Azure SQL. Unset means "no target here".
/// </summary>
internal sealed class SqlServerTarget : IDisposable
{
    internal const string Setting = "TCC_SQLSERVER_TEST";
    private readonly string _server;
    private readonly string _name = "tcc_s5_" + Guid.NewGuid().ToString("N")[..12];

    private SqlServerTarget(string server)
    {
        _server = server;
        using (var admin = new SqlConnection(server))
        {
            admin.Open();
            Run(admin, "CREATE DATABASE [" + _name + "]");
        }

        using var connection = new SqlConnection(ConnectionString);
        connection.Open();
        var schema = Path.Combine(PersistenceFixture.Root, "docs", "data", "schema");
        // A Warehouse declares keys NOT ENFORCED; SQL Server has no such clause, so the keys are simply enforced here.
        foreach (var file in new[] { Path.Combine(schema, "tcc-schema.sqlserver.sql") }
            .Concat(Directory.EnumerateFiles(Path.Combine(schema, "migrations"), "*.sql").Order(StringComparer.Ordinal)))
        {
            foreach (var batch in System.Text.RegularExpressions.Regex.Split(File.ReadAllText(file).Replace(" NOT ENFORCED;", ";", StringComparison.Ordinal), @"^\s*GO\s*$", System.Text.RegularExpressions.RegexOptions.Multiline))
            {
                if (!string.IsNullOrWhiteSpace(batch))
                {
                    Run(connection, batch);
                }
            }
        }
    }

    internal static bool Configured => !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable(Setting));

    internal static SqlServerTarget? TryCreate() => Configured ? new SqlServerTarget(Environment.GetEnvironmentVariable(Setting)!) : null;

    internal string ConnectionString => new SqlConnectionStringBuilder(_server) { InitialCatalog = _name, Pooling = false }.ConnectionString;

    internal PersistenceDatabase Database(BulkLoadPolicy policy) => new(() => new SqlConnection(ConnectionString), new SqlServerDialect(policy));

    private static void Run(SqlConnection connection, string sql)
    {
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        command.CommandTimeout = 300;
        command.ExecuteNonQuery();
    }

    public void Dispose()
    {
        SqlConnection.ClearAllPools();
        using var admin = new SqlConnection(_server);
        admin.Open();
        Run(admin, "ALTER DATABASE [" + _name + "] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [" + _name + "]");
    }

    /// <summary>A hash of every stored Gold row and the run manifest for a client, independent of physical row order.</summary>
    internal static string Dump(PersistenceDatabase database, long clientId)
    {
        using var session = database.Open();
        var lines = new List<string>();
        foreach (var table in Tables)
        {
            foreach (var row in session.Query(clientId, "SELECT * FROM " + table + " WHERE {tenant}"))
            {
                lines.Add(table + "|" + string.Join("|", row.Select(cell => cell.Key + "=" + Text(cell.Value))));
            }
        }

        lines.Sort(StringComparer.Ordinal);
        return Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(string.Join("\n", lines)))) + " (" + lines.Count + " rows)";
    }

    private static string Text(object? value) => value switch
    {
        null => "NULL",
        DateTime time => time.ToString("O", CultureInfo.InvariantCulture),
        decimal number => number.ToString(CultureInfo.InvariantCulture),
        bool flag => flag ? "1" : "0",
        _ => Convert.ToString(value, CultureInfo.InvariantCulture) ?? string.Empty,
    };

    private static readonly string[] Tables =
    [
        "tcc_ops.run_manifest", "tcc_gold.employee_period_fact", "tcc_gold.employee_eligibility", "tcc_gold.onezero_matrix",
        "tcc_gold.unit_month_summary", "tcc_gold.run_method_summary", "tcc_gold.unit_year_master", "tcc_gold.unit_credit_installment",
    ];
}
