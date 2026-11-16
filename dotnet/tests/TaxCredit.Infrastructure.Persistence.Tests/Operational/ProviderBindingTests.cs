using TaxCredit.Domain.Claims;
using System.Data;
using System.Globalization;
using TaxCredit.Domain.Warehouse;
using TaxCredit.Infrastructure.Persistence.Operational;
using TaxCredit.Infrastructure.Persistence.Sql;
using TaxCredit.Infrastructure.Persistence.Tests.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.Operational;

public sealed class ProviderBindingTests
{
    [Fact]
    public void Native_override_order_is_transactional_bound_and_independent_of_timestamp_and_public_id()
    {
        using var connection = new RecordingConnection
        {
            Read = (sql, _) =>
            {
                var result = new DataTable { Locale = CultureInfo.InvariantCulture };
                if (sql.StartsWith("SELECT last_value", StringComparison.Ordinal))
                {
                    result.Columns.Add("last_value", typeof(long));
                    result.Rows.Add(42L);
                }
                return result;
            },
        };
        var database = new PersistenceDatabase(() => connection, new SqlServerDialect());
        var at = RunBatchRepositoryTests.At(0);
        var row = new ManualOverride("z", "run", 11, "unit", "GA_JTC:local", "base_year", null, "2023", "reason",
            "Synthetic ordering check", "author", at);
        var repository = new ManualOverrideRepository(database);
        repository.Record(row);
        Assert.Equal(1, connection.Commits);
        var sequence = Assert.Single(connection.Commands, c => c.Sql.StartsWith("UPDATE tcc_ops.write_sequence", StringComparison.Ordinal));
        Assert.Equal(["manual_override"], sequence.Values);
        var insert = Assert.Single(connection.Commands, c => c.Sql.Contains("INSERT INTO [tcc_ops].[manual_override]", StringComparison.Ordinal));
        Assert.Equal(42L, insert.Values[^1]);
        Assert.Equal("z", insert.Values[0]);
        Assert.Equal(11L, insert.Values[2]);
        Assert.IsType<DateTime>(insert.Values[11]);
        repository.History(11);
        var history = connection.Commands[^1];
        Assert.EndsWith("ORDER BY write_order", history.Sql, StringComparison.Ordinal);
        Assert.Equal([11L], history.Values);
        Assert.DoesNotContain("rowid", history.Sql, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void WarehouseClaimsBindTypedDatesAndUtcInstantsWithoutScalingMoney()
    {
        using var connection = new RecordingConnection();
        var database = new PersistenceDatabase(() => connection, new SqlServerDialect());
        var instant = RunBatchRepositoryTests.At(0) with { OffsetMinutes = 330, Microsecond = 123456 };
        var claim = ProgramClaim.Create(ClaimRepositoryTests.Claim(11, "typed").ToSpec() with { DecidedAt = instant, EffectiveFrom = instant });
        new ClaimRepository(database).Record(claim);
        var insert = connection.Commands.Last();
        Assert.Contains("INSERT INTO", insert.Sql, StringComparison.Ordinal);
        Assert.Equal("1234.50", insert.Values[7]);
        var timestamp = Assert.IsType<DateTime>(insert.Values[20]);
        Assert.Equal(new DateTime(2026, 1, 1, 6, 30, 0, DateTimeKind.Utc).AddTicks(1234560), timestamp);
        Assert.Equal(DateTimeKind.Utc, timestamp.Kind);
        Assert.Equal(new DateTime(2026, 1, 1), Assert.IsType<DateTime>(insert.Values[22]));
        Assert.Equal(1, connection.Commits);
    }

    [Fact]
    public void WarehouseLeasePredicatesAndUpdatesShareTypedUtcClock()
    {
        using var connection = new RecordingConnection();
        var database = new PersistenceDatabase(() => connection, new SqlServerDialect());
        var now = RunBatchRepositoryTests.At(0) with { OffsetMinutes = 330 };
        Assert.True(new RunBatchRepository(database).Heartbeat(11, "item", "owner", 120, now));
        var command = Assert.Single(connection.Commands);
        Assert.Equal(new DateTime(2026, 1, 1, 6, 30, 0, DateTimeKind.Utc), Assert.IsType<DateTime>(command.Values[0]));
        Assert.Equal(new DateTime(2026, 1, 1, 6, 32, 0, DateTimeKind.Utc), Assert.IsType<DateTime>(command.Values[1]));
        Assert.Equal(command.Values[0], command.Values[^1]);
    }
}
