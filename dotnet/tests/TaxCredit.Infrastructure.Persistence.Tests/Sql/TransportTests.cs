using System.Data;
using Microsoft.Data.SqlClient;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.Sql;

public sealed class TransportTests
{
    [Theory]
    [InlineData(24556)]
    [InlineData(3960)]
    [InlineData(1205)]
    public void Aborted_conflicts_rollback_the_whole_transaction_and_retry(int number)
    {
        var connections = new List<RecordingConnection>();
        var delays = new List<TimeSpan>();
        var database = new PersistenceDatabase(() =>
        {
            var connection = new RecordingConnection();
            connections.Add(connection);
            return connection;
        }, new SqlServerDialect(), delay: delays.Add);
        var calls = 0;
        Assert.Equal("done", database.Transact(session =>
        {
            session.Execute(1, "UPDATE t SET x=? WHERE {tenant}", calls);
            if (++calls < 4)
            {
                throw new NativeSqlException(number);
            }

            return "done";
        }));
        Assert.Equal(new[] { 200d, 400d, 800d }, delays.Select(t => t.TotalMilliseconds));
        Assert.Equal(3, connections.Sum(c => c.Rollbacks));
        Assert.Equal(1, connections.Sum(c => c.Commits));
        Assert.All(connections, c => Assert.True(c.WasDisposed));
    }

    [Fact]
    public void Permanent_failures_and_unknown_commit_outcomes_are_not_retried()
    {
        var connection = new RecordingConnection();
        var database = new PersistenceDatabase(() => connection, new SqlServerDialect());
        Assert.Throws<NativeSqlException>(() => database.Transact<int>(_ => throw new NativeSqlException(208)));
        Assert.Equal(1, connection.Rollbacks);
        var ambiguous = new RecordingConnection { CommitError = new IOException("Lost acknowledgement.") };
        var attempts = 0;
        var second = new PersistenceDatabase(() => { attempts++; return ambiguous; }, new SqlServerDialect());
        Assert.Throws<AmbiguousCommitException>(() => second.Transact(_ => 1));
        Assert.Equal(1, attempts);
    }

    [Fact]
    public void Opening_failure_disposes_the_connection()
    {
        var connection = new RecordingConnection { OpenError = new IOException("Offline.") };
        var database = new PersistenceDatabase(() => connection, new SqlServerDialect());
        Assert.Throws<IOException>(() => database.Open());
        Assert.True(connection.WasDisposed);
    }

    [Fact]
    public async Task Entra_connections_encrypt_validate_certificates_and_refresh_the_SQL_scope()
    {
        var tokens = new Tokens();
        var factory = new EntraSqlConnections("synthetic.invalid", "synthetic", tokens);
        using var first = factory.Create();
        using var second = factory.Create();
        var settings = new SqlConnectionStringBuilder(first.ConnectionString);
        Assert.Equal(SqlConnectionEncryptOption.Mandatory, settings.Encrypt);
        Assert.False(settings.TrustServerCertificate);
        Assert.False(settings.PersistSecurityInfo);
        Assert.Equal(4, settings.MaxPoolSize);
        Assert.Equal(ConnectionState.Closed, first.State);
        Assert.Same(first.AccessTokenCallback, second.AccessTokenCallback);
        var firstToken = await first.AccessTokenCallback!(null!, CancellationToken.None);
        var refreshed = await second.AccessTokenCallback!(null!, CancellationToken.None);
        Assert.Equal("synthetic-1", firstToken.AccessToken);
        Assert.Equal("synthetic-2", refreshed.AccessToken);
        Assert.Equal(new[] { EntraSqlConnections.Scope, EntraSqlConnections.Scope }, tokens.Scopes);
    }

    [Fact]
    public void Decimal_parameters_keep_scale_and_dates_are_typed_not_floats()
    {
        var parameter = new SqlParameter();
        SqlValues.Bind(parameter, PyDecimal.Parse("1234.50"), false);
        Assert.Equal(SqlDbType.Decimal, parameter.SqlDbType);
        Assert.Equal(2, parameter.Scale);
        Assert.Equal("1234.50", parameter.Value.ToString());
        SqlValues.Bind(parameter, new DateOnly(2026, 1, 15), false);
        Assert.Equal(SqlDbType.Date, parameter.SqlDbType);
        Assert.IsType<DateTime>(parameter.Value);
    }

    [Theory]
    [InlineData(2, 500)]
    [InlineData(34, 61)]
    public void Multirow_batches_are_parameterized_under_the_ceiling(int columnsCount, int firstRows)
    {
        var connection = new RecordingConnection();
        var database = new PersistenceDatabase(() => connection, new SqlServerDialect());
        using var session = database.Open();
        var columns = Enumerable.Range(0, columnsCount).Select(i => i == 0 ? "client_id" : "c" + i).ToArray();
        var rows = Enumerable.Range(0, 1001).Select(_ => (IReadOnlyList<object?>)Enumerable.Range(0, columnsCount)
            .Select(i => i == 0 ? (object)1L : "'; DROP TABLE t; --").ToArray()).ToArray();
        session.Insert(1, "tcc_gold.t", columns, rows);
        Assert.Equal(firstRows * columnsCount, connection.Commands[0].Values.Length);
        Assert.All(connection.Commands, c =>
        {
            Assert.InRange(c.Values.Length, 1, 2090);
            Assert.DoesNotContain("DROP TABLE", c.Sql, StringComparison.Ordinal);
            Assert.Contains("'; DROP TABLE t; --", c.Values);
        });
    }

    private sealed class Tokens : IEntraSqlTokenProvider
    {
        internal List<string> Scopes { get; } = [];
        public ValueTask<SqlAccessToken> Acquire(string scope, CancellationToken cancellationToken)
        {
            Scopes.Add(scope);
            return ValueTask.FromResult(new SqlAccessToken("synthetic-" + Scopes.Count, DateTimeOffset.UtcNow.AddHours(1)));
        }
    }
}
