using System.Diagnostics;

namespace TaxCredit.Infrastructure.Persistence.Tests.Sql;

public sealed class BoundedReadTests
{
    private const string Expensive = """
        WITH RECURSIVE numbers(client_id, value) AS (
            SELECT 1, 1 UNION ALL SELECT client_id, value + 1 FROM numbers WHERE value < 1000000000
        )
        SELECT COUNT(*) AS total FROM numbers WHERE {tenant}
        """;

    [Fact]
    public void SQLite_interrupts_expensive_reads_at_the_deadline_and_the_session_remains_usable()
    {
        using var fixture = new PersistenceFixture(false);
        using var session = fixture.Database.Open();
        var clock = Stopwatch.StartNew();
        Assert.Throws<TimeoutException>(() => session.QueryBounded(1, Expensive, 1, 1, CancellationToken.None));
        Assert.InRange(clock.Elapsed.TotalSeconds, 0.5, 5);
        Assert.Single(session.QueryBounded(1, "SELECT 1 AS client_id WHERE {tenant}", 1, 1, CancellationToken.None));
    }

    [Fact]
    public void Cancellation_interrupts_SQLite_without_waiting_for_the_query_timeout()
    {
        using var fixture = new PersistenceFixture(false);
        using var session = fixture.Database.Open();
        using var cancellation = new CancellationTokenSource(TimeSpan.FromMilliseconds(100));
        var clock = Stopwatch.StartNew();
        Assert.Throws<OperationCanceledException>(() => session.QueryBounded(1, Expensive, 1, 30, cancellation.Token));
        Assert.InRange(clock.Elapsed.TotalSeconds, 0, 5);
        Assert.Single(session.Query(1, "SELECT 1 AS client_id WHERE {tenant}"));
    }

    [Fact]
    public void Exceeding_the_row_cap_refuses_instead_of_returning_a_partial_result()
    {
        using var fixture = new PersistenceFixture(false);
        using var session = fixture.Database.Open();
        Assert.Throws<InvalidOperationException>(() => session.QueryBounded(1,
            "SELECT 1 AS client_id WHERE {tenant} UNION ALL SELECT 1", 1, 1, CancellationToken.None));
    }
}
