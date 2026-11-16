using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.Sql;

public sealed class TenantBindingTests
{
    [Theory]
    [InlineData("999999999999999999999999999999999999999999999999999999999999")]
    [InlineData("0")]
    [InlineData("-1")]
    [InlineData("1.5")]
    public void Client_binding_refuses_out_of_range_identifiers_before_SQL(string text)
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => TaxCredit.Application.Ports.Persistence.ClientIdentity.Parse(text));
        Assert.Equal(long.MaxValue, TaxCredit.Application.Ports.Persistence.ClientIdentity.Parse("9223372036854775807"));
    }

    [Fact]
    public void Parameters_before_each_join_marker_keep_their_position()
    {
        var bound = new TenantBinding(7, ["AccountId"]).Bind(
            "SELECT ? AS q FROM a JOIN b ON {tenant:b@AccountId} AND b.k=? WHERE {tenant:a} AND a.x=?",
            ["before", "middle", "after"]);
        Assert.Equal("SELECT ? AS q FROM a JOIN b ON b.AccountId = ? AND b.k=? WHERE a.client_id = ? AND a.x=?", bound.Sql);
        Assert.Equal(new object?[] { "before", 7L, "middle", 7L, "after" }, bound.Values);
    }

    [Theory]
    [InlineData("SELECT * FROM t")]
    [InlineData("SELECT * FROM t WHERE x=1 AND {tenant}")]
    [InlineData("SELECT * FROM t WHERE ({tenant})")]
    [InlineData("SELECT '{tenant}' FROM t")]
    [InlineData("SELECT * FROM t WHERE {tenant@password}")]
    [InlineData("SELECT * FROM t WHERE {tenant} AND x=?")]
    [InlineData("SELECT * FROM t -- WHERE {tenant}")]
    public void Refused_sql_never_reaches_the_provider(string sql)
    {
        var connection = new RecordingConnection();
        var database = new PersistenceDatabase(() => connection, new SqlServerDialect());
        using var session = database.Open();
        Assert.Throws<TenantScopeViolation>(() => session.Query(7, sql));
        Assert.Empty(connection.Commands);
    }

    [Fact]
    public void Literal_question_marks_and_comments_do_not_consume_values()
    {
        var bound = new TenantBinding(1).Bind("SELECT 'can''t ?' AS q /* ? */ FROM t WHERE {tenant} AND x=?", [9L]);
        Assert.Equal(new object?[] { 1L, 9L }, bound.Values);
    }

    [Fact]
    public void Inserts_check_every_row_before_creating_a_command()
    {
        var connection = new RecordingConnection();
        var database = new PersistenceDatabase(() => connection, new SqlServerDialect());
        using var session = database.Open();
        Assert.Throws<TenantScopeViolation>(() => session.Insert(3, "tcc_ops.t", ["id"], [new object?[] { "a" }]));
        Assert.Throws<TenantScopeViolation>(() => session.Insert(3, "tcc_ops.t", ["id", "client_id"],
            [new object?[] { "a", 3L }, new object?[] { "b", 4L }]));
        Assert.Empty(connection.Commands);
    }

    [Fact]
    public void Exemptions_require_a_named_reason_and_log_every_use()
    {
        var messages = new List<string>();
        var database = new PersistenceDatabase(() => new RecordingConnection(), new SqlServerDialect(), messages.Add);
        using var session = database.Open();
        session.ExecuteExempt(SqlExemption.Worker, "SELECT 1");
        session.ExecuteExempt(SqlExemption.Worker, "SELECT 1");
        Assert.Equal(2, messages.Count);
        Assert.All(messages, message => Assert.Contains("worker claims/reaps", message, StringComparison.Ordinal));
        Assert.Throws<TenantScopeViolation>(() => session.ExecuteExempt((SqlExemption)999, "SELECT 1"));
    }

    [Fact]
    public void Identical_local_ids_cannot_cross_the_tenant_boundary()
    {
        using var fixture = new PersistenceFixture();
        fixture.Database.Transact(session =>
        {
            session.ExecuteExempt(SqlExemption.Schema, "CREATE TABLE people (client_id INTEGER NOT NULL,id TEXT NOT NULL)");
            session.Insert(1, "people", ["client_id", "id"], [new object?[] { 1L, "same" }]);
            session.Insert(2, "people", ["client_id", "id"], [new object?[] { 2L, "same" }]);
            return 0;
        });
        using var read = fixture.Database.Open();
        Assert.Equal(1L, Assert.Single(read.Query(1, "SELECT client_id,id FROM people WHERE {tenant}"))["client_id"]);
        Assert.Equal(2L, Assert.Single(read.Query(2, "SELECT client_id,id FROM people WHERE {tenant}"))["client_id"]);
    }
}
