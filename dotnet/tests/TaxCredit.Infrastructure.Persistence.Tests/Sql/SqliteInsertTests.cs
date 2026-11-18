using System.Diagnostics;
using System.Numerics;
using TaxCredit.Application.Hosting;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.Sql;

public sealed class SqliteInsertTests
{
    private static readonly string[] Columns = ["client_id", "n", "d", "t"];

    [Fact]
    public void A_large_insert_never_sends_a_statement_with_thousands_of_parameters_on_SQLite()
    {
        // Microsoft.Data.Sqlite resolves each named parameter by a linear scan, so a 2,000-parameter statement costs ~20 ms.
        using var fixture = new PersistenceFixture(false);
        Create(fixture);
        var parameters = new List<long>();
        using var listener = new ActivityListener
        {
            ShouldListenTo = source => source.Name == RunSpans.SourceName,
            Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllData,
            ActivityStopped = activity =>
            {
                if (activity.OperationName == "sql.insert-batch") { parameters.Add(Convert.ToInt64(activity.GetTagItem("parameters"), System.Globalization.CultureInfo.InvariantCulture)); }
            },
        };
        ActivitySource.AddActivityListener(listener);
        var rows = Enumerable.Range(0, 2000).Select(i => (IReadOnlyList<object?>)[1L, (long)i, "1.50", "x"]).ToArray();
        var written = fixture.Database.Transact(s => s.Insert(1, "tcc_ops.probe", Columns, rows));
        Assert.Equal(2000, written);
        Assert.NotEmpty(parameters);
        Assert.All(parameters, count => Assert.InRange(count, 1, 64));
        using var session = fixture.Database.Open();
        Assert.Equal(2000L, session.Query(1, "SELECT COUNT(*) AS n FROM tcc_ops.probe WHERE {tenant}").Single()["n"]);
    }

    [Fact]
    public void Rows_keep_their_order_nulls_and_typed_values_when_one_statement_is_reused()
    {
        using var fixture = new PersistenceFixture(false);
        Create(fixture);
        fixture.Database.Transact(s => s.Insert(1, "tcc_ops.probe", Columns,
        [
            [1L, 5L, PyDecimal.Parse("1.50"), null],
            [1L, null, null, "x"],
            [1L, new BigInteger(7), PyDecimal.Parse("2.00"), new DateOnly(2024, 1, 2)],
            [1L, 9L, null, null],
        ]));
        using var session = fixture.Database.Open();
        var rows = session.Query(1, "SELECT n, d, t FROM tcc_ops.probe WHERE {tenant} ORDER BY rowid");
        Assert.Equal([5L, null, 7L, 9L], rows.Select(r => r["n"]));
        Assert.Equal(["1.50", null, "2.00", null], rows.Select(r => r["d"]));
        Assert.Equal([null, "x", "2024-01-02", null], rows.Select(r => r["t"]));
    }

    [Fact]
    public void A_mismatched_row_writes_nothing()
    {
        using var fixture = new PersistenceFixture(false);
        Create(fixture);
        Assert.Throws<TenantScopeViolation>(() => fixture.Database.Transact(s => s.Insert(1, "tcc_ops.probe", Columns,
            [[1L, 1L, "1.00", "a"], [1L, 2L]])));
        using var session = fixture.Database.Open();
        Assert.Equal(0L, session.Query(1, "SELECT COUNT(*) AS n FROM tcc_ops.probe WHERE {tenant}").Single()["n"]);
    }

    private static void Create(PersistenceFixture fixture) => fixture.Database.Transact(s =>
        s.ExecuteExempt(SqlExemption.Schema, "CREATE TABLE tcc_ops_probe (client_id INTEGER NOT NULL, n INTEGER, d TEXT, t TEXT)"));
}
